import os
import json
import time
import requests
import random
import re

# ==========================================
# CONFIGURAZIONI
# ==========================================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev" # Assicurati che sia il tuo vero Worker URL
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROK_API_KEY = os.environ.get("GROK_API_KEY")
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
    """Restituisce un dizionario con i risultati, oppure None se il provider fallisce completamente."""
    prompt = """You are a strict Trust & Safety AI Sentinel for a developer Ad Network.
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
        if provider == 'gemini':
            # LISTA AGGIORNATA: Priorità assoluta al modello leggero '8b' per i Free Tier
            models_to_try = ["gemini-1.5-flash-8b", "gemini-1.5-flash", "gemini-2.0-flash"]
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
                    print(f"⚠️ {provider.upper()} ({model_name}): Quota esaurita o Limite a 0.")
                    continue # Prova con il prossimo modello Gemini (a volte hanno quote diverse)
                else:
                    print(f"⚠️ {provider.upper()} ({model_name}): Errore {res.status_code}")
                    continue
            
            if not success:
                return None

        elif provider == 'grok':
            # LISTA AGGIORNATA: I modelli stabili attuali della API xAI
            models_to_try = ["grok-2-latest", "grok-2", "grok-3-mini", "grok-4.3"]
            success = False
            headers = {"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"}
            
            for model_name in models_to_try:
                payload = {"model": model_name, "messages": [{"role": "user", "content": prompt}]}
                res = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload, timeout=20)
                
                if res.status_code == 200:
                    response_text = res.json()['choices'][0]['message']['content']
                    success = True
                    break
                elif res.status_code == 429:
                    print(f"⚠️ {provider.upper()} ({model_name}): Quota esaurita.")
                    return None
                elif res.status_code == 400 and ("Model not found" in res.text or "invalid-argument" in res.text):
                    print(f"⚠️ {provider.upper()} ({model_name}): Deprecato. Passo al successivo...")
                    continue
                else:
                    print(f"⚠️ {provider.upper()} ({model_name}): Errore {res.status_code}")
                    continue
                    
            if not success:
                return None
                
    except Exception as e:
        print(f"❌ Errore Connessione Rete con {provider}: {e}")
        return None

    # Parsing dei risultati a prova di errore
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
    if GEMINI_API_KEY: available_ais.append('gemini')
    if GROK_API_KEY: available_ais.append('grok')
    
    if not available_ais:
        print("❌ Nessuna API Key configurata. Esco.")
        return

    max_ads_to_check = 50 
    ads_to_check = ads[:max_ads_to_check]
    batches = [ads_to_check[i:i + BATCH_SIZE] for i in range(0, len(ads_to_check), BATCH_SIZE)]
    
    print(f"🔍 Sentinel: Analisi di {len(ads_to_check)} annunci in {len(batches)} batch.")
    
    for batch in batches:
        random.shuffle(available_ais)
        
        batch_results = None
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
            
        time.sleep(2) 
        
    save_history(history)
    print("🏁 Controllo completato.")

if __name__ == "__main__":
    run_sentinel()
