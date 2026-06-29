import os
import json
import time
import requests
import random
import re

# ==========================================
# CONFIGURAZIONI E VARIABILI D'AMBIENTE
# ==========================================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev" # Sostituisci con il tuo Worker URL se diverso
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROK_API_KEY = os.environ.get("GROK_API_KEY")
HISTORY_FILE = "checked_ads.json"
BATCH_SIZE = 10 # Analizza 10 annunci per ogni richiesta AI

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

def get_ads_from_server():
    """Fa solo 2 chiamate al server per estrarre il massimo degli annunci disponibili"""
    ads_dict = {}
    print("📡 Contatto il server Cloudflare per scaricare gli annunci...")
    for fmt in ['banner', 'interstitial']:
        try:
            res = requests.get(f"{WORKER_URL}/api/serve?format={fmt}&geo=global", timeout=10)
            if res.status_code == 200:
                for ad in res.json().get('ads', []):
                    ads_dict[ad['id']] = ad
        except Exception as e:
            print(f"Errore fetch {fmt}: {e}")
    return list(ads_dict.values())

def flag_ad(ad_id, reason):
    print(f"🚨 AD FLAGGATO! ID: {ad_id} | Motivo: {reason}")
    # 3 report consecutivi faranno scattare il ban automatico sul tuo worker
    for _ in range(3):
        try:
            requests.post(f"{WORKER_URL}/api/report?id={ad_id}", timeout=5)
        except:
            pass
        time.sleep(0.5)

def analyze_batch(ads_batch, provider):
    """Analizza un lotto di annunci con l'AI scelta"""
    
    prompt = """You are a strict Trust & Safety AI Sentinel. Analyze this batch of ads.
Rules for FLAG: NSFW/Porn, Violence, Scams, Malware, Phishing or Illegal activities.
For each ad, you MUST reply with exactly this format on a new line:
[ID] -> PASS
or
[ID] -> FLAG: [Brief Reason]

Here are the ads:
"""
    for ad in ads_batch:
        prompt += f"\n--- ID: {ad['id']}\nHeadline: {ad.get('headline','')}\nDesc: {ad.get('description','')}\nURL: {ad.get('destination_url','')}\n"

    print(f"🧠 Inviando batch a {provider.upper()}...")
    
    response_text = ""
    
    try:
        if provider == 'gemini':
            # Utilizzo del NUOVO SDK ufficiale google-genai
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            # Usiamo gemini-1.5-flash che ha il Free Tier GARANTITO (1500 req/giorno)
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
            )
            response_text = response.text
            
        elif provider == 'grok':
            headers = {"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": "grok-beta", "messages": [{"role": "user", "content": prompt}]}
            res = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                response_text = res.json()['choices'][0]['message']['content']
                
    except Exception as e:
        print(f"❌ Errore API {provider}: {e}")
        return {}

    # Parsing intelligente della risposta (estrae ID e verdetto)
    results = {}
    for ad in ads_batch:
        ad_id = ad['id']
        match = re.search(rf"{ad_id}\s*(?:->|:|-)?\s*(FLAG|PASS)(.*)", response_text, re.IGNORECASE)
        if match:
            status = match.group(1).upper()
            reason = match.group(2).strip(" :->") if status == "FLAG" else ""
            results[ad_id] = {"status": status, "reason": reason}
        else:
            results[ad_id] = {"status": "PASS", "reason": ""}
            
    return results

def run_sentinel():
    ads = get_ads_from_server()
    if not ads:
        print("Nessun annuncio trovato. Esco.")
        return

    history = load_history()
    current_time = time.time()
    
    # Ordiniamo gli annunci: prima quelli MAI visti, poi quelli controllati più vecchi
    ads.sort(key=lambda x: history.get(x['id'], 0))
    
    available_ais = []
    if GEMINI_API_KEY: available_ais.append('gemini')
    if GROK_API_KEY: available_ais.append('grok')
    
    if not available_ais:
        print("❌ Nessuna API Key configurata. Esco.")
        return

    # Prendiamo solo i primi N annunci per non consumare troppe risorse in una run
    max_ads_to_check = 50 
    ads_to_check = ads[:max_ads_to_check]
    
    # Dividiamo in lotti (batches)
    batches = [ads_to_check[i:i + BATCH_SIZE] for i in range(0, len(ads_to_check), BATCH_SIZE)]
    
    for batch in batches:
        chosen_ai = random.choice(available_ais)
        results = analyze_batch(batch, chosen_ai)
        
        for ad in batch:
            ad_id = ad['id']
            res = results.get(ad_id)
            
            if res and res['status'] == "FLAG":
                flag_ad(ad_id, res['reason'])
            
            # Aggiorniamo lo storico con il timestamp attuale
            history[ad_id] = current_time
            
        time.sleep(2) # Pausa tra un lotto e l'altro
        
    save_history(history)
    print("✅ Controllo completato. Memoria aggiornata.")

if __name__ == "__main__":
    run_sentinel()
