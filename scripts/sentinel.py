import os
import json
import time
import requests
import random
import tempfile
import sys
import hashlib
import cv2
import torch

from PIL import Image
from transformers import pipeline

# ==========================
# CONFIG
# ==========================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"
SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY")
HISTORY_FILE = "checked_ads.json"

torch.set_num_threads(1)

print("⏳ Loading Sentinel models (offline-safe)...")

# ==========================
# MODELS (STABLE + CACHE FRIENDLY)
# ==========================

# TEXT SAFETY (robusto, leggero, stabile)
text_model = pipeline(
    "text-classification",
    model="facebook/roberta-hate-speech-dynabench-r4-target",
    truncation=True
)

# IMAGE NSFW (già stabile)
image_model = pipeline(
    "image-classification",
    model="Falconsai/nsfw_image_detection"
)

print("✅ Models ready")

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
        json.dump(history, f, indent=2)

def get_ad_hash(ad):
    content = f"{ad.get('headline','')}{ad.get('description','')}{ad.get('media_url','')}{ad.get('destination_url','')}"
    return hashlib.md5(content.encode()).hexdigest()

# ==========================
# SERVER
# ==========================
def get_ads_from_server():
    if not SENTINEL_SECRET_KEY:
        print("❌ Missing SENTINEL_KEY")
        return []

    try:
        r = requests.get(
            f"{WORKER_URL}/api/admin/serve_all",
            headers={"X-Sentinel-Key": SENTINEL_SECRET_KEY},
            timeout=20
        )

        if r.status_code == 200:
            return r.json().get("ads", [])

        return []
    except Exception as e:
        print("❌ Server error:", e)
        return []

def flag_ad(ad_id, reason):
    print(f"🚨 FLAG {ad_id} -> {reason}")

    for _ in range(2):
        try:
            requests.post(f"{WORKER_URL}/api/report?id={ad_id}", timeout=5)
        except:
            pass
        time.sleep(0.3)

# ==========================
# TEXT ANALYSIS (ROBUSTA)
# ==========================
def analyze_text(text):
    if not text.strip():
        return 0.0

    try:
        result = text_model(text[:512])[0]

        label = result["label"].lower()
        score = float(result["score"])

        # mapping semplice ma stabile
        if "hate" in label or "offensive" in label:
            return score

        return 0.0

    except:
        return 0.0

# ==========================
# IMAGE ANALYSIS
# ==========================
def analyze_image(path):
    try:
        img = Image.open(path).convert("RGB")
        img.thumbnail((512, 512))

        result = image_model(img)
        scores = {r["label"].lower(): r["score"] for r in result}

        nsfw = scores.get("nsfw", 0.0)
        porn = scores.get("porn", 0.0)

        return max(nsfw, porn)

    except:
        return 0.0

# ==========================
# VIDEO FRAME CHECK
# ==========================
def analyze_video(path):
    try:
        cap = cv2.VideoCapture(path)

        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 24
        i = 0

        max_frames = fps * 10
        worst = 0.0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if i % fps == 0:
                tmp = path + "_f.jpg"
                cv2.imwrite(tmp, frame)

                score = analyze_image(tmp)
                worst = max(worst, score)

                os.remove(tmp)

                if worst > 0.65:
                    cap.release()
                    return worst

            i += 1
            if i > max_frames:
                break

        cap.release()
        return worst

    except:
        return 0.0

# ==========================
# MEDIA HANDLER
# ==========================
def analyze_media(url):
    try:
        r = requests.get(url, timeout=15)

        ext = ".mp4" if "mp4" in r.headers.get("Content-Type", "") else ".jpg"

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        tmp.write(r.content)
        tmp.close()

        if ext == ".mp4":
            return analyze_video(tmp.name)
        else:
            return analyze_image(tmp.name)

    except:
        return 0.0

    finally:
        try:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)
        except:
            pass

# ==========================
# MAIN ANALYSIS
# ==========================
def analyze_ad(ad):
    text = f"{ad.get('headline','')} {ad.get('description','')}"
    media_url = ad.get("media_url")

    text_score = analyze_text(text)

    media_score = 0.0
    if media_url:
        media_score = analyze_media(media_url)

    final = max(text_score, media_score)

    # soglia unica stabile
    if final >= 0.60:
        return {"status": "FLAG", "reason": f"RISK_{final:.2f}"}

    return {"status": "PASS", "reason": ""}

# ==========================
# RUN
# ==========================
def run():
    ads = get_ads_from_server()

    if not ads:
        print("📭 No ads")
        return

    history = load_history()
    now = time.time()

    queue = []

    for ad in ads:
        h = get_ad_hash(ad)
        if h not in history:
            ad["hash"] = h
            queue.append(ad)

    queue = queue[:50]
    random.shuffle(queue)

    print(f"🔍 Processing {len(queue)} ads")

    for ad in queue:
        try:
            res = analyze_ad(ad)

            if res["status"] == "FLAG":
                flag_ad(ad["id"], res["reason"])

            history[ad["hash"]] = now

        except Exception as e:
            print("⚠️ error:", e)

    save_history(history)
    print("🏁 DONE")

if __name__ == "__main__":
    run()
