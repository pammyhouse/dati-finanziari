import os
import json
import time
import requests
import random
import tempfile
import sys
import hashlib
import cv2
from PIL import Image
import torch
from transformers import (
    pipeline,
    AutoTokenizer,
    AutoModelForSequenceClassification
)
from detoxify import Detoxify

# ==========================
# CONFIG
# ==========================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"
SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY")
HISTORY_FILE = "checked_ads.json"

torch.set_num_threads(1)

print("⏳ Loading AI models...")

# ==========================
# MODELS
# ==========================

# 1. Toxicity / sexual / threat
text_toxic_model = Detoxify("multilingual")

# 2. ZERO-SHOT SAFETY (CRITICAL UPGRADE)
zero_shot_tokenizer = AutoTokenizer.from_pretrained(
    "MoritzLaurer/deberta-v3-large-zeroshot-v2"
)
zero_shot_model = AutoModelForSequenceClassification.from_pretrained(
    "MoritzLaurer/deberta-v3-large-zeroshot-v2"
)

zero_shot = pipeline(
    "zero-shot-classification",
    model=zero_shot_model,
    tokenizer=zero_shot_tokenizer
)

# 3. IMAGE CAPTIONING (semantic vision)
image_caption = pipeline(
    "image-to-text",
    model="Salesforce/blip-image-captioning-large"
)

print("✅ Models ready")


# ==========================
# HISTORY
# ==========================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            return json.load(open(HISTORY_FILE))
        except:
            return {}
    return {}

def save_history(h):
    with open(HISTORY_FILE, "w") as f:
        json.dump(h, f, indent=2)

def hash_ad(ad):
    return hashlib.md5(
        f"{ad.get('headline','')}{ad.get('description','')}{ad.get('media_url','')}".encode()
    ).hexdigest()


# ==========================
# TEXT SAFETY (NO KEYWORDS)
# ==========================
def analyze_text(ad):
    text = f"{ad.get('headline','')} {ad.get('description','')}".strip()

    try:
        tox = text_toxic_model.predict(text)

        base_risk = (
            tox.get("toxicity", 0) * 0.4 +
            tox.get("sexual_explicit", 0) * 0.4 +
            tox.get("threat", 0) * 0.5
        )

        # 🔥 semantic classification (drugs/weapons/fraud/etc)
        z = zero_shot(
            text,
            candidate_labels=[
                "illegal drugs sale",
                "weapons or firearms",
                "fraud or scam",
                "adult sexual content",
                "normal advertisement"
            ]
        )

        illegal_score = 0
        for label, score in zip(z["labels"], z["scores"]):
            if label != "normal advertisement":
                illegal_score = max(illegal_score, score)

        final_score = max(base_risk, illegal_score)

        if final_score > 0.75:
            return {"status": "FLAG", "reason": "TEXT_SEMANTIC_RISK"}

    except Exception as e:
        print("⚠️ text error:", e)

    return {"status": "PASS", "reason": ""}


# ==========================
# IMAGE SAFETY (SEMI-SEMTANTIC)
# ==========================
def analyze_image(path):
    try:
        img = Image.open(path)

        caption = image_caption(img)[0]["generated_text"].lower()

        # second semantic check via zero-shot
        z = zero_shot(
            caption,
            candidate_labels=[
                "sexual content",
                "weapons",
                "drugs",
                "cartoon sexualized content",
                "safe content"
            ]
        )

        max_score = max(z["scores"])

        return max_score > 0.70

    except Exception as e:
        print("⚠️ image error:", e)
        return False


# ==========================
# MULTIMEDIA
# ==========================
def analyze_media(ad):
    url = ad.get("media_url")

    # always text first
    t = analyze_text(ad)
    if t["status"] == "FLAG":
        return t

    if not url:
        return t

    print("🖼️ MEDIA", ad["id"])

    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return None

        ext = ".jpg"
        if "mp4" in r.headers.get("Content-Type",""):
            ext = ".mp4"

    except:
        return None

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp.write(r.content)
    tmp.close()

    flagged = False

    try:
        if ext != ".mp4":
            flagged = analyze_image(tmp.name)

        else:
            vid = cv2.VideoCapture(tmp.name)

            fps = int(vid.get(cv2.CAP_PROP_FPS)) or 24
            i = 0

            success, frame = vid.read()

            while success:
                if i % fps == 0:
                    fp = tmp.name + "_f.jpg"
                    cv2.imwrite(fp, frame)

                    if analyze_image(fp):
                        flagged = True
                        break

                success, frame = vid.read()
                i += 1

                if i > fps * 10:
                    break

            vid.release()

    finally:
        os.remove(tmp.name)

    if flagged:
        return {"status": "FLAG", "reason": "MEDIA_SEMANTIC_RISK"}

    return {"status": "PASS", "reason": ""}


# ==========================
# MAIN
# ==========================
def run():
    if not SENTINEL_SECRET_KEY:
        print("missing key")
        return

    ads = requests.get(
        f"{WORKER_URL}/api/admin/serve_all",
        headers={"X-Sentinel-Key": SENTINEL_SECRET_KEY}
    ).json().get("ads", [])

    history = load_history()
    now = time.time()

    queue = []
    for ad in ads:
        h = hash_ad(ad)
        if h not in history:
            ad["h"] = h
            queue.append(ad)

    queue = queue[:50]
    random.shuffle(queue)

    print("🔍 Processing", len(queue))

    for ad in queue:
        try:
            res = analyze_media(ad) if ad.get("media_url") else analyze_text(ad)

            if res and res["status"] == "FLAG":
                print("🚨 FLAG", ad["id"], res["reason"])

            history[ad["h"]] = now

        except Exception as e:
            print("error", e)

    save_history(history)
    print("DONE")


if __name__ == "__main__":
    run()
