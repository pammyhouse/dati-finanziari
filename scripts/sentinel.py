import os
import json
import time
import requests
import base64
import tempfile
import cv2
import sys

# ==========================
# CONFIGURATION - GITHUB SECRETS
# ==========================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"

# Le credenziali vengono lette in modo sicuro dalle variabili d'ambiente
SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY")
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")

if not all([SENTINEL_SECRET_KEY, CF_ACCOUNT_ID, CF_API_TOKEN]):
    print("❌ ERRORE CRITICO: Credenziali mancanti. Assicurati di aver configurato i GitHub Secrets.")
    sys.exit(1)

# Modelli Cloudflare
VISION_MODEL = "@cf/meta/llama-3.2-11b-vision-instruct"
TEXT_MODEL = "@cf/meta/llama-3.1-8b-instruct"

print("🤖 Avvio AdSwap Sentinel AI...")

# ==========================
# HELPER: CLOUDFLARE AI
# ==========================
def ask_cloudflare_ai(text_prompt, base64_images=None):
    if base64_images:
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{VISION_MODEL}"
        content = []
        # Aggiungiamo tutte le immagini (se video, saranno 3 frame)
        for b64_img in base64_images:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}})
        content.append({"type": "text", "text": text_prompt})
    else:
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{TEXT_MODEL}"
        content = text_prompt

    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messages": [
            {
                "role": "system",
                "content": "You are a strict and highly accurate advertising moderation AI. You must analyze the ad content (text, URL, and images if provided). Flag the ad if it contains or promotes: NSFW (nudity, pornography), illegal drugs, weapons, graphic violence, malware, phishing, or obvious scams. Otherwise, pass it. You must reply ONLY with a valid JSON in this exact format: {\"status\": \"PASS\" or \"FLAG\", \"reason\": \"Brief explanation\"}. Do not add markdown blocks or any other text."
            },
            {
                "role": "user",
                "content": content
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        res_json = response.json()
        
        if response.status_code == 200 and res_json.get("success"):
            ai_response = res_json["result"]["response"]
            # Puliamo eventuali markdown residui (es. ```json ... ```) restituiti dall'AI
            clean_json = ai_response.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        else:
            print(f"❌ Errore API Cloudflare: {response.text}")
            return {"status": "FLAG", "reason": "AI_API_ERROR"}
    except Exception as e:
        print(f"❌ Errore di connessione o Parsing JSON dell'AI: {e}")
        return {"status": "FLAG", "reason": "PARSE_ERROR"}

# ==========================
# MEDIA PROCESSING
# ==========================
def extract_frames_base64(media_url):
    """Scarica il file e, se immagine restituisce 1 frame base64, se video restituisce 3 frame."""
    try:
        res = requests.get(media_url, timeout=15)
        if res.status_code != 200:
            return None

        ext = ".jpg"
        if "mp4" in res.headers.get("Content-Type", "").lower() or media_url.endswith(".mp4"):
            ext = ".mp4"

        # Salva in un file temporaneo
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(res.content)
            tmp_path = tmp.name

        base64_frames = []

        if ext == ".mp4":
            vid = cv2.VideoCapture(tmp_path)
            total_frames = int(vid.get(cv2.CAP_PROP_FRAME_COUNT))
            # Prendiamo 3 frame significativi dal video
            frame_indices = [int(total_frames * 0.1), int(total_frames * 0.5), int(total_frames * 0.9)]
            
            for idx in frame_indices:
                vid.set(cv2.CAP_PROP_POS_FRAMES, idx)
                success, frame = vid.read()
                if success:
                    # Rimpiccioliamo a 512x512 per risparmiare token ed evitare errori di Payload Size
                    frame = cv2.resize(frame, (512, 512), interpolation=cv2.INTER_AREA)
                    _, buffer = cv2.imencode('.jpg', frame)
                    base64_frames.append(base64.b64encode(buffer).decode('utf-8'))
            vid.release()
        else:
            # Immagine statica
            img = cv2.imread(tmp_path)
            if img is not None:
                img = cv2.resize(img, (512, 512), interpolation=cv2.INTER_AREA)
                _, buffer = cv2.imencode('.jpg', img)
                base64_frames.append(base64.b64encode(buffer).decode('utf-8'))

        os.remove(tmp_path)
        return base64_frames if base64_frames else None

    except Exception as e:
        print(f"⚠️ Errore processamento media: {e}")
        return None

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
    # Chiama l'API report 10 volte consecutive per farlo finire subito in stato 'Flagged' (necessari 3 report nel DB)
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

    print(f"🔍 Trovati {len(ads)} annunci 'pending' da revisionare.")

    for ad in ads:
        ad_id = ad["id"]
        print(f"\n⏳ Analisi annuncio: {ad.get('app_name')}...")

        text_prompt = f"App Name: {ad.get('app_name')}\nHeadline: {ad.get('headline')}\nDescription: {ad.get('description')}\nDestination URL: {ad.get('destination_url')}"

        base64_images = None
        if ad.get("media_url"):
            base64_images = extract_frames_base64(ad["media_url"])

        # Chiama l'Intelligenza Artificiale di Cloudflare
        ai_verdict = ask_cloudflare_ai(text_prompt, base64_images)

        if ai_verdict.get("status") == "PASS":
            approve_ad(ad_id)
        else:
            reason = ai_verdict.get("reason", "Violazione Sconosciuta o non determinabile.")
            flag_ad(ad_id, reason)

    print("\n🏁 Revisione automatica completata.")

if __name__ == "__main__":
    run_sentinel()
