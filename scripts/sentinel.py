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
# CONFIGURAZIONI
# ==========================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"
SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY")
HISTORY_FILE = "checked_ads.json"

torch.set_num_threads(1)

print("⏳ Caricamento dei modelli IA (Zero-Shot & Multimodal)...")

# ==========================
# MODELLI (COMPATIBILI GITHUB ACTIONS)
# ==========================

# 1. Modello Testuale Zero-Shot (Multilingua) per riconoscere contesti illegali
text_model = pipeline(
    "zero-shot-classification",
    model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli" 
)

# 2. Modello base per il Porno esplicito
image_model = pipeline(
    "image-classification",
    model="Falconsai/nsfw_image_detection"
)

# 3. CLIP per contesti visivi complessi (Armi, Droghe, Truffe)
clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

print("✅ Modelli pronti all'uso.")

# ==========================
# STORICO E HASH
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
    return hashlib.md5(content.encode()).hexdigest()

# ==========================
# SERVER
# ==========================
def get_ads_from_server():
    if not SENTINEL_SECRET_KEY:
        print("❌ SENTINEL_KEY mancante")
        return []

    try:
        res = requests.get(
            f"{WORKER_URL}/api/admin/serve_all",
            headers={"X-Sentinel-Key": SENTINEL_SECRET_KEY},
            timeout=20
        )
        if res.status_code == 200:
            return res.json().get("ads", [])
        return []
    except Exception as e:
        print("❌ Errore del server:", e)
        return []

def flag_ad(ad_id, reason):
    print(f"🚨 FLAG IMMEDIATO (Burst x3) {ad_id} -> {reason}")
    # Il burst a 3 assicura la sospensione automatica immediata dell'utente sul Worker
    for i in range(3):
        try:
            requests.post(f"{WORKER_URL}/api/report?id={ad_id}", timeout=5)
            print(f"   -> Segnalazione {i+1}/3 inviata con successo.")
        except Exception as e:
            print(f"   -> Fallimento connessione alla chiamata {i+1}: {e}")
        time.sleep(0.5)

# ==========================
# ANALISI TESTUALE (ZERO-SHOT)
# ==========================
def text_risk(text):
    if not text.strip(): return 0.0
    try:
        candidate_labels = ["illegal drugs and narcotics", "weapons and firearms", "pornography", "financial scam", "safe marketing advertisement"]
        res = text_model(text[:512], candidate_labels, multi_label=False)
        
        if res['labels'][0] == "safe marketing advertisement":
            return 0.1
            
        risk_score = 0.0
        for label, score in zip(res['labels'], res['scores']):
            if label != "safe marketing advertisement":
                risk_score += score
                
        return min(risk_score, 1.0)
    except:
        return 0.0

# ==========================
# ANALISI IMMAGINI (CLIP ZERO-SHOT)
# ==========================
def clip_risk(image_path):
    try:
        image = Image.open(image_path).convert("RGB")
        prompts = [
            "sexual content and nudity",
            "firearms, weapons or guns",
            "illegal drugs or narcotics",
            "financial scam or phishing",
            "safe family friendly image"
        ]

        inputs = clip_processor(text=prompts, images=image, return_tensors="pt", padding=True)
        outputs = clip_model(**inputs)
        probs = outputs.logits_per_image.softmax(dim=1)[0]

        unsafe_score = float(probs[0] + probs[1] + probs[2] + probs[3])
        safe_score = float(probs[4])

        return unsafe_score - safe_score
    except:
        return 0.0

# ==========================
# ANALISI IMMAGINI (NSFW DI BASE)
# ==========================
def image_risk(image_path):
    try:
        img = Image.open(image_path).convert("RGB")
        img.thumbnail((512, 512))

        result = image_model(img)
        scores = {r["label"].lower(): r["score"] for r in result}

        return max(scores.get("nsfw", 0), scores.get("porn", 0), scores.get("sexy", 0))
    except:
        return 0.0

# ==========================
# ANALISI URL (Eurisitica)
# ==========================
def url_risk(url):
    if not url: return 0.0
    signals = [".zip", ".click", ".loan", ".win", "casino", "bet", "phishing"]
    score = sum(0.2 for s in signals if s in url.lower())
    return min(score, 1.0)

# ==========================
# ANALISI MULTIMODALE PONDERATA
# ==========================
def analyze_ad(ad):
    text = f"{ad.get('headline','')} {ad.get('description','')}"
    url = ad.get("destination_url", "")

    # -------- TESTO --------
    t_score = text_risk(text)

    # -------- MEDIA --------
    m_score = 0.0
    media_url = ad.get("media_url")
    tmp_file = None

    if media_url:
        try:
            r = requests.get(media_url, timeout=15)
            ext = ".mp4" if "mp4" in r.headers.get("Content-Type", "") else ".jpg"

            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            tmp_file.write(r.content)
            tmp_file.close()

            if ext == ".mp4":
                cap = cv2.VideoCapture(tmp_file.name)
                fps = int(cap.get(cv2.CAP_PROP_FPS)) or 24
                i = 0

                while True:
                    ret, frame = cap.read()
                    if not ret: break

                    if i % fps == 0:
                        fpath = tmp_file.name + "_f.jpg"
                        cv2.imwrite(fpath, frame)

                        img_score = image_risk(fpath)
                        clip_score = max(0, clip_risk(fpath)) 
                        
                        m_score = max(m_score, img_score, clip_score)
                        os.remove(fpath)

                    i += 1
                    if i > fps * 10: break 
                cap.release()

            else:
                img_score = image_risk(tmp_file.name)
                clip_score = max(0, clip_risk(tmp_file.name))
                m_score = max(img_score, clip_score)

        except:
            m_score = 0.0
        finally:
            if tmp_file and os.path.exists(tmp_file.name):
                os.remove(tmp_file.name)

    # -------- URL --------
    u_score = url_risk(url)

    # -------- CALCOLO FINALE --------
    final_score = max(t_score, m_score) * 0.8 + (u_score * 0.2)

    if final_score > 0.65:
        return {"status": "FLAG", "reason": f"AI_RISK_SCORE:_{final_score:.2f}"}

    return {"status": "PASS", "reason": ""}

# ==========================
# LOOP PRINCIPALE
# ==========================
def run():
    ads = get_ads_from_server()
    if not ads:
        print("📭 Nessun annuncio da verificare.")
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

    print(f"🔍 Elaborazione di {len(queue)} creatività in locale...")

    for ad in queue:
        try:
            res = analyze_ad(ad)
            if res["status"] == "FLAG":
                flag_ad(ad["id"], res["reason"])
            history[ad["hash"]] = now
        except Exception as e:
            print(f"⚠️ Errore imprevisto sull'ID {ad.get('id')}:", e)

    save_history(history)
    print("🏁 Elaborazione completata.")

if __name__ == "__main__":
    run()
