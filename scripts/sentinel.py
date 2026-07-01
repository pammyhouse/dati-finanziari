import os
import json
import time
import requests
import random
import tempfile
import hashlib
import cv2
import torch

from PIL import Image
from transformers import pipeline, CLIPProcessor, CLIPModel

# ==========================
# CONFIG
# ==========================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"
SENTINEL_KEY = os.environ.get("SENTINEL_KEY")
HISTORY_FILE = "checked_ads.json"

torch.set_num_threads(1)

print("⏳ Loading Sentinel models...")

# ==========================
# MODELS (STABLE SETUP)
# ==========================

text_model = pipeline(
    "zero-shot-classification",
    model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
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
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
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
def fetch_ads():
    if not SENTINEL_KEY:
        return []

    r = requests.get(
        f"{WORKER_URL}/api/admin/serve_all",
        headers={"X-Sentinel-Key": SENTINEL_KEY},
        timeout=20
    )

    if r.status_code != 200:
        return []

    return r.json().get("ads", [])


def flag(ad_id, score):
    print(f"🚨 FLAG {ad_id} -> RISK_{score:.2f}")

    for _ in range(2):
        try:
            requests.post(f"{WORKER_URL}/api/report?id={ad_id}", timeout=5)
        except:
            pass
        time.sleep(0.2)


# ==========================
# TEXT SCORE (CALIBRATED)
# ==========================
LABELS = [
    "safe advertisement",
    "sexual content",
    "drugs or illegal substances",
    "weapons or violence",
    "fraud or scam"
]

def text_score(text):
    if not text.strip():
        return 0.0

    out = text_model(text[:512], LABELS)

    # prendi max NON assoluto ma escluso SAFE
    best_label = out["labels"][0]
    best_score = out["scores"][0]

    if best_label == "safe advertisement":
        return 0.0

    return float(best_score)


# ==========================
# IMAGE SCORE
# ==========================
def image_score(img):
    res = image_model(img)
    scores = {r["label"].lower(): r["score"] for r in res}

    return max(
        scores.get("nsfw", 0),
        scores.get("porn", 0),
        scores.get("sexy", 0)
    )


# ==========================
# CLIP SEMANTIC CHECK
# ==========================
PROMPTS = [
    "sexual explicit content",
    "weapons or firearms",
    "illegal drugs",
    "scam or fraud",
    "safe family friendly image"
]

def clip_score(image):
    inputs = clip_processor(text=PROMPTS, images=image, return_tensors="pt", padding=True)

    with torch.no_grad():
        out = clip_model(**inputs)
        probs = out.logits_per_image.softmax(dim=1)[0]

    idx = int(probs.argmax())

    if idx == len(PROMPTS) - 1:
        return 0.0

    return float(probs[idx])


# ==========================
# VIDEO SAMPLING
# ==========================
def sample_video(path):
    cap = cv2.VideoCapture(path)
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 24

    frames = []
    i = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if i % fps == 0:
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            cv2.imwrite(tmp.name, frame)
            frames.append(tmp.name)

        i += 1

        if i > fps * 8:
            break

    cap.release()
    return frames


# ==========================
# MAIN ANALYSIS
# ==========================
def analyze(ad):
    text = f"{ad.get('headline','')} {ad.get('description','')}"
    url = ad.get("destination_url", "")
    media = ad.get("media_url")

    t = text_score(text)

    m = 0.0

    tmp_file = None

    if media:
        try:
            r = requests.get(media, timeout=10)

            ext = ".mp4" if "mp4" in r.headers.get("Content-Type","") else ".jpg"

            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            tmp_file.write(r.content)
            tmp_file.close()

            if ext == ".mp4":
                frames = sample_video(tmp_file.name)

                for f in frames:
                    img = Image.open(f).convert("RGB")

                    m = max(
                        m,
                        image_score(img),
                        clip_score(img)
                    )

                    os.remove(f)

            else:
                img = Image.open(tmp_file.name).convert("RGB")

                m = max(
                    image_score(img),
                    clip_score(img)
                )

        except:
            m = 0.0

        finally:
            if tmp_file and os.path.exists(tmp_file.name):
                os.remove(tmp_file.name)

    # ⚖️ FUSIONE REALISTICA (IMPORTANTISSIMO)
    risk = max(t, m)

    # smoothing per evitare 1.0 finti
    risk = min(risk * 0.85, 1.0)

    if risk > 0.72:
        return {"flag": True, "score": risk}

    return {"flag": False, "score": risk}


# ==========================
# RUN
# ==========================
def run():
    ads = fetch_ads()

    if not ads:
        print("📭 No ads")
        return

    hist = load_history()
    now = time.time()

    queue = []

    for ad in ads:
        h = ad_hash(ad)
        if h not in hist:
            ad["hash"] = h
            queue.append(ad)

    random.shuffle(queue)

    print(f"🔍 Processing {len(queue)} ads")

    for ad in queue[:50]:
        res = analyze(ad)

        if res["flag"]:
            flag(ad["id"], res["score"])

        hist[ad["hash"]] = now

    save_history(hist)
    print("🏁 DONE")


if __name__ == "__main__":
    run()
