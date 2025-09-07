import requests
import json
import time

def traduci_parole_batch(parole, source_lang="en", target_lang="it", retry=3, delay=1):
    """
    Traduce una lista di parole usando LibreTranslate con contesto.
    Inserisce ogni parola in 'Translate: parola' per ottenere traduzioni più accurate.
    """
    separatore = "|||"
    testo_da_tradurre = separatore.join([f"Translate: {p}" for p in parole])

    url = "https://libretranslate.com/translate"
    payload = {
        "q": testo_da_tradurre,
        "source": source_lang,
        "target": target_lang,
        "format": "text"
    }

    for attempt in range(retry):
        try:
            response = requests.post(url, data=payload, timeout=15)
            if response.status_code == 200:
                testo_tradotto = response.json()["translatedText"]
                # rimuove 'Traduci:' dal testo tradotto e divide
                parole_tradotte = [t.replace("Traduci:", "").strip() for t in testo_tradotto.split(separatore)]
                return dict(zip(parole, parole_tradotte))
            else:
                print(f"Errore traduzione: status {response.status_code}, tentativo {attempt+1}")
        except requests.RequestException as e:
            print(f"Eccezione durante traduzione: {e}, tentativo {attempt+1}")
        time.sleep(delay)
    
    # fallback se non va a buon fine
    return {p: p for p in parole}

def traduci_dizionario_chiavi(dizionario, source_lang="en", target_lang="it"):
    parole = list(dizionario.keys())
    dizionario_traduzioni = traduci_parole_batch(parole, source_lang, target_lang)
    
    nuovo_dizionario = {dizionario_traduzioni.get(k, k): v for k, v in dizionario.items()}
    return nuovo_dizionario

if __name__ == "__main__":
    # Esempio di dizionario
    dizionario = {
        "abandon": 0.1,
        "abundance": 0.9,
        "access": 0.7,
        "accept": 0.7,
        "accelerate": 0.8,
        "accredit": 0.6,
        "once upon a time, there was something": 0.8
    }

    # Traduzione
    dizionario_tradotto = traduci_dizionario_chiavi(dizionario)

    # Salvataggio su file JSON
    output_file = "scripts/dizionario_tradotto.json"  # cartella 'scripts' esistente
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dizionario_tradotto, f, ensure_ascii=False, indent=2)

    print(f"Traduzione completata. Risultato salvato in '{output_file}'.")
