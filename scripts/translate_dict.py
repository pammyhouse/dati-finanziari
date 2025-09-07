import requests
import json

def traduci_parole_batch(parole, source_lang="en", target_lang="it"):
    separatore = "|||"
    testo_da_tradurre = separatore.join(parole)

    url = "https://libretranslate.com/translate"
    payload = {
        "q": testo_da_tradurre,
        "source": source_lang,
        "target": target_lang,
        "format": "text"
    }
    response = requests.post(url, data=payload)
    traduzioni = {}
    if response.status_code == 200:
        testo_tradotto = response.json()["translatedText"]
        parole_tradotte = testo_tradotto.split(separatore)
        traduzioni = dict(zip(parole, parole_tradotte))
    else:
        traduzioni = {p: p for p in parole}  # fallback
    return traduzioni

def traduci_dizionario_chiavi(dizionario, source_lang="en", target_lang="it"):
    parole = list(dizionario.keys())
    dizionario_traduzioni = traduci_parole_batch(parole, source_lang, target_lang)
    
    nuovo_dizionario = {}
    for chiave, valore in dizionario.items():
        nuova_chiave = dizionario_traduzioni.get(chiave, chiave)
        nuovo_dizionario[nuova_chiave] = valore
    return nuovo_dizionario

# Esempio di dizionario
dizionario = {
    "abandon": 0.1,
    "abundance": 0.9,
    "access": 0.7,
    "accept": 0.7,
    "accelerate": 0.8,
    "accredit": 0.6
}

# Traduzione
dizionario_tradotto = traduci_dizionario_chiavi(dizionario)

# Salvataggio su file JSON
with open("dizionario_tradotto.json", "w", encoding="utf-8") as f:
    json.dump(dizionario_tradotto, f, ensure_ascii=False, indent=2)

print("Traduzione completata. Risultato salvato in 'dizionario_tradotto.json'.")
