import os
import json
import time
import requests
import random
import re
import tempfile
import sys
import hashlib
import google.generativeai as genai  # Utilizzo dell'SDK stabile per la quota 1500/day

# ==========================================
# CONFIGURAZIONI E VARIABILI D'AMBIENTE
# ==========================================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY") 
HISTORY_FILE = "checked_ads.json"
BATCH_SIZE = 10

# Inizializzazione stabile di Google Gemini 1.5
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

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

def get_ad_hash(ad):
    """Genera l'impronta digitale dell'ad. Se cambiano testo o media, l'hash cambia e viene ricontrollato."""
    content = f"{ad.get('headline', '')}{ad.get('description', '')}{ad.get('media_url', '')}{ad.get('destination_url', '')}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_ads_from_server():
    if not SENTINEL_SECRET_KEY:
        print("❌ SENTINEL_KEY non configurata nei secrets. Accesso totale negato.")
        return []

    print("📡 Download TOTALE annunci dal server (Bypass crediti/sospensioni)...")
    headers = {"X-Sentinel-Key": SENTINEL_SECRET_KEY}
    try:
        res = requests.get(f"{WORKER_URL}/api/admin/serve_all", headers=headers, timeout=20)
        if res.status_code == 200:
            return res.json().get('ads', [])
        else:
            print(f"❌ Errore Autorizzazione Worker: {res.status_code}")
            return []
    except Exception as e:
        print(f"❌ Errore connessione Cloudflare: {e}")
        return []

def flag_ad(ad_id, reason):
    print(f"🚨 AD FLAGGATO! ID: {ad_id} | Motivo: {reason}")
    for _ in range(3):
        try:
            requests.post(f"{WORKER_URL}/api/report?id={ad_id}", timeout=5)
        except:
            pass
        time.sleep(0.5)

# ==========================================
# PROMPT TUNING: SEVERO MA TOLLERANTE
# ==========================================
POLICY_PROMPT = """You are a Trust & Safety AI Sentinel. 
Your ONLY job is to catch SEVERE Tier-1 violations. DO NOT act as a strict marketing compliance officer.

CRITICAL SECURITY RULES (YOU MUST FLAG THESE):
1. NSFW/PORN: Explicit adult content, pornography, nudity.
2. ILLEGAL: Weapons, illegal drugs, severe violence, gore.
3. SEVERE MALWARE/PHISHING: Destination URLs containing highly malicious domains or blatant credential harvesting scams.

TOLERANCE RULES (YOU MUST PASS THESE - DO NOT FLAG):
- IGNORE aggressive marketing, clickbait, or hype (e.g., "Download now!", "Guaranteed returns", "Best app ever").
- IGNORE financial claims like "easy portfolio growth" or crypto trading promotions.
- IGNORE minor brand discrepancies (e.g., Image says brand X, text says brand Y).
- IGNORE poor grammar, typos, or low-quality visuals.
- If in doubt about a marketing tactic, PASS. Only FLAG if it's a clear Tier-1 security threat (Porn, Illegal, actual Malware).

For each ad, you MUST reply with exactly this format:
[ID] -> PASS
or
[ID] -> FLAG: [Brief Reason]
"""

