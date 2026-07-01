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
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
from detoxify import Detoxify

# ==========================
# CONFIG
# ==========================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"
SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY")
HISTORY_FILE = "checked_ads.json"

torch.set_num_threads(1)

print("⏳ Loading AI models...")

try:
    # --- TEXT MODELS ---
    text_model = Detoxify("multilingual")

    safety_tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-base")
    safety_model = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-base")

    # --- IMAGE MODEL ---
    image_model = pipeline(
        "image-classification",
        model="falconsai/nsfw_image_detection"
    )

    print("✅ Models ready")

except Exception as e:
    print("❌ Model error:", e)
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
        print("❌ Missing SENTINEL_KEY")
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
        print("❌ Connection error:", e)
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
# URL RISK (soft signal)
# ==========================
def url_risk(url):
    if not url:
        return 0.0

    url = url.lower()

    signals = [".zip", ".click", ".loan", ".win", "phishing", "casino", "bet"]

    score = 0.0
    for s in signals:
        if s in url:
            score += 0.25

    return min(score, 1.0)


# ==========================
# LLM SAFETY CHECK (NO BLACKLIST)
# ==========================
def llm_safety_check(text):
    prompt = f"""
Determine if this content contains illegal or unsafe activity such as:
- drugs
- weapons
- scams
- fraud
- sexual exploitation

Answer only: SAFE or UNSAFE

Text:
{text}
"""

    inputs = safety_tokenizer(prompt, return_tensors="pt", truncation=True)

    outputs = safety_model.generate(
        **inputs,
        max_new_tokens=5
    )

    result = safety_tokenizer.decode(outputs[0], skip_special_tokens=True).upper()

    return "UNSAFE" in result


# ==========================
# TEXT ANALYSIS (MULTI-LAYER)
# ==========================
def analyze_text(ad):
    text = f"{ad.get('headline','')} {ad.get('description','')}".strip().lower()
    url = ad.get("destination_url", "")

    try:
        # --- Layer 1: Detoxify (emotion / toxicity)
        res = text_model.predict(text)

        toxicity = res.get("toxicity", 0)
        sexual = res.get("sexual_explicit", 0)
        threat = res.get("threat", 0)

        risk_score = (
            toxicity * 0.4 +
            sexual * 0.3 +
            threat * 0.6 +
            url_risk(url) * 0.3
        )

        if risk_score > 0.75:
            return {"status": "FLAG", "reason": "TOXICITY_MODEL"}

        # --- Layer 2: LLM semantic safety (drugs/weapons/fraud)
        if llm_safety_check(text):
            return {"status": "FLAG", "reason": "LLM_ILLEGAL_CONTENT"}

    except Exception as e:
        print("⚠️ Text error:", e)

    return {"status": "PASS", "reason": ""}


# ==========================
# IMAGE ANALYSIS
# ==========================
def analyze_image(file_path):
    try:
        img = Image.open(file_path)
        img.thumbnail((512, 512))

        result = image_model(img)
        scores = {r["label"].lower(): r["score"] for r in result}

        sexual_score = max(
            scores.get("nsfw", 0),
            scores.get("porn", 0),
            scores.get("sexy", 0)
        )

        if sexual_score > 0.80:
            return True

        return False

    except Exception as e:
        print("⚠️ Image error:", e)
        return False


# ==========================
# MULTIMEDIA
# ==========================
def analyze_multimedia_ad(ad):
    media_url = ad.get("media_url")

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
        if ext != ".mp4":
            flagged = analyze_image(tmp.name)

        else:
            vid = cv2.VideoCapture(tmp.name)

            fps = int(vid.get(cv2.CAP_PROP_FPS)) or 24
            frame_i = 0
            max_seconds = 10

            success, frame = vid.read()

            while success:
                if frame_i % fps == 0:
                    frame_path = tmp.name + "_frame.jpg"
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
        return {"status": "FLAG", "reason": "MEDIA_RISK"}

    return {"status": "PASS", "reason": ""}


# ==========================
# MAIN LOOP
# ==========================
def run_sentinel():
    ads = get_ads_from_server()

    if not ads:
        print("📭 No ads")
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
        print("✅ No new content")
        sys.exit(0)

    random.shuffle(queue)
    queue = queue[:50]

    print(f"🔍 Processing {len(queue)} ads")

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
            print("⚠️ error:", e)

    save_history(history)
    print("🏁 DONE")


if __name__ == "__main__":
    try:
        run_sentinel()
    except Exception as e:
        print("❌ CRITICAL:", e)
        sys.exit(1)
