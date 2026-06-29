import os
import random
import requests
import time

# Configurazioni
WORKER_URL = "https://adswap.api-tradegpt.workers.dev" # Sostituisci se diverso
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROK_API_KEY = os.environ.get("GROK_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

PROMPT = """
You are a strict Trust & Safety AI Sentinel for a B2B Developer Ad Network. 
Analyze the following ad text and image.
Rules for FLAG:
1. NSFW, Pornographic, or sexually explicit content.
2. Violence, gore, or illegal activities (drugs, weapons).
3. Scam, deceptive behavior, malware, or phishing.
4. If you have any doubt about its safety, be conservative and FLAG it.

Reply ONLY with "PASS" if it is completely safe, or "FLAG: [Reason]" if it violates the rules.

Ad Headline: {headline}
Ad Description: {description}
Destination URL: {url}
"""

def get_ads():
    try:
        # Peschiamo annunci banner e interstitial per analizzarli
        ads = []
        for fmt in ['banner', 'interstitial']:
            res = requests.get(f"{WORKER_URL}/api/serve?format={fmt}&geo=global")
            if res.status_code == 200:
                ads.extend(res.json().get('ads', []))
        # Rimuoviamo i duplicati
        return {ad['id']: ad for ad in ads}.values()
    except Exception as e:
        print(f"Errore nel fetch degli ads: {e}")
        return []

def flag_ad(ad_id, reason):
    print(f"🚨 AD FLAGGATO! ID: {ad_id} | Motivo: {reason}")
    # Chiamiamo il report 3 volte per far scattare il ban immediato nel tuo worker
    for _ in range(3):
        requests.post(f"{WORKER_URL}/api/report?id={ad_id}")
        time.sleep(0.5)

def analyze_with_gemini(ad, image_bytes):
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Usa Gemini 1.5 Flash (veloce, multimodale e con un piano gratuito generoso)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt_text = PROMPT.format(
        headline=ad.get('headline', ''), 
        description=ad.get('description', ''), 
        url=ad.get('destination_url', '')
    )
    
    content = [prompt_text]
    if image_bytes:
        content.append({"mime_type": "image/jpeg", "data": image_bytes})
        
    response = model.generate_content(content)
    return response.text.strip()

def analyze_with_openai_compatible(ad, image_bytes, api_key, endpoint, model_name):
    # Funzione generica per Grok o OpenAI usando la loro libreria o REST API
    # Per semplicità, qui facciamo un'analisi solo testo se il modello non supporta bene le immagini via REST diretto
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    prompt_text = PROMPT.format(
        headline=ad.get('headline', ''), 
        description=ad.get('description', ''), 
        url=ad.get('destination_url', '')
    )
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": 50
    }
    
    res = requests.post(endpoint, headers=headers, json=payload)
    if res.status_code == 200:
        return res.json()['choices'][0]['message']['content'].strip()
    return "PASS" # Fallback sicuro in caso di errore API

def run_sentinel():
    ads = get_ads()
    print(f"👁️ Sentinel attivato: Trovati {len(ads)} annunci da analizzare.")
    
    # Determina quali AI sono disponibili
    available_ais = []
    if GEMINI_API_KEY: available_ais.append('gemini')
    if GROK_API_KEY: available_ais.append('grok')
    if OPENAI_API_KEY: available_ais.append('openai')
    
    if not available_ais:
        print("Nessuna API Key configurata. Esco.")
        return

    for ad in ads:
        # Scarica l'immagine se esiste
        image_bytes = None
        if ad.get('media_url'):
            try:
                img_res = requests.get(ad['media_url'], timeout=5)
                if img_res.status_code == 200:
                    image_bytes = img_res.content
            except:
                pass
                
        # Scegli un'AI a caso per questo annuncio
        chosen_ai = random.choice(available_ais)
        print(f"Analizzo annuncio {ad['id']} con {chosen_ai.upper()}...")
        
        try:
            result = ""
            if chosen_ai == 'gemini':
                result = analyze_with_gemini(ad, image_bytes)
            elif chosen_ai == 'grok':
                result = analyze_with_openai_compatible(ad, image_bytes, GROK_API_KEY, "https://api.x.ai/v1/chat/completions", "grok-beta")
            elif chosen_ai == 'openai':
                result = analyze_with_openai_compatible(ad, image_bytes, OPENAI_API_KEY, "https://api.openai.com/v1/chat/completions", "gpt-4o-mini")
                
            if result.startswith("FLAG"):
                flag_ad(ad['id'], result)
            else:
                print("✅ PASS")
                
        except Exception as e:
            print(f"Errore durante l'analisi dell'annuncio {ad['id']}: {e}")
            
        time.sleep(2) # Pausa per non saturare i rate limit gratuiti

if __name__ == "__main__":
    run_sentinel()
