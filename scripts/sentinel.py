import os
import json
import time
import requests
import re
from google import genai
from google.genai import types

# ==========================================
# CONFIGURAZIONI E VARIABILI D'AMBIENTE
# ==========================================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev" # Controlla che sia il tuo vero URL
HISTORY_FILE = "checked_ads.json"
BATCH_SIZE = 10 # Analizza 10 annunci per volta

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

def analyze_batch_with_retry(ads_batch, max_retries=5, initial_delay=10):
    """Sfrutta il tuo codice infallibile per analizzare il batch con Gemini 2.5 Flash"""
    
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

    print(f"🧠 Inviando batch di {len(ads_batch)} annunci a GEMINI 2.5 Flash...")
    
    # Inizializza il client esattamente come nel tuo repo funzionante
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    delay = initial_delay
    response_text = ""

    for attempt in range(max_retries):
        try:
            print(f"🔄 Tentativo {attempt + 1}/{max_retries}...")
            
            response = client.models.generate_content(
                model='gemini-2.5-flash', 
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1, # Bassa per risposte molto rigide e precise
                )
            )
            
            if not response or not response.text:
                raise ValueError("Risposta vuota dal modello")
                
            response_text = response.text.strip()
            break # Usciamo dal loop dei tentativi se è andato a buon fine!

        except Exception as e:
            err_msg = str(e).upper()
            print(f"⚠️ Errore API: {e}")
            if any(x in err_msg for x in ["503", "429", "404", "UNAVAILABLE", "EXHAUSTED", "NONE", "RESOURCE_EXHAUSTED"]):
                if attempt < max_retries - 1:
                    print(f"🕒 Quota/Limite raggiunto temporaneamente. Riprovo in {delay}s...")
                    time.sleep(delay)
                    delay *= 2
                    continue
            return None # Se fallisce tutti i tentativi o c'è un errore fatale

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
    if not os.environ.get("GEMINI_API_KEY"):
        print("❌ Nessuna API Key GEMINI configurata. Esco.")
        return

    ads = get_ads_from_server()
    if not ads:
        print("📭 Nessun annuncio trovato nella rete. Esco.")
        return

    history = load_history()
    current_time = time.time()
    
    # Ordiniamo: i nuovi annunci (0) vanno in cima
    ads.sort(key=lambda x: history.get(x['id'], 0))
    
    max_ads_to_check = 50 
    ads_to_check = ads[:max_ads_to_check]
    batches = [ads_to_check[i:i + BATCH_SIZE] for i in range(0, len(ads_to_check), BATCH_SIZE)]
    
    print(f"🔍 Sentinel: Analisi di {len(ads_to_check)} annunci in {len(batches)} batch.")
    
    for batch in batches:
        batch_results = analyze_batch_with_retry(batch)
        
        if batch_results is None:
            print("❌ Analisi fallita per questo lotto dopo multipli tentativi.")
            continue
            
        for ad in batch:
            ad_id = ad['id']
            res = batch_results.get(ad_id)
            
            if res and res['status'] == "FLAG":
                flag_ad(ad_id, res['reason'])
            
            # Aggiorniamo il timestamp di controllo per questo annuncio
            history[ad_id] = current_time
            
        time.sleep(5) # Pausa tranquilla prima del prossimo batch
        
    save_history(history)
    print("🏁 Controllo completato con successo. Registro memoria aggiornato.")
    
    # Chiusura d'emergenza sicura per GitHub Actions
    os._exit(0)

if __name__ == "__main__":
    try:
        run_sentinel()
    except Exception as e:
        print(f"❌ Errore critico finale: {e}")
        os._exit(1)
