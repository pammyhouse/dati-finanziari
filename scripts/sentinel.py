import os
import json
import time
import requests
import random
import re
import tempfile
import sys
import hashlib
from google import genai
from google.genai import types

# ==========================================
# CONFIGURAZIONI E VARIABILI D'AMBIENTE
# ==========================================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY") 
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

def get_ad_hash(ad):
    content = f"{ad.get('headline', '')}{ad.get('description', '')}{ad.get('media_url', '')}{ad.get('destination_url', '')}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_ads_from_server():
    if not SENTINEL_SECRET_KEY:
        print("❌ SENTINEL_KEY non configurata. Accesso negato.")
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
# PROMPT TUNING: SEVERO MA TOLLERANTE SUL MARKETING
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

def analyze_text_batch(ads_batch, provider):
    prompt = POLICY_PROMPT + "\nHere is the batch of text-only ads to check:\n"
    for ad in ads_batch:
        prompt += f"\n--- ID: {ad['id']}\nHeadline: {ad.get('headline','')}\nDesc: {ad.get('description','')}\nURL: {ad.get('destination_url','')}\n"

    print(f"🧠 [TESTO + URL] Inviando batch a {provider.upper()}...")
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
                model='gemini-2.0-flash', 
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

def analyze_multimedia_ad(ad):
    print(f"🖼️ [MEDIA + URL] Inizio analisi per ID: {ad['id']}")
    
    media_url = ad.get('media_url')
    if not media_url: return None

    try:
        res = requests.get(media_url, timeout=10)
        if res.status_code != 200:
            print(f"⚠️ Impossibile scaricare il media per {ad['id']}.")
            return None
            
        mime_type = res.headers.get("Content-Type") or ""
        ext = '.jpg' 
        if 'png' in mime_type.lower(): ext = '.png'
        elif 'gif' in mime_type.lower(): ext = '.gif'
        elif 'mp4' in mime_type.lower() or media_url.endswith('.mp4'): ext = '.mp4'
        elif 'webp' in mime_type.lower(): ext = '.webp'
            
    except Exception as e:
        print(f"❌ Errore download asset: {e}")
        return None

    temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    temp_file.write(res.content)
    temp_file.close()
    
    uploaded_file = None

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        uploaded_file = client.files.upload(file=temp_file.name)
        
        if ext == '.mp4':
            time.sleep(3) 

        prompt = POLICY_PROMPT + f"""
Here is the single multimedia ad content to review:
Ad Headline: {ad.get('headline','')}
Ad Description: {ad.get('description','')}
Destination URL: {ad.get('destination_url','')}

Reply EXACTLY with "PASS" if everything is safe, or "FLAG: [Reason]" if it violates the Tier-1 rules."""

        max_retries = 4
        delay = 15 
        
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=[uploaded_file, prompt],
                    config=types.GenerateContentConfig(temperature=0.1)
                )
                
                if not response or not response.text:
                    return {"status": "FLAG", "reason": "BLOCKED_BY_GOOGLE_SAFETY (Extreme Content Detected)"}
                
                response_text = response.text.strip().upper()
                
                if "FLAG" in response_text:
                    reason_match = re.search(r"FLAG\s*(?::|->)?\s*(.*)", response_text, re.IGNORECASE)
                    reason = reason_match.group(1).strip() if reason_match else "Policy Violation"
                    return {"status": "FLAG", "reason": reason}
                else:
                    return {"status": "PASS", "reason": ""}
                    
            except Exception as e:
                err_msg = str(e).upper()
                if any(x in err_msg for x in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"]):
                    if attempt < max_retries - 1:
                        print(f"🕒 Sovraccarico server o rate limit Google. Attendo {delay}s e riprovo...")
                        time.sleep(delay)
                        delay *= 2
                        continue
                
                print(f"❌ Errore API Gemini Multimodale per {ad['id']}: {e}")
                return None
                
        return None 
        
    finally:
        if uploaded_file:
            try: client.files.delete(name=uploaded_file.name)
            except: pass
        if os.path.exists(temp_file.name):
            os.remove(temp_file.name)

def run_sentinel():
    if not GEMINI_API_KEY:
        print("❌ API Key GEMINI mancante! Esco.")
        return

    ads = get_ads_from_server()
    if not ads:
        print("📭 Nessun annuncio trovato nel database globale. Esco.")
        return

    history = load_history()
    current_time = time.time()
    
    ads_to_check = []
    for ad in ads:
        ad_hash = get_ad_hash(ad)
        if ad_hash not in history:
            ad['hash_signature'] = ad_hash 
            ads_to_check.append(ad)

    if not ads_to_check:
        print("✅ Tutti gli annunci sono puliti e già stati verificati.")
        sys.exit(0)

    random.shuffle(ads_to_check)
    ads_to_check = ads_to_check[:30] 
    
    ads_text_only = [ad for ad in ads_to_check if not ad.get('media_url')]
    ads_with_media = [ad for ad in ads_to_check if ad.get('media_url')]
    
    print(f"🔍 Sentinel attivato. Da analizzare: {len(ads_text_only)} (Solo Testo), {len(ads_with_media)} (Con Media).")

    if ads_text_only:
        available_ais = []
        if GROQ_API_KEY: available_ais.append('groq')
        available_ais.append('gemini')

        batches = [ads_text_only[i:i + BATCH_SIZE] for i in range(0, len(ads_text_only), BATCH_SIZE)]
        
        for batch in batches:
            for ai_provider in available_ais:
                results = analyze_text_batch(batch, ai_provider)
                if results is not None:
                    print(f"✅ Batch testo/URL analizzato con {ai_provider.upper()}.")
                    for ad in batch:
                        res = results.get(ad['id'])
                        if res and res['status'] == "FLAG":
                            flag_ad(ad['id'], res['reason'])
                        if res: history[ad['hash_signature']] = current_time
                    break 
            time.sleep(2)

    if ads_with_media:
        print("🎬 Inizio analisi annunci multimediali (Testo + Media + URL)...")
        for ad in ads_with_media:
            res = analyze_multimedia_ad(ad)
            
            if res is not None:
                if res['status'] == "FLAG":
                    flag_ad(ad['id'], res['reason'])
                history[ad['hash_signature']] = current_time
            else:
                print(f"⚠️ Analisi fallita per {ad['id']}. Riproverò alla prossima esecuzione.")
                
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
