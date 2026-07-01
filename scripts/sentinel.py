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
from transformers import pipeline, CLIPProcessor, CLIPModel

# ==========================
# CONFIG
# ==========================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"
SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY")
HISTORY_FILE = "checked_ads.json"

torch.set_num_threads(1)

print("⏳ Loading Sentinel models...")

# ==========================
# MODELS (STABLE SETUP)
# ==========================

text_model = pipeline(
    "text-classification",
    model="unitary/toxic-bert",
    top_k=None
)

image_model = pipeline(
    "image-classification",
    model="Falconsai/nsfw_image_detection"
)

clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

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

def save_history(h):
    with open(HISTORY_FILE, "w") as f:
        json.dump(h, f, indent=2)

def ad_hash(ad):
    raw = f"{ad.get('headline','')}{ad.get('description','')}{ad.get('media_url','')}{ad.get('destination_url','')}"
    return hashlib.md5(raw.encode()).hexdigest()


# ==========================
# SERVER
# ==========================
def get_ads():
    if not SENTINEL_SECRET_KEY:
        print("❌ Missing SENTINEL_KEY")
        return []

    try:
        r = requests.get(
            f"{WORKER_URL}/api/admin/serve_all",
            headers={"X-Sentinel-Key": SENTINEL_SECRET_KEY},
            timeout=20
        )
        return r.json().get("ads", []) if r.status_code == 200 else []
    except:
        return []


def flag(ad_id, reason):
    print(f"🚨 FLAG {ad_id} -> {reason}")
    try:
        requests.post(f"{WORKER_URL}/api/report?id={ad_id}", timeout=5)
    except:
        pass


# ==========================
# TEXT RISK (STABLE)
# ==========================
def text_risk(text):
    if not text.strip():
        return 0.0

    try:
        out = text_model(text[:512])[0]

        # toxic-bert returns list of labels
        for item in out:
            if item["label"] == "toxic":
                return float(item["score"])

    except:
        pass

    return 0.0


# ==========================
# IMAGE NSFW MODEL
# ==========================
def image_risk(path):
    try:
        img = Image.open(path).convert("RGB")
        img.thumbnail((512, 512))

        out = image_model(img)
        scores = {x["label"].lower(): x["score"] for x in out}

        return max(
            scores.get("nsfw", 0),
            scores.get("porn", 0),
            scores.get("sexy", 0)
        )

    except:
        return 0.0


# ==========================
# CLIP SOFT SIGNAL (NOT DECIDER)
# ==========================
def clip_risk(path):
    try:
        img = Image.open(path).convert("RGB")

        prompts = [
            "sexual content",
            "suggestive cartoon image",
            "adult content",
            "safe family image"
        ]

        inputs = clip_processor(
            text=prompts,
            images=img,
            return_tensors="pt",
            padding=True
        )

        with torch.no_grad():
            out = clip_model(**inputs)
            probs = out.logits_per_image.softmax(dim=1)[0]

        unsafe = float(probs[0] + probs[1] + probs[2])
        safe = float(probs[3])

        return max(0.0, unsafe - safe)

    except:
        return 0.0


# ==========================
# URL RISK (WEAK SIGNAL)
# ==========================
def url_risk(url):
    if not url:
        return 0.0

    signals = [".zip", ".click", ".loan", ".win", "casino", "bet", "phishing"]
    return min(sum(0.2 for s in signals if s in url.lower()), 1.0)


# ==========================
# MULTIMODAL ANALYSIS
# ==========================
def analyze(ad):
    text = f"{ad.get('headline','')} {ad.get('description','')}"
    url = ad.get("destination_url", "")

    t = text_risk(text)
    u = url_risk(url)

    m = 0.0
    tmp = None

    media = ad.get("media_url")

    if media:
        try:
            r = requests.get(media, timeout=15)

            ext = ".mp4" if "mp4" in r.headers.get("Content-Type", "") else ".jpg"

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            tmp.write(r.content)
            tmp.close()

            if ext == ".mp4":
                cap = cv2.VideoCapture(tmp.name)

                fps = int(cap.get(cv2.CAP_PROP_FPS)) or 24
                i = 0

                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break

                    if i % fps == 0:
                        f = tmp.name + "_f.jpg"
                        cv2.imwrite(f, frame)

                        img_r = image_risk(f)
                        clip_r = clip_risk(f)

                        m = max(m, img_r, clip_r)
                        os.remove(f)

                    i += 1
                    if i > fps * 10:
                        break

                cap.release()

            else:
                m = max(image_risk(tmp.name), clip_risk(tmp.name))

        except:
            m = 0.0

        finally:
            if tmp and os.path.exists(tmp.name):
                os.remove(tmp.name)

    # ==========================
    # FINAL SCORE (CALIBRATED)
    # ==========================
    score = (
        t * 0.45 +
        m * 0.45 +
        u * 0.10
    )

    if score > 0.72:
        return {"status": "FLAG", "reason": f"RISK_{score:.2f}"}

    return {"status": "PASS", "reason": ""}


# ==========================
# MAIN LOOP
# ==========================
def run():
    ads = get_ads()
    if not ads:
        print("📭 No ads")
        return

    history = load_history()
    now = time.time()

    queue = []
    for ad in ads:
        h = ad_hash(ad)
        if h not in history:
            ad["hash"] = h
            queue.append(ad)

    queue = queue[:40]
    random.shuffle(queue)

    print(f"🔍 Processing {len(queue)} ads")

    for ad in queue:
        try:
            res = analyze(ad)

            if res["status"] == "FLAG":
                flag(ad["id"], res["reason"])

            history[ad["hash"]] = now

        except Exception as e:
            print("⚠️ error:", e)

    save_history(history)
    print("🏁 DONE")


if __name__ == "__main__":
    run()
