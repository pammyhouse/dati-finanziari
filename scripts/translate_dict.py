import json
from libretranslatepy import LibreTranslateAPI

def traduci_dizionario_chiavi(dizionario, source_lang="en", target_lang="it"):
    """
    Traduce le chiavi di un dizionario mantenendo i valori numerici invariati.
    """
    lt = LibreTranslateAPI("https://libretranslate.com/")  # server pubblico LibreTranslate
    
    nuovo_dizionario = {}
    for chiave, valore in dizionario.items():
        try:
            nuova_chiave = lt.translate(chiave, source_lang, target_lang)
        except Exception as e:
            print(f"Errore durante la traduzione di '{chiave}': {e}")
            nuova_chiave = chiave  # fallback se fallisce
        nuovo_dizionario[nuova_chiave] = valore

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
    output_file = "scripts/dizionario_tradotto.json"  # assicurati che la cartella 'scripts' esista
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dizionario_tradotto, f, ensure_ascii=False, indent=2)

    print(f"Traduzione completata. Risultato salvato in '{output_file}'.")
