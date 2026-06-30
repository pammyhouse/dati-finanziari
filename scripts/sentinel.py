import os
import json
import time
import requests
import random
import re
import tempfile
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

# ==========================================
# MOTORE 1: ANALISI SOLO TESTO (IN BATCH)
# ==========================================
def analyze_text_batch(ads_batch, provider):
    prompt = """You are a strict Trust & Safety AI Sentinel. Analyze this batch of ads.
Rules for FLAG: NSFW/Porn, Violence, Scams, Malware, Phishing or Illegal activities.
For each ad, you MUST reply with exactly this format on a new line:
[ID] -> PASS
or
[ID] -> FLAG: [Brief Reason]

Here is the batch to check:
"""
    for ad in ads_batch:
        prompt += f"\n--- ID: {ad['id']}\nHeadline: {ad.get('headline','')}\nDesc: {ad.get('description','')}\nURL: {ad.get('destination_url','')}\n"

    print(f"🧠 [TESTO] Inviando batch a {provider.upper()}...")
    response_text = ""
    
    try:
        if provider == 'groq':
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                response_text = res.json()['choices'][0]['message']['content']
            else:
                return None

        elif provider == 'gemini':
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model='gemini-2.5-flash', 
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            response_text = response.text
                
    except Exception as e:
        print(f"❌ Errore rete con {provider}: {e}")
        return None

    if not response_text: return None

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

# ==========================================
# MOTORE 2: ANALISI MULTIMEDIALE (SINGOLA)
# ==========================================
def analyze_multimedia_ad(ad):
    """Scarica il media e lo invia a Gemini insieme ai testi dell'annuncio."""
    print(f"🖼️ [MEDIA] Inizio analisi multimodale per ID: {ad['id']}")
    
    media_url = ad.get('media_url')
    if not media_url: return None

    # 1. Scarica il file in una cartella temporanea sicura
    try:
        res = requests.get(media_url, timeout=10)
        if res.status_code != 200:
            print(f"⚠️ Impossibile scaricare il media per {ad['id']}.")
            return None # Ritorna None così non viene segnato come controllato
    except:
        return None

    # Salva il file localmente
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.write(res.content)
    temp_file.close()

    try:
        # 2. Carica il file su Google Gemini
        client = genai.Client(api_key=GEMINI_API_KEY)
        uploaded_file = client.files.upload(file=temp_file.name)
        
        # Se è un video, diamo 2 secondi a Gemini per processarlo lato server
        if "video" in res.headers.get("Content-Type", "") or media_url.endswith(".mp4"):
            time.sleep(2)

        # 3. Chiedi a Gemini di analizzare TUTTO (File + Testo)
        prompt = f"""You are a strict Trust & Safety AI Sentinel.
Analyze the attached media file AND the following text associated with it.
Rules for FLAG: NSFW/Porn, Violence, Scams, Malware, Phishing or Illegal activities.

Ad Headline: {ad.get('headline','')}
Ad Description: {ad.get('description','')}
Destination URL: {ad.get('destination_url','')}

Reply EXACTLY with a single word "PASS" if everything is safe, or "FLAG: [Brief Reason]" if the media or text violate policies."""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(temperature=0.1)
        )
        
        # 4. Pulizia: Cancella il file dai server di Google
        try:
            client.files.delete(name=uploaded_file.name)
        except:
            pass

        response_text = response.text.strip().upper()
        
        if response_text.startswith("FLAG"):
            reason = response_text.replace("FLAG:", "").strip()
            return {"status": "FLAG", "reason": reason}
        else:
            return {"status": "PASS", "reason": ""}

    except Exception as e:
        print(f"❌ Errore durante l'analisi multimodale di {ad['id']}: {e}")
        return None
        
    finally:
        # Pulizia: Cancella il file dal server GitHub
        if os.path.exists(temp_file.name):
            os.remove(temp_file.name)

# ==========================================
# GESTORE CENTRALE
# ==========================================
def run_sentinel():
    if not GEMINI_API_KEY:
        print("❌ API Key GEMINI mancante! Obbligatoria per i controlli multimediali. Esco.")
        return

    ads = get_ads_from_server()
    if not ads:
        print("📭 Nessun annuncio trovato nella rete. Esco.")
        return

    history = load_history()
    current_time = time.time()
    
    # 🧠 ORDINAMENTO: I nuovi annunci (o quelli mai controllati) vengono prima.
    ads.sort(key=lambda x: history.get(x['id'], 0))
    
    # Limita a 40 annunci totali per non sforare i tempi di esecuzione
    ads_to_check = ads[:40] 
    
    # SEPARAZIONE DELLE CODE
    ads_text_only = [ad for ad in ads_to_check if not ad.get('media_url')]
    ads_with_media = [ad for ad in ads_to_check if ad.get('media_url')]
    
    print(f"🔍 Sentinel attivato. Da analizzare: {len(ads_text_only)} (Solo Testo), {len(ads_with_media)} (Con Media).")

    # --- FASE 1: GESTIONE CODA SOLO TESTO (Batch) ---
    if ads_text_only:
        available_ais = []
        if GROQ_API_KEY: available_ais.append('groq')
        available_ais.append('gemini')

        batches = [ads_text_only[i:i + BATCH_SIZE] for i in range(0, len(ads_text_only), BATCH_SIZE)]
        
        for batch in batches:
            for ai_provider in available_ais:
                results = analyze_text_batch(batch, ai_provider)
                if results is not None:
                    print(f"✅ Batch testo analizzato con {ai_provider.upper()}.")
                    for ad in batch:
                        res = results.get(ad['id'])
                        if res and res['status'] == "FLAG":
                            flag_ad(ad['id'], res['reason'])
                        # Salva in history solo se il controllo è andato a buon fine
                        if res: history[ad['id']] = current_time
                    break # Esce dal loop dei provider
            time.sleep(2)

    # --- FASE 2: GESTIONE CODA MULTIMEDIALE (Singoli) ---
    if ads_with_media:
        print("🎬 Inizio analisi annunci multimediali (Testo + Media)...")
        for ad in ads_with_media:
            res = analyze_multimedia_ad(ad)
            
            if res is not None:
                if res['status'] == "FLAG":
                    flag_ad(ad['id'], res['reason'])
                # L'annuncio viene segnato come controllato SOLO ORA, dopo che
                # Gemini ha letto contemporaneamente Testi + Video/Immagine.
                history[ad['id']] = current_time
            else:
                print(f"⚠️ Analisi fallita per {ad['id']}. Riproverò alla prossima esecuzione.")
                
            time.sleep(3) # Pausa tra un file multimediale e l'altro
            
    save_history(history)
    print("🏁 Controllo completato. Registro aggiornato.")

if __name__ == "__main__":
    import sys
    try:
        run_sentinel()
    except Exception as e:
        print(f"❌ Errore critico finale: {e}")
        sys.exit(1)
