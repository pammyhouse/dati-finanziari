import os
import json
import time
import requests
import random
import re

# ==========================================
# CONFIGURAZIONI E VARIABILI D'AMBIENTE
# ==========================================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev" # Il tuo Worker Cloudflare
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROK_API_KEY = os.environ.get("GROK_API_KEY")
HISTORY_FILE = "checked_ads.json"
BATCH_SIZE = 10 # Impacchetta 10 annunci alla volta (massimizza l'uso gratuito)

def load_history():
    """Carica la memoria storica degli annunci già controllati"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_history(history):
    """Salva la memoria storica su file JSON (che GitHub committerà)"""
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

def get_ads_from_server():
    """Ottimizzazione Server: 2 sole chiamate a Cloudflare per scaricare TUTTO il database"""
    ads_dict = {}
    print("📡 Contatto il server Cloudflare per scaricare l'intero database annunci...")
    for fmt in ['banner', 'interstitial']:
        try:
            # Scarichiamo tutti gli annunci in un colpo solo
            res = requests.get(f"{WORKER_URL}/api/serve?format={fmt}&geo=global", timeout=10)
            if res.status_code == 200:
                for ad in res.json().get('ads', []):
                    ads_dict[ad['id']] = ad
        except Exception as e:
            print(f"Errore fetch {fmt}: {e}")
    return list(ads_dict.values())

def flag_ad(ad_id, reason):
    print(f"🚨 AD FLAGGATO! ID: {ad_id} | Motivo: {reason}")
    # 3 report consecutivi faranno scattare l'espulsione immediata dalla rete sul tuo worker
    for _ in range(3):
        try:
            requests.post(f"{WORKER_URL}/api/report?id={ad_id}", timeout=5)
        except:
            pass
        time.sleep(0.5)

def analyze_batch(ads_batch, provider):
    """Analizza il lotto con l'AI scelta, usando chiamate REST a prova di crash"""
    
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

    print(f"🧠 Inviando batch a {provider.upper()} tramite API REST Diretta...")
    
    response_text = ""
    
    try:
        if provider == 'gemini':
            # Fallback a cascata per i modelli Gemini (se uno va in 404, prova il successivo)
            models_to_try = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-pro"]
            success = False
            
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                
                res = requests.post(url, json=payload, timeout=20)
                
                if res.status_code == 200:
                    response_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                    success = True
                    break
                elif res.status_code == 404:
                    print(f"⚠️ Modello Gemini {model_name} non trovato (404), switch al modello successivo...")
                    continue
                else:
                    print(f"❌ Errore Gemini API ({res.status_code}): {res.text}")
                    break
            
            if not success:
                return {}

        elif provider == 'grok':
            # Fallback a cascata per i modelli Grok (se uno va in Model Not Found, prova il successivo)
            models_to_try = ["grok-2-latest", "grok-4.3", "grok-3", "grok-2"]
            success = False
            headers = {"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"}
            
            for model_name in models_to_try:
                payload = {"model": model_name, "messages": [{"role": "user", "content": prompt}]}
                res = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload, timeout=20)
                
                if res.status_code == 200:
                    response_text = res.json()['choices'][0]['message']['content']
                    success = True
                    break
                elif res.status_code == 400 and ("Model not found" in res.text or "invalid-argument" in res.text):
                    print(f"⚠️ Modello Grok '{model_name}' deprecato o non trovato, switch al modello successivo...")
                    continue
                else:
                    print(f"❌ Errore Grok API ({res.status_code}): {res.text}")
                    break
                    
            if not success:
                return {}
                
    except Exception as e:
        print(f"❌ Errore Connessione di rete con {provider}: {e}")
        return {}

    # Motore di Parsing: estrae la decisione dell'AI anche se ci mette parole in più
    results = {}
    for ad in ads_batch:
        ad_id = ad['id']
        # Regex che cerca "[ID] -> PASS" o "[ID] : FLAG"
        match = re.search(rf"{ad_id}\s*(?:->|:|-)?\s*(FLAG|PASS)(.*)", response_text, re.IGNORECASE)
        if match:
            status = match.group(1).upper()
            reason = match.group(2).strip(" :->") if status == "FLAG" else ""
            results[ad_id] = {"status": status, "reason": reason}
        else:
            # Se l'AI ha ignorato questo annuncio, lo segniamo PASS per non fare danni, e verrà rivalutato.
            results[ad_id] = {"status": "PASS", "reason": ""}
            
    return results

def run_sentinel():
    ads = get_ads_from_server()
    if not ads:
        print("📭 Nessun annuncio trovato nella rete. Esco.")
        return

    history = load_history()
    current_time = time.time()
    
    # 🧠 INTELLIGENZA DEL REGISTRO: Ordiniamo gli annunci in base a quando sono stati controllati.
    # Chi non è nel file history.json otterrà il valore 0 e sarà messo in cima alla lista (Priorità Massima).
    ads.sort(key=lambda x: history.get(x['id'], 0))
    
    available_ais = []
    if GEMINI_API_KEY: available_ais.append('gemini')
    if GROK_API_KEY: available_ais.append('grok')
    
    if not available_ais:
        print("❌ Nessuna API Key configurata nei Secrets di GitHub. Sentinel disattivato.")
        return

    # Controlliamo un massimo di 50 annunci per ogni avvio (5 richieste AI, costo praticamente ZERO)
    max_ads_to_check = 50 
    ads_to_check = ads[:max_ads_to_check]
    batches = [ads_to_check[i:i + BATCH_SIZE] for i in range(0, len(ads_to_check), BATCH_SIZE)]
    
    print(f"🔍 Sentinel attivato: Analisi di {len(ads_to_check)} annunci in {len(batches)} batch.")
    
    for batch in batches:
        # Sceglie a caso tra Gemini e Grok per variare l'intelligenza di controllo
        chosen_ai = random.choice(available_ais)
        results = analyze_batch(batch, chosen_ai)
        
        for ad in batch:
            ad_id = ad['id']
            res = results.get(ad_id)
            
            if res and res['status'] == "FLAG":
                flag_ad(ad_id, res['reason'])
            
            # Aggiorna il timestamp nel registro: "Controllato oggi!"
            history[ad_id] = current_time
            
        time.sleep(2) # Pausa di rispetto per non saturare i limiti gratuiti delle AI
        
    save_history(history)
    print("✅ Controllo completato con successo. Registro memoria aggiornato.")

if __name__ == "__main__":
    run_sentinel()
