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

# ==========================================
# CONFIGURAZIONI E VARIABILI D'AMBIENTE
# ==========================================
WORKER_URL = "https://adswap.api-tradegpt.workers.dev"
SENTINEL_SECRET_KEY = os.environ.get("SENTINEL_KEY") 
HISTORY_FILE = "checked_ads.json"

print("⏳ Inizializzazione modelli AI in RAM locale...")
try:
    # Modello testuale addestrato per il riconoscimento di tossicità multilingua
    text_model = Detoxify('multilingual')
    # Modello leggerissimo ed efficiente per la classificazione NSFW visiva
    image_model = pipeline("image-classification", model="falconsai/nsfw_image_detection")
    print("✅ Modelli locali pronti all'uso.")
except Exception as e:
    print(f"❌ Errore caricamento modelli: {e}")
    sys.exit(1)

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

def get_ad_hash(ad):
    content = f"{ad.get('headline', '')}{ad.get('description', '')}{ad.get('media_url', '')}{ad.get('destination_url', '')}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_ads_from_server():
    if not SENTINEL_SECRET_KEY:
        print("❌ SENTINEL_KEY non configurata. Accesso negato.")
        return []

    print("📡 Download TOTALE annunci dal server...")
    headers = {"X-Sentinel-Key": SENTINEL_SECRET_KEY}
    try:
        res = requests.get(f"{WORKER_URL}/api/admin/serve_all", headers=headers, timeout=20)
        if res.status_code == 200:
            return res.json().get('ads', [])
        return []
    except:
        return []

def flag_ad(ad_id, reason):
    print(f"🚨 AD FLAGGATO! ID: {ad_id} | Motivo: {reason}")
    for _ in range(3):
        try:
            requests.post(f"{WORKER_URL}/api/report?id={ad_id}", timeout=5)
        except:
            pass
        time.sleep(0.5)

def is_malicious_url(url):
    """Controlla domini e pattern notoriamente legati a truffe, phishing e malware."""
    if not url: return False
    url_lower = url.lower()
    
    bad_tlds = ['.xyz', '.zip', '.click', '.loan', '.top', '.win', '.stream']
    if any(url_lower.endswith(tld) or (tld + "/") in url_lower for tld in bad_tlds):
        return True
        
    bad_keywords = ['free-money', 'hack', 'crack', 'nude', 'porn', 'xxx', 'sex', 'casino', 'betting', 'phishing']
    if any(keyword in url_lower for keyword in bad_keywords):
        return True
        
    return False

# ==========================================
# MOTORE 1: TESTO E URL (DETOXIFY + REGEX)
# ==========================================
def analyze_text(ad):
    url = ad.get('destination_url', '')
    if is_malicious_url(url):
        return {"status": "FLAG", "reason": "MALICIOUS_OR_BANNED_URL"}

    text = f"{ad.get('headline', '')} {ad.get('description', '')}".strip()
    if not text:
        return {"status": "PASS", "reason": ""}

    try:
        results = text_model.predict(text)
        # Soglie di tolleranza severe ma mirate ai Tier-1
        if results['toxicity'] > 0.85 or results['sexual_explicit'] > 0.7 or results['threat'] > 0.75:
            return {"status": "FLAG", "reason": "TOXIC_OR_EXPLICIT_TEXT"}
    except Exception as e:
        print(f"⚠️ Errore analisi testo: {e}")
        
    return {"status": "PASS", "reason": ""}

# ==========================================
# MOTORE 2: MULTIMEDIALE (NSFW ONNX PIPELINE)
# ==========================================
def analyze_image_file(file_path):
    """Analizza una singola immagine e restituisce True se è NSFW."""
    try:
        img = Image.open(file_path)
        img.thumbnail((512, 512)) # Riduce la risoluzione per alleggerire la CPU
        result = image_model(img)
        # result formato: [{'label': 'nsfw', 'score': 0.9}, {'label': 'normal', 'score': 0.1}]
        for res in result:
            if res['label'] == 'nsfw' and res['score'] > 0.75:
                return True
        return False
    except Exception as e:
        print(f"⚠️ Errore classificazione immagine: {e}")
        return False

