import os
import json
import time
import requests
import re
import sys
import tempfile

import cv2  # opencv-python-headless: estrazione frame video senza dipendere da ffmpeg di sistema

# ==========================
# CONFIGURATION - SECRETS & LIMITS
# ==========================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"

SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY")
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")

if not all([SENTINEL_SECRET_KEY, CF_ACCOUNT_ID, CF_API_TOKEN]):
    print("❌ ERRORE CRITICO: Credenziali mancanti. Assicurati di aver configurato i GitHub Secrets.")
    sys.exit(1)

# Tetto "morbido" per run: non e' la vera protezione (quella e' il rilevamento
# del quota-exceeded qui sotto), mette solo un limite di buon senso a quante
# richieste HTTP il job puo' fare in un singolo minuto, girando ogni ora.
MAX_ADS_PER_RUN = 20

TEXT_MODEL = "@cf/meta/llama-3.1-8b-instruct"
# Vision: consumato via Cloudflare Workers AI come servizio -> non soggetto alla
# clausola Meta che esclude gli sviluppatori con sede in UE che eseguono
# direttamente i pesi del modello (quella clausola non vale per chi consuma il
# modello come API di terzi). Fai comunque lo step di "agree" una tantum
# sul tuo account prima del primo utilizzo.
VISION_MODEL = "@cf/meta/llama-3.2-11b-vision-instruct"

MODERATION_SYSTEM_PROMPT = (
    "You are a strict advertising moderation AI. Analyze the provided ad content "
    "(and image, if present). Classify it using two fields:\n"
    "1) status: \"PASS\" if the ad is a normal, safe advertisement; \"REJECT\" otherwise.\n"
    "2) severity: only meaningful when status is REJECT. Use \"SEVERE\" ONLY for content that is "
    "NSFW/pornographic, depicts or promotes illegal drugs, weapons, graphic violence, malware, phishing, "
    "scams, or any illegal activity. Use \"MINOR\" for anything else that still fails review "
    "(e.g. misleading claims, broken/suspicious destination, poor quality, unclear branding, "
    "unlabeled AI-generated content, unrelated or low-effort creative).\n"
    "Reply ONLY with a valid JSON in this exact format: "
    "{\"status\": \"PASS\" or \"REJECT\", \"severity\": \"SEVERE\" or \"MINOR\" or \"NONE\", "
    "\"reason\": \"Brief explanation\"}. Do not write any other text."
)

print("🤖 Avvio AdSwap Sentinel AI...")


# ==========================
# HELPER: CLOUDFLARE AI (TESTO)
# ==========================
def ask_cloudflare_text(text_prompt):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{TEXT_MODEL}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messages": [
            {"role": "system", "content": MODERATION_SYSTEM_PROMPT},
            {"role": "user", "content": text_prompt}
        ]
    }
    return _call_and_parse(url, headers, payload)


# ==========================
# HELPER: CLOUDFLARE AI (VISION)
# ==========================
def ask_cloudflare_vision(image_bytes, text_context):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{VISION_MODEL}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "image": list(image_bytes),
        "prompt": (
            MODERATION_SYSTEM_PROMPT
            + "\n\nAd context (for reference only, judge mainly the image): "
            + text_context
        )
    }
    return _call_and_parse(url, headers, payload)


def _call_and_parse(url, headers, payload):
    """Ritorna sempre un dict con 'status' in {PASS, REJECT, ERROR, QUOTA_EXCEEDED}."""
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45)

        # Rilevamento budget neuroni esaurito: Cloudflare risponde 429, oppure
        # 200 con success=false e un messaggio d'errore che menziona il limite.
        if response.status_code == 429:
            return {"status": "QUOTA_EXCEEDED", "severity": "NONE", "reason": "HTTP 429"}

        res_json = response.json()

        if not res_json.get("success", False):
            errors_blob = json.dumps(res_json.get("errors", [])).lower()
            if "limit" in errors_blob or "quota" in errors_blob or "exceeded" in errors_blob:
                return {"status": "QUOTA_EXCEEDED", "severity": "NONE", "reason": errors_blob}
            print(f"❌ Errore API Cloudflare: {response.text}")
            return {"status": "ERROR", "severity": "NONE", "reason": "AI_API_ERROR"}

        ai_response = res_json["result"]["response"]
        if isinstance(ai_response, dict):
            return _normalize_verdict(ai_response)

        json_match = re.search(r'\{.*\}', ai_response.replace('\n', ''), re.DOTALL)
        if json_match:
            return _normalize_verdict(json.loads(json_match.group(0)))
        return {"status": "ERROR", "severity": "NONE", "reason": "AI did not return valid JSON format."}

    except Exception as e:
        print(f"❌ Errore di connessione o Parsing: {e}")
        return {"status": "ERROR", "severity": "NONE", "reason": "NETWORK_ERROR"}


def _normalize_verdict(v):
    status = v.get("status", "REJECT")
    if status not in ("PASS", "REJECT"):
        status = "REJECT"
    severity = v.get("severity", "NONE")
    if severity not in ("SEVERE", "MINOR", "NONE"):
        severity = "MINOR" if status == "REJECT" else "NONE"
    return {"status": status, "severity": severity, "reason": v.get("reason", "Violazione policy.")}


