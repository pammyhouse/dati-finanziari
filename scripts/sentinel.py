import os
import json
import time
import requests
import random
import re
from google import genai
from google.genai import types

# ==========================================
# CONFIGURAZIONI E VARIABILI D'AMBIENTE
# ==========================================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev" # Controlla che sia corretto
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
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

def analyze_batch_with_retry(ads_batch, provider, max_retries=3, initial_delay=5):
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

    print(f"🧠 Inviando batch a {provider.upper()}...")
    
    delay = initial_delay
    response_text = ""

    for attempt in range(max_retries):
        try:
            if provider == 'groq':
                # Implementazione Ufficiale GROQ aggiornata ai nuovi modelli Llama 3.1
                headers = {
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "llama-3.1-8b-instant", # IL MODELLO NUOVO E SUPPORTATO
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                }
                res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
                
                if res.status_code == 200:
                    response_text = res.json()['choices'][0]['message']['content']
                    break
                else:
                    err_msg = res.text
                    print(f"⚠️ GROQ Errore {res.status_code}: {err_msg}")
                    if res.status_code == 429:
                        print(f"🕒 Rate limit Groq, attendo {delay}s...")
                        time.sleep(delay)
                        delay *= 2
                        continue
                    else:
                        return None # Altri errori fatali (es. 401 Auth)

            elif provider == 'gemini':
                # Implementazione GEMINI 2.5 presa dal tuo codice funzionante
                client = genai.Client(api_key=GEMINI_API_KEY)
                response = client.models.generate_content(
                    model='gemini-2.5-flash', 
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.1)
                )
                if not response or not response.text:
                    raise ValueError("Risposta vuota dal modello")
                response_text = response.text
                break

        except Exception as e:
            err_msg = str(e).upper()
            print(f"⚠️ Errore {provider.upper()}: {e}")
            if any(x in err_msg for x in ["503", "429", "404", "UNAVAILABLE", "EXHAUSTED", "NONE"]):
                if attempt < max_retries - 1:
                    print(f"🕒 Riprovo in {delay}s...")
                    time.sleep(delay)
                    delay *= 2
                    continue
            return None 

    if not response_text:
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
    available_ais = []
    if GROQ_API_KEY: available_ais.append('groq')
    if GEMINI_API_KEY: available_ais.append('gemini')
    
    if not available_ais:
        print("❌ Nessuna API Key configurata. Esco.")
        return

    ads = get_ads_from_server()
    if not ads:
        print("📭 Nessun annuncio trovato nella rete. Esco.")
        return

    history = load_history()
    current_time = time.time()
    
    # Priorità agli annunci mai visti o visti da più tempo
    ads.sort(key=lambda x: history.get(x['id'], 0))
    
    max_ads_to_check = 50 
    ads_to_check = ads[:max_ads_to_check]
    batches = [ads_to_check[i:i + BATCH_SIZE] for i in range(0, len(ads_to_check), BATCH_SIZE)]
    
    print(f"🔍 Sentinel: Analisi di {len(ads_to_check)} annunci in {len(batches)} batch.")
    
    for batch in batches:
        batch_results = None
        
        # Prova i provider disponibili finché uno non funziona
        for ai_provider in available_ais:
            batch_results = analyze_batch_with_retry(batch, ai_provider)
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
    print("🏁 Controllo completato. Registro aggiornato.")
    os._exit(0)

if __name__ == "__main__":
    try:
        run_sentinel()
    except Exception as e:
        print(f"❌ Errore critico finale: {e}")
        os._exit(1)