# ==========================================
# MOTORE 1: ANALISI SOLO TESTO E URL (GROQ)
# ==========================================
def analyze_text_batch(ads_batch):
    prompt = POLICY_PROMPT + "\nHere is the batch of text-only ads to check:\n"
    for ad in ads_batch:
        prompt += f"\n--- ID: {ad['id']}\nHeadline: {ad.get('headline','')}\nDesc: {ad.get('description','')}\nURL: {ad.get('destination_url','')}\n"

    print("🧠 [TESTO + URL] Inviando batch a GROQ...")
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            response_text = res.json()['choices'][0]['message']['content']
        else:
            return None
    except:
        return None

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
# MOTORE 2: ANALISI MULTIMEDIALE + URL (IBRIDO)
# ==========================================
def analyze_multimedia_ad(ad):
    media_url = ad.get('media_url')
    if not media_url: return None

    try:
        res = requests.get(media_url, timeout=10)
        if res.status_code != 200: return None
        mime_type = res.headers.get("Content-Type") or ""
        
        ext = '.jpg' 
        if 'png' in mime_type.lower(): ext = '.png'
        elif 'gif' in mime_type.lower(): ext = '.gif'
        elif 'mp4' in mime_type.lower() or media_url.endswith('.mp4'): ext = '.mp4'
        elif 'webp' in mime_type.lower(): ext = '.webp'
    except:
        return None

    is_video = 'video' in mime_type or ext == '.mp4'
    single_ad_prompt = POLICY_PROMPT + f"\nHeadline: {ad.get('headline','')}\nDesc: {ad.get('description','')}\nURL: {ad.get('destination_url','')}\n"

    # --------------------------------------------------------
    # STRADA A: IMMAGINE -> GROQ VISION (Gratis, No limiti di 20)
    # --------------------------------------------------------
    if not is_video and GROQ_API_KEY:
        print(f"👁️ [GROQ VISION] Analisi immagine per ID: {ad['id']}")
        try:
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.2-11b-vision-preview",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": single_ad_prompt},
                        {"type": "image_url", "image_url": {"url": media_url}} # Passa l'URL pubblico direttamente
                    ]
                }],
                "temperature": 0.1
            }
            vision_res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
            if vision_res.status_code == 200:
                response_text = vision_res.json()['choices'][0]['message']['content'].strip().upper()
                if "FLAG" in response_text:
                    reason_match = re.search(r"FLAG\s*(?::|->)?\s*(.*)", response_text, re.IGNORECASE)
                    return {"status": "FLAG", "reason": reason_match.group(1).strip() if reason_match else "Policy Violation"}
                else:
                    return {"status": "PASS", "reason": ""}
            print(f"⚠️ Groq Vision Status {vision_res.status_code}. Fallback su Gemini...")
        except Exception as e:
            print(f"⚠️ Errore Groq Vision ({e}). Fallback su Gemini...")

    # --------------------------------------------------------
    # STRADA B: VIDEO O FALLBACK -> GEMINI 1.5 FLASH (1500 req/day)
    # --------------------------------------------------------
    if not GEMINI_API_KEY: return None
    print(f"🎥 [GEMINI 1.5 FLASH] Analisi multimodale per ID: {ad['id']}")

    temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    temp_file.write(res.content)
    temp_file.close()
    uploaded_file = None

    try:
        # Caricamento stabile tramite l'SDK classico
        uploaded_file = genai.upload_file(path=temp_file.name)
        if is_video: time.sleep(3)

        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content([uploaded_file, single_ad_prompt])
        
        if not response or not response.text:
            return {"status": "FLAG", "reason": "BLOCKED_BY_GOOGLE_SAFETY (Potential Adult/Extreme material)"}

        response_text = response.text.strip().upper()
        if "FLAG" in response_text:
            reason_match = re.search(r"FLAG\s*(?::|->)?\s*(.*)", response_text, re.IGNORECASE)
            return {"status": "FLAG", "reason": reason_match.group(1).strip() if reason_match else "Policy Violation"}
        return {"status": "PASS", "reason": ""}
    except Exception as e:
        print(f"❌ Errore Gemini 1.5 per {ad['id']}: {e}")
        return None
    finally:
        if uploaded_file:
            try: uploaded_file.delete()
            except: pass
        if os.path.exists(temp_file.name): os.remove(temp_file.name)

# ==========================================
# GESTORE PRINCIPALE
# ==========================================
def run_sentinel():
    ads = get_ads_from_server()
    if not ads:
        print("📭 Nessun annuncio trovato nel database globale.")
        sys.exit(0)

    history = load_history()
    current_time = time.time()
    
    ads_to_check = []
    for ad in ads:
        ad_hash = get_ad_hash(ad)
        if ad_hash not in history:
            ad['hash_signature'] = ad_hash 
            ads_to_check.append(ad)

    if not ads_to_check:
        print("✅ Tutti gli annunci in rete sono già stati verificati e non modificati.")
        sys.exit(0)

    random.shuffle(ads_to_check)
    ads_to_check = ads_to_check[:30] 
    
    ads_text_only = [ad for ad in ads_to_check if not ad.get('media_url')]
    ads_with_media = [ad for ad in ads_to_check if ad.get('media_url')]
    
    print(f"🔍 Sentinel attivato. Da analizzare: {len(ads_text_only)} (Solo Testo), {len(ads_with_media)} (Con Media).")

    if ads_text_only and GROQ_API_KEY:
        batches = [ads_text_only[i:i + BATCH_SIZE] for i in range(0, len(ads_text_only), BATCH_SIZE)]
        for batch in batches:
            results = analyze_text_batch(batch)
            if results is not None:
                print(f"✅ Batch testo/URL analizzato con GROQ.")
                for ad in batch:
                    res = results.get(ad['id'])
                    if res and res['status'] == "FLAG":
                        flag_ad(ad['id'], res['reason'])
                    if res: history[ad['hash_signature']] = current_time
            time.sleep(2)

    if ads_with_media:
        print("🎬 Inizio analisi annunci multimediali...")
        for ad in ads_with_media:
            res = analyze_multimedia_ad(ad)
            if res is not None:
                if res['status'] == "FLAG":
                    flag_ad(ad['id'], res['reason'])
                history[ad['hash_signature']] = current_time
            else:
                print(f"⚠️ Analisi fallita temporaneamente per {ad['id']}.")
            time.sleep(2)
            
    save_history(history)
    print("🏁 Controllo completato. Registro aggiornato.")
    sys.exit(0)

if __name__ == "__main__":
    try:
        run_sentinel()
    except Exception as e:
        print(f"❌ Errore critico finale: {e}")
        sys.exit(1)
