from ollamafreeapi import OllamaFreeAPI

# Inizializza client
client = OllamaFreeAPI()

# Prompt di esempio
prompt = """
Dati finanziari odierni:
NasCOMP: +0.5%
Nas100: +0.4%

Domanda: "NasCOMP e Nas100 vanno di pari passo?"
"""

# Chiamata al modello
response = client.chat(model_name="llama3:8b-instruct", prompt=prompt)

# Mostra output
print(response)
