# scripts/translate_dict.py
import json
import os
from googletrans import Translator

def traduci_dizionario_chiavi(dizionario, src='en', dest='it'):
    translator = Translator()
    nuovo_dizionario = {}
    for chiave, valore in dizionario.items():
        try:
            traduzione = translator.translate(chiave, src=src, dest=dest).text
        except Exception as e:
            print(f"Errore durante la traduzione di '{chiave}': {e}")
            traduzione = chiave  # fallback
        nuovo_dizionario[traduzione] = valore
    return nuovo_dizionario

if __name__ == "__main__":
    # Dizionario di esempio
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

    # Creazione cartella 'scripts' se non esiste
    os.makedirs('scripts', exist_ok=True)

    # Salvataggio su file JSON
    output_file = "scripts/dizionario_tradotto.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dizionario_tradotto, f, ensure_ascii=False, indent=2)

    print(f"Traduzione completata. Risultato salvato in '{output_file}'.")
