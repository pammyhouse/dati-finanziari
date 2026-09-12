import os
import json
import time
import requests
import re
import sys
import tempfile

import cv2  # opencv-python-headless

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

MAX_ADS_PER_RUN = 20

TEXT_MODEL = "@cf/meta/llama-3.1-8b-instruct"
VISION_MODEL = "@cf/meta/llama-3.2-11b-vision-instruct"

# ==========================
# IL NUOVO CERVELLO LEGALE (SCUDO ANTI-TRUFFA E ANTI-FALSI POSITIVI)
# ==========================
# ==========================
# IL NUOVO CERVELLO LEGALE (SCUDO ANTI-TRUFFA E ANTI-FALSI POSITIVI)
# ==========================
MODERATION_SYSTEM_PROMPT = (
    "You are the Chief Legal & Moderation AI for a global mobile advertising network. "
    "Your objective is to shield the network from extreme illegal liabilities (FTC/SEC violations, CP, malware) "
    "while being explicitly tolerant of weird, indie, religious, or edgy content.\n\n"
    
    "🛑 1. SEVERE VIOLATIONS (Leads to immediate account ban):\n"
    "Label severity as 'SEVERE' ONLY for:\n"
    "- Explicit, graphic pornography or non-consensual sexual content.\n"
    "- Actual, malicious malware or phishing links attempting to steal passwords/CC info.\n"
    "- Sale of illegal drugs, unregulated weapons, or promotion of terrorism.\n"
    "- Extremely deceptive financial scams (e.g., 'Guaranteed 500% ROI in 1 day').\n\n"
    
    "⚠️ 2. MINOR VIOLATIONS (Ad is rejected, but account is safe):\n"
    "Label severity as 'MINOR' for:\n"
    "- Political campaigning, controversial social opinions, or deepfakes of living politicians.\n"
    "- Annoying spam, completely gibberish text, or broken/invalid URLs.\n"
    "- Highly blurry, glitched, or unreadable media.\n"
    "- Vague 'get-rich' courses or ambiguous weight-loss supplements that bend the rules but aren't strictly illegal scams.\n"
    "- 'Simulated' system warnings (e.g., 'Your storage is full' for a cleaner app) - these violate policies but are NOT severe malware.\n"
    "- WHEN IN DOUBT or if the context is unclear, you MUST REJECT with MINOR severity and request more info.\n\n"
    
    "✅ 3. FALSE POSITIVES (MUST PASS):\n"
    "DO NOT reject these. They are 100% allowed:\n"
    "- Religious, spiritual, or cultural content (e.g., monks, incense, prayers, tarot, astrology).\n"
    "- Humor, sarcasm, and meme-style ads.\n"
    "- Fantasy/Gaming violence (swords, cartoon guns, explosions in video games).\n"
    "- Simulated casino games (slots/poker) where NO REAL MONEY is bet or won (virtual coins only).\n"
    "- Standard financial tools (budget apps, crypto trackers) with no deceptive promises.\n\n"
    
    "Classify using two fields:\n"
    "1) status: \"PASS\" if safe; \"REJECT\" if there is a violation or you are unsure.\n"
    "2) severity: \"SEVERE\" (ONLY for strictly illegal/malicious content from Rule 1); \"MINOR\" (for Rule 2, policy violations, or uncertainty); \"NONE\" (if PASS).\n"
    "Reply ONLY with a valid JSON in this exact format: "
    "{\"status\": \"PASS\" or \"REJECT\", \"severity\": \"SEVERE\" or \"MINOR\" or \"NONE\", \"reason\": \"Brief, objective explanation if rejected. If uncertain, state 'Needs manual review'.\"}. Do not write any other text."
)

print("🤖 Avvio AdSwap Sentinel AI (Legal Compliance Mode)...")

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
            + "\n\nAd context (for reference only, verify the image against policies): "
            + text_context
        )
    }
    return _call_and_parse(url, headers, payload)

def _call_and_parse(url, headers, payload):
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45)

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
    return {"status": status, "severity": severity, "reason": v.get("reason", "Policy violation.")}

# ==========================
# HELPER: MEDIA (IMMAGINE / FRAME VIDEO)
# ==========================
def fetch_media_bytes(media_url):
    if not media_url:
        return None
    try:
        raw = requests.get(media_url, timeout=20).content
        is_video = media_url.lower().endswith(".mp4")

        with tempfile.NamedTemporaryFile(suffix=".mp4" if is_video else ".jpg") as tmp_f:
            tmp_f.write(raw)
            tmp_f.flush()

            if is_video:
                cap = cv2.VideoCapture(tmp_f.name)
                fps = cap.get(cv2.CAP_PROP_FPS) or 0
                if fps > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps))
                success, frame = cap.read()
                cap.release()
                if not success:
                    return None
                img = frame
            else:
                img = cv2.imread(tmp_f.name)
                if img is None:
                    return None

            img = cv2.resize(img, (400, 400), interpolation=cv2.INTER_AREA)
            ok, encoded = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            return encoded.tobytes() if ok else None
    except Exception as e:
        print(f"⚠️ Impossibile estrarre o comprimere il media per l'analisi visiva: {e}")
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
    print(f"🚨 SEGNALATO (contenuto grave, innesca sospensione account): {ad_id}")
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
            print("⛔ Budget neuroni Cloudflare esaurito per oggi. Interrompo il run.")
            break
        if text_verdict["status"] == "ERROR":
            print(f"⏭️  Salto per errore infrastrutturale ({text_verdict['reason']}).")
            processed += 1
            continue

        media_bytes = fetch_media_bytes(ad.get("media_url"))
        vision_verdict = None
        
        if media_bytes:
            vision_verdict = ask_cloudflare_vision(media_bytes, text_prompt)
            
            if vision_verdict["status"] == "QUOTA_EXCEEDED":
                print("⛔ Budget neuroni Cloudflare esaurito (vision). Interrompo il run.")
                break
            if vision_verdict["status"] == "ERROR":
                print(f"⚠️ Analisi visiva non riuscita ({vision_verdict['reason']}), procedo solo con il testo.")
                vision_verdict = None

        verdicts = [v for v in [text_verdict, vision_verdict] if v is not None]
        final_reject = any(v["status"] == "REJECT" for v in verdicts)

        if not final_reject:
            approve_ad(ad_id)
        else:
            # Raccogliamo la severità più alta
            is_severe = any(v["severity"] == "SEVERE" for v in verdicts)
            reasons = [v["reason"] for v in verdicts if v["status"] == "REJECT"]
            combined_reason = " | ".join(dict.fromkeys(reasons))

            # Lo rifiutiamo sulla dashboard mettendoci il motivo testuale
            reject_ad(ad_id, combined_reason)
            
            # SE E SOLO SE l'infrazione è gravissima (pornografia, truffe finanziarie esplicite, phishing)
            # invochiamo la funzione flag_ad che fa bannare temporaneamente l'utente
            if is_severe:
                flag_ad(ad_id)

        processed += 1

    print(f"\n🏁 Revisione automatica completata. Annunci processati in questo run: {processed}.")

if __name__ == "__main__":
    run_sentinel()
