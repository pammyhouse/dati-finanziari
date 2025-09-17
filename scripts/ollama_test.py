from ollamafreeapi import OllamaFreeAPI
import time

# Inizializza client
client = OllamaFreeAPI()

# Prompt di esempio
prompt = """
Dati finanziari odierni:
NasCOMP: +0.5%
Nas100: +0.4%

Domanda: "NasCOMP e Nas100 vanno di pari passo?"
"""

# Lista di modelli stabili e più leggeri da provare
modelli_possibili = ["mistral:7b-instruct", "llama3:7b-instruct"]

# Retry loop
for modello in modelli_possibili:
    try:
        response = client.chat(model_name=modello, prompt=prompt)
        print(f"Risposta dal modello {modello}:")
        print(response)
        break  # esci dal loop se va a buon fine
    except Exception as e:
        print(f"Il modello {modello} ha fallito: {e}")
        time.sleep(5)  # aspetta 5 secondi prima di provare il prossimo modello