def analyze_multimedia_ad(ad):
    media_url = ad.get('media_url')
    if not media_url: 
        return analyze_text(ad)

    print(f"🖼️ Analisi locale per ID: {ad['id']}")
    
    # 1. Controlla prima il testo e l'URL (Risparmia CPU se c'è già una violazione)
    text_res = analyze_text(ad)
    if text_res["status"] == "FLAG":
        return text_res

    # 2. Download Media
    try:
        res = requests.get(media_url, timeout=15)
        if res.status_code != 200: return None
        mime_type = res.headers.get("Content-Type") or ""
        ext = '.jpg' 
        if 'mp4' in mime_type.lower() or media_url.endswith('.mp4'): ext = '.mp4'
    except:
        return None

    temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    temp_file.write(res.content)
    temp_file.close()

    is_video = ext == '.mp4'
    flagged = False

    try:
        if not is_video:
            # STRADA A: Analisi Immagine Diretta
            flagged = analyze_image_file(temp_file.name)
        else:
            # STRADA B: Estrazione Frame da Video
            print(f"🎥 Estrazione frame video in corso...")
            vidcap = cv2.VideoCapture(temp_file.name)
            fps = int(vidcap.get(cv2.CAP_PROP_FPS))
            if fps <= 0: fps = 24
            
            frame_count = 0
            success, image = vidcap.read()
            while success:
                # Estrae 1 frame al secondo
                if frame_count % fps == 0:
                    frame_path = temp_file.name + f"_frame_{frame_count}.jpg"
                    cv2.imwrite(frame_path, image)
                    
                    if analyze_image_file(frame_path):
                        flagged = True
                        os.remove(frame_path)
                        break # Ferma subito l'analisi del video se trova un frame illecito
                        
                    os.remove(frame_path)
                
                success, image = vidcap.read()
                frame_count += 1
                
                # Limite di sicurezza: analizza al massimo i primi 30 secondi (30 frame estratti)
                if frame_count > fps * 30:
                    break 
            
            vidcap.release()

        if flagged:
            return {"status": "FLAG", "reason": "NSFW_MEDIA_DETECTED"}
        return {"status": "PASS", "reason": ""}

    finally:
        if os.path.exists(temp_file.name):
            os.remove(temp_file.name)

# ==========================================
# GESTORE CENTRALE
# ==========================================
def run_sentinel():
    ads = get_ads_from_server()
    if not ads:
        print("📭 Nessun annuncio trovato nel database globale.")
        sys.exit(0)

    history = load_history()
    current_time = time.time()
    
    ads_to_check = []
    for ad in ads:
        ad_hash = get_ad_hash(ad)
        if ad_hash not in history:
            ad['hash_signature'] = ad_hash 
            ads_to_check.append(ad)

    if not ads_to_check:
        print("✅ Tutti gli annunci in rete sono già stati verificati.")
        sys.exit(0)

    # Processa al massimo 50 annunci nuovi per run per non sforare i minuti di GitHub Actions
    random.shuffle(ads_to_check)
    ads_to_check = ads_to_check[:50] 
    
    print(f"🔍 Sentinel attivato. Elaborazione di {len(ads_to_check)} nuove creatività in locale.")

    for ad in ads_to_check:
        if not ad.get('media_url'):
            res = analyze_text(ad)
        else:
            res = analyze_multimedia_ad(ad)
            
        if res is not None:
            if res['status'] == "FLAG":
                flag_ad(ad['id'], res['reason'])
            history[ad['hash_signature']] = current_time

    save_history(history)
    print("🏁 Controllo completato. Registro aggiornato.")
    sys.exit(0)

if __name__ == "__main__":
    try:
        run_sentinel()
    except Exception as e:
        print(f"❌ Errore critico finale: {e}")
        sys.exit(1)
