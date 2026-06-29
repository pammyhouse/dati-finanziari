import os
import json
import time
import requests
import random
import re

# ==========================================
# CONFIGURAZIONI
# ==========================================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev" # Il tuo Worker
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") # ATTENZIONE: Ora è GROQ con la Q
HISTORY_FILE = "checked_ads.json"
BATCH_SIZE = 10 

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
    ads_dict = {}
    print("📡 Download annunci dal server Cloudflare...")
    for fmt in ['banner', 'interstitial']:
        try:
            res = requests.get(f"{WORKER_URL}/api/serve?format={fmt}&geo=global", timeout=10)
            if res.status_code == 200:
                for ad in res.json().get('ads', []):
                    ads_dict[ad['id']] = ad
        except Exception as e:
            print(f"Errore connessione Cloudflare ({fmt}): {e}")
    return list(ads_dict.values())

def flag_ad(ad_id, reason):
    print(f"🚨 AD FLAGGATO! ID: {ad_id} | Motivo: {reason}")
    for _ in range(3):
        try:
            requests.post(f"{WORKER_URL}/api/report?id={ad_id}", timeout=5)
        except:
            pass
        time.sleep(0.5)

def analyze_batch(ads_batch, provider):
    prompt = """You are a strict Trust & Safety AI Sentinel for an Ad Network.
Analyze this batch of ads and check for policy violations.
Rules for FLAG: NSFW/Porn, Violence, Scams, Malware, Phishing or Illegal activities.
For each ad, you MUST reply with exactly this format on a new line:
[ID] -> PASS
or
[ID] -> FLAG: [Brief Reason]

Here is the batch to check:
"""
    for ad in ads_batch:
        prompt += f"\n--- ID: {ad['id']}\nHeadline: {ad.get('headline','')}\nDesc: {ad.get('description','')}\nURL: {ad.get('destination_url','')}\n"

    print(f"🧠 Tentativo con {provider.upper()}...")
    response_text = ""
    
    try:
        if provider == 'groq':
            # La vera API 100% gratuita di Groq.com (modello Llama 3)
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}", 
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama3-8b-8192", 
                "messages": [{"role": "user", "content": prompt}]
            }
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
            
            if res.status_code == 200:
                response_text = res.json()['choices'][0]['message']['content']
            else:
                print(f"⚠️ GROQ Errore {res.status_code}: {res.text}")
                return None

        elif provider == 'gemini':
            # Fallback su Gemini (se l'account Google non è bloccato)
            models_to_try = ["gemini-1.5-flash", "gemini-1.5-flash-8b"]
            success = False
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                res = requests.post(url, json=payload, timeout=20)
                
                if res.status_code == 200:
                    response_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                    success = True
                    break
                elif res.status_code == 429:
                    print(f"⚠️ GEMINI ({model_name}): Quota esaurita o Limite a 0 (Blocco Europeo).")
                    break # Inutile riprovare altri modelli se l'account è bloccato
                else:
                    print(f"⚠️ GEMINI ({model_name}): Errore {res.status_code}")
                    continue
            
            if not success:
                return None
                
    except Exception as e:
        print(f"❌ Errore di rete con {provider}: {e}")
        return None

    # Estrazione dei risultati
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
        print("📭 Nessun annuncio trovato nella rete. Esco.")
        return

    history = load_history()
    current_time = time.time()
    
    ads.sort(key=lambda x: history.get(x['id'], 0))
    
    available_ais = []
    # Diamo priorità assoluta a Groq perché sappiamo che funziona ed è gratis
    if GROQ_API_KEY: available_ais.append('groq')
    if GEMINI_API_KEY: available_ais.append('gemini')
    
    if not available_ais:
        print("❌ Nessuna API Key configurata. Esco.")
        return

    max_ads_to_check = 50 
    ads_to_check = ads[:max_ads_to_check]
    batches = [ads_to_check[i:i + BATCH_SIZE] for i in range(0, len(ads_to_check), BATCH_SIZE)]
    
    print(f"🔍 Sentinel: Analisi di {len(ads_to_check)} annunci in {len(batches)} batch.")
    
    for batch in batches:
        batch_results = None
        
        # Prova prima Groq, se fallisce passa a Gemini
        for ai_provider in available_ais:
            batch_results = analyze_batch(batch, ai_provider)
            if batch_results is not None:
                print(f"✅ Batch analizzato con successo da {ai_provider.upper()}.")
                break 
        
        if batch_results is None:
            print("❌ Tutti i provider AI hanno fallito per questo batch.")
            continue
            
        for ad in batch:
            ad_id = ad['id']
            res = batch_results.get(ad_id)
            
            if res and res['status'] == "FLAG":
                flag_ad(ad_id, res['reason'])
            
            history[ad_id] = current_time
            
        time.sleep(1) # Groq è velocissimo, basta 1 secondo di pausa
        
    save_history(history)
    print("🏁 Controllo completato.")

if __name__ == "__main__":
    run_sentinel()
