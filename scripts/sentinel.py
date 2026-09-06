import os
import json
import time
import requests
import re
import sys

# ==========================
# CONFIGURATION - SECRETS & LIMITS
# ==========================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"

SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY")
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")

if not all([SENTINEL_SECRET_KEY, CF_ACCOUNT_ID, CF_API_TOKEN]):
    print("❌ ERRORE CRITICO: Credenziali mancanti. Assicurati di aver configurato i GitHub Secrets.")
    sys.exit(1)

# PROTEZIONE COSTI: Massimo 5 annunci ad ogni avvio.
# Girando ogni ora sono max 120 annunci/giorno -> Consumo: ~500 neuroni/giorno (Limite gratis: 10.000/giorno). Costo: $0.00.
MAX_ADS_PER_RUN = 50

# Usiamo il modello Llama 3.1 8B (Nessun blocco Europeo, precisissimo con i JSON)
TEXT_MODEL = "@cf/meta/llama-3.1-8b-instruct"

print("🤖 Avvio AdSwap Sentinel AI...")

# ==========================
# HELPER: CLOUDFLARE AI
# ==========================
def ask_cloudflare_ai(text_prompt):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{TEXT_MODEL}"
    
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messages": [
            {
                "role": "system",
                "content": "You are a strict advertising moderation AI. Analyze the provided App Name, Headline, Description, and URL. Flag the ad if it contains or promotes: NSFW (nudity, pornography), illegal drugs, weapons, graphic violence, malware, phishing, or obvious scams. If it's a normal safe app/ad, you must pass it. Reply ONLY with a valid JSON in this exact format: {\"status\": \"PASS\" or \"FLAG\", \"reason\": \"Brief explanation\"}. Do not write any other text."
            },
            {
                "role": "user",
                "content": text_prompt
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        res_json = response.json()
        
        if response.status_code == 200 and res_json.get("success"):
            ai_response = res_json["result"]["response"]
            
            # Se Cloudflare restituisce direttamente un Dizionario Python
            if isinstance(ai_response, dict):
                return ai_response
                
            # Se restituisce una Stringa, usiamo la Regex per estrarre il JSON in modo infallibile
            json_match = re.search(r'\{.*\}', ai_response.replace('\n', ''), re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            else:
                return {"status": "FLAG", "reason": "AI did not return valid JSON format."}
        else:
            print(f"❌ Errore API Cloudflare: {response.text}")
            return {"status": "FLAG", "reason": "AI_API_ERROR"}
    except Exception as e:
        print(f"❌ Errore di connessione o Parsing: {e}")
        return {"status": "FLAG", "reason": "NETWORK_ERROR"}

# ==========================
# ACTIONS
# ==========================
def approve_ad(ad_id):
    print(f"✅ APPROVATO: {ad_id}")
    try:
        requests.post(f"{WORKER_URL}/api/admin/creatives/approve?id={ad_id}", headers={"X-Sentinel-Key": SENTINEL_SECRET_KEY}, timeout=10)
    except: pass

def flag_ad(ad_id, reason):
    print(f"🚨 FLAGGATO ({reason}): {ad_id}")
    # Segnala 10 volte consecutive per portarlo in stato "Flagged" nel database
    for _ in range(10):
        try:
            requests.post(f"{WORKER_URL}/api/report?id={ad_id}", timeout=5)
            time.sleep(0.2)
        except: pass

# ==========================
# MAIN LOOP
# ==========================
def run_sentinel():
    headers = {"X-Sentinel-Key": SENTINEL_SECRET_KEY}
    
    # 1. Recupera SOLO gli annunci in attesa di revisione ("pending")
    try:
        res = requests.get(f"{WORKER_URL}/api/admin/creatives/pending", headers=headers, timeout=20)
        ads = res.json()
    except Exception as e:
        print(f"❌ Errore di connessione al Worker: {e}")
        return

    if not ads:
        print("📭 Nessun annuncio in coda di revisione. Termino.")
        return

    # Limite di sicurezza sui costi
    queue = ads[:MAX_ADS_PER_RUN]
    
    print(f"🔍 Trovati {len(ads)} annunci pending. Analizzo i primi {len(queue)}...")

    for ad in queue:
        ad_id = ad["id"]
        print(f"\n⏳ Analisi annuncio: {ad.get('app_name')}...")

        text_prompt = f"App Name: {ad.get('app_name')}\nHeadline: {ad.get('headline')}\nDescription: {ad.get('description')}\nDestination URL: {ad.get('destination_url')}"

        # Chiama l'Intelligenza Artificiale (Solo Testo e URL)
        ai_verdict = ask_cloudflare_ai(text_prompt)

        if ai_verdict.get("status") == "PASS":
            approve_ad(ad_id)
        else:
            reason = ai_verdict.get("reason", "Violazione Sconosciuta")
            flag_ad(ad_id, reason)

    print("\n🏁 Revisione automatica completata.")

if __name__ == "__main__":
    run_sentinel()