# ==========================
# HELPER: MEDIA (IMMAGINE / FRAME VIDEO)
# ==========================
def fetch_media_bytes(media_url):
    """Scarica il media; se e' un video, estrae un frame con OpenCV. Ritorna bytes JPEG o None."""
    if not media_url:
        return None
    try:
        raw = requests.get(media_url, timeout=20).content
        is_video = media_url.lower().endswith(".mp4")

        if not is_video:
            return raw

        with tempfile.NamedTemporaryFile(suffix=".mp4") as vid_f:
            vid_f.write(raw)
            vid_f.flush()

            cap = cv2.VideoCapture(vid_f.name)
            # Prova a saltare ~1 secondo per evitare fotogrammi neri iniziali
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            if fps > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps))
            success, frame = cap.read()
            cap.release()

            if not success:
                return None

            ok, encoded = cv2.imencode(".jpg", frame)
            return encoded.tobytes() if ok else None
    except Exception as e:
        print(f"⚠️ Impossibile estrarre il media per l'analisi visiva: {e}")
        return None


# ==========================
# ACTIONS
# ==========================
def approve_ad(ad_id):
    print(f"✅ APPROVATO: {ad_id}")
    try:
        requests.post(f"{WORKER_URL}/api/admin/creatives/approve?id={ad_id}",
                       headers={"X-Sentinel-Key": SENTINEL_SECRET_KEY}, timeout=10)
    except Exception:
        pass


def reject_ad(ad_id, reason):
    print(f"🛑 RIFIUTATO ({reason}): {ad_id}")
    try:
        requests.post(f"{WORKER_URL}/api/admin/creatives/reject",
                       headers={"X-Sentinel-Key": SENTINEL_SECRET_KEY, "Content-Type": "application/json"},
                       json={"id": ad_id, "reason": reason}, timeout=10)
    except Exception:
        pass


def flag_ad(ad_id):
    print(f"🚨 SEGNALATO (contenuto grave): {ad_id}")
    for _ in range(10):
        try:
            requests.post(f"{WORKER_URL}/api/report?id={ad_id}", timeout=5)
            time.sleep(0.2)
        except Exception:
            pass


# ==========================
# MAIN LOOP
# ==========================
def run_sentinel():
    headers = {"X-Sentinel-Key": SENTINEL_SECRET_KEY}

    try:
        res = requests.get(f"{WORKER_URL}/api/admin/creatives/pending", headers=headers, timeout=20)
        ads = res.json()
    except Exception as e:
        print(f"❌ Errore di connessione al Worker: {e}")
        return

    if not ads:
        print("📭 Nessun annuncio in coda di revisione. Termino.")
        return

    queue = ads[:MAX_ADS_PER_RUN]
    print(f"🔍 Trovati {len(ads)} annunci pending. Analizzo fino a {len(queue)} in questo run...")

    processed = 0
    for ad in queue:
        ad_id = ad["id"]
        print(f"\n⏳ [{processed + 1}/{len(queue)}] Analisi annuncio: {ad.get('app_name')}...")

        text_prompt = (
            f"App Name: {ad.get('app_name')}\n"
            f"Headline: {ad.get('headline')}\n"
            f"Description: {ad.get('description')}\n"
            f"Destination URL: {ad.get('destination_url')}"
        )

        text_verdict = ask_cloudflare_text(text_prompt)

        if text_verdict["status"] == "QUOTA_EXCEEDED":
            print("⛔ Budget neuroni Cloudflare esaurito per oggi. Interrompo il run: "
                  "gli annunci restanti verranno ripresi al prossimo giro orario.")
            break

        if text_verdict["status"] == "ERROR":
            print(f"⏭️  Salto per errore infrastrutturale ({text_verdict['reason']}), riproverò più tardi.")
            processed += 1
            continue

        media_bytes = fetch_media_bytes(ad.get("media_url"))
        vision_verdict = None
        if media_bytes:
            vision_verdict = ask_cloudflare_vision(media_bytes, text_prompt)
            if vision_verdict["status"] == "QUOTA_EXCEEDED":
                print("⛔ Budget neuroni Cloudflare esaurito per oggi (durante l'analisi vision). "
                      "Interrompo il run.")
                break
            if vision_verdict["status"] == "ERROR":
                print(f"⚠️ Analisi visiva non riuscita ({vision_verdict['reason']}), procedo solo con il testo.")
                vision_verdict = None

        verdicts = [v for v in [text_verdict, vision_verdict] if v is not None]
        final_reject = any(v["status"] == "REJECT" for v in verdicts)

        if not final_reject:
            approve_ad(ad_id)
        else:
            severe_hits = [v for v in verdicts if v["status"] == "REJECT" and v["severity"] == "SEVERE"]
            reasons = [v["reason"] for v in verdicts if v["status"] == "REJECT"]
            combined_reason = " | ".join(dict.fromkeys(reasons))

            reject_ad(ad_id, combined_reason)
            if severe_hits:
                flag_ad(ad_id)

        processed += 1

    print(f"\n🏁 Revisione automatica completata. Annunci processati in questo run: {processed}.")


if __name__ == "__main__":
    run_sentinel()
