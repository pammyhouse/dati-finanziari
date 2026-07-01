import os
import json
import time
import requests
import random
import re
import tempfile
import sys
import hashlib
import cv2
from PIL import Image
import torch
from transformers import pipeline
from detoxify import Detoxify

# ==========================
# CONFIG
# ==========================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"
SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY")
HISTORY_FILE = "checked_ads.json"

# 🔥 stabilità CPU GitHub Actions
torch.set_num_threads(1)

print("⏳ Inizializzazione modelli AI locali...")

try:
    text_model = Detoxify('multilingual')

    image_model = pipeline(
        "image-classification",
        model="falconsai/nsfw_image_detection"
    )

    print("✅ Modelli pronti.")
except Exception as e:
    print(f"❌ Errore modelli: {e}")
    sys.exit(1)


# ==========================
# HISTORY
# ==========================
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
    content = f"{ad.get('headline','')}{ad.get('description','')}{ad.get('media_url','')}{ad.get('destination_url','')}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


# ==========================
# SERVER
# ==========================
def get_ads_from_server():
    if not SENTINEL_SECRET_KEY:
        print("❌ SENTINEL_KEY mancante")
        return []

    headers = {"X-Sentinel-Key": SENTINEL_SECRET_KEY}

    try:
        res = requests.get(
            f"{WORKER_URL}/api/admin/serve_all",
            headers=headers,
            timeout=20
        )

        if res.status_code == 200:
            return res.json().get("ads", [])

        print("❌ Worker error:", res.status_code, res.text)
        return []

    except Exception as e:
        print("❌ Connessione fallita:", e)
        return []


def flag_ad(ad_id, reason):
    print(f"🚨 FLAG {ad_id} -> {reason}")

    for _ in range(2):
        try:
            requests.post(
                f"{WORKER_URL}/api/report?id={ad_id}",
                timeout=5
            )
        except:
            pass
        time.sleep(0.3)


# ==========================
# URL SAFETY
# ==========================
def is_malicious_url(url):
    if not url:
        return False

    url = url.lower()

    bad_patterns = [
        ".xyz", ".zip", ".click", ".loan", ".top", ".win",
        "free-money", "hack", "crack", "casino", "bet", "phishing"
    ]

    return any(p in url for p in bad_patterns)


# ==========================
# TEXT ANALYSIS
# ==========================
def analyze_text(ad):
    url = ad.get("destination_url", "")
    text = f"{ad.get('headline','')} {ad.get('description','')}".strip()

    # 1. URL check
    if is_malicious_url(url):
        return {"status": "FLAG", "reason": "MALICIOUS_URL"}

    # 2. keyword minimal risk filter
    keywords = ["droga", "pistola", "cocaine", "guns", "sex", "xxx", "porn"]
    if any(k in text.lower() for k in keywords):
        return {"status": "FLAG", "reason": "ILLEGAL_KEYWORDS"}

    # 3. ML toxicity model
    try:
        res = text_model.predict(text)

        if (
            res.get("toxicity", 0) > 0.85 or
            res.get("sexual_explicit", 0) > 0.60 or
            res.get("threat", 0) > 0.75
        ):
            return {"status": "FLAG", "reason": "TOXIC_TEXT"}

    except Exception as e:
        print("⚠️ Detoxify error:", e)

    return {"status": "PASS", "reason": ""}


# ==========================
# IMAGE ANALYSIS
# ==========================
def analyze_image(file_path):
    try:
        img = Image.open(file_path)
        img.thumbnail((512, 512))

        result = image_model(img)

        scores = {r["label"]: r["score"] for r in result}

        # 🔥 soglia più aggressiva per ads
        nsfw_score = scores.get("nsfw", 0)

        if nsfw_score > 0.60:
            return True

        # fallback extra categorie (se presenti)
        if scores.get("porn", 0) > 0.40:
            return True

        return False

    except Exception as e:
        print("⚠️ Image error:", e)
        return False


# ==========================
# MULTIMEDIA ANALYSIS
# ==========================
def analyze_multimedia_ad(ad):
    media_url = ad.get("media_url")

    # sempre text-first
    text_res = analyze_text(ad)
    if text_res["status"] == "FLAG":
        return text_res

    if not media_url:
        return text_res

    print(f"🖼️ MEDIA {ad['id']}")

    try:
        res = requests.get(media_url, timeout=15)
        if res.status_code != 200:
            return None

        ext = ".jpg"
        if "mp4" in res.headers.get("Content-Type", "").lower():
            ext = ".mp4"

    except:
        return None

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp.write(res.content)
    tmp.close()

    flagged = False

    try:
        # IMAGE
        if ext != ".mp4":
            flagged = analyze_image(tmp.name)

        # VIDEO
        else:
            vid = cv2.VideoCapture(tmp.name)

            fps = int(vid.get(cv2.CAP_PROP_FPS)) or 24
            frame_i = 0
            max_seconds = 10  # 🔥 più leggero per GitHub Actions

            success, frame = vid.read()

            while success:
                if frame_i % fps == 0:
                    frame_path = tmp.name + f"_f.jpg"
                    cv2.imwrite(frame_path, frame)

                    if analyze_image(frame_path):
                        flagged = True
                        os.remove(frame_path)
                        break

                    os.remove(frame_path)

                success, frame = vid.read()
                frame_i += 1

                if frame_i > fps * max_seconds:
                    break

            vid.release()

    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)

    if flagged:
        return {"status": "FLAG", "reason": "NSFW_MEDIA"}

    return {"status": "PASS", "reason": ""}


# ==========================
# MAIN LOOP
# ==========================
def run_sentinel():
    ads = get_ads_from_server()

    if not ads:
        print("📭 Nessun annuncio")
        sys.exit(0)

    history = load_history()
    now = time.time()

    queue = []

    for ad in ads:
        h = get_ad_hash(ad)
        if h not in history:
            ad["hash"] = h
            queue.append(ad)

    if not queue:
        print("✅ Nessun nuovo contenuto")
        sys.exit(0)

    random.shuffle(queue)
    queue = queue[:50]

    print(f"🔍 Analisi {len(queue)} ads")

    for ad in queue:
        try:
            if ad.get("media_url"):
                res = analyze_multimedia_ad(ad)
            else:
                res = analyze_text(ad)

            if res and res["status"] == "FLAG":
                flag_ad(ad["id"], res["reason"])

            history[ad["hash"]] = now

        except Exception as e:
            print("⚠️ error ad:", e)

    save_history(history)
    print("🏁 DONE")
    sys.exit(0)


if __name__ == "__main__":
    try:
        run_sentinel()
    except Exception as e:
        print("❌ CRITICAL:", e)
        sys.exit(1)
