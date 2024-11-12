import os
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from sklearn.ensemble import RandomForestClassifier
import numpy as np
import pandas as pd
import logging

# Configurazione di logging
logging.basicConfig(level=logging.DEBUG)

# Definizione del numero di alberi e della profondità massima
NUM_TREES = 80
MAX_DEPTH = 8
STOCK_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"]  # Lista dei simboli

# Funzione per ottenere dati storici del simbolo da file HTML su GitHub
def get_stock_data(symbol):
    url = f"https://raw.githubusercontent.com/pammyhouse/dati-finanziari/main/{symbol}.html"
    response = requests.get(url)
    if response.status_code != 200:
        logging.error(f"Errore nel caricamento del file HTML per {symbol}")
        return None

    # Parsing del contenuto HTML
    soup = BeautifulSoup(response.content, 'html.parser')
    rows = soup.select("table tbody tr")
    
    # Estrarre i dati nelle liste appropriate
    dates, opens, highs, lows, closes, volumes, changes = [], [], [], [], [], [], []
    for row in rows:
        columns = row.find_all("td")
        if len(columns) >= 6:
            dates.append(columns[0].text)
            opens.append(float(columns[1].text))
            closes.append(float(columns[2].text))
            highs.append(float(columns[3].text))
            lows.append(float(columns[4].text))
            volumes.append(float(columns[5].text))
            changes.append(float(columns[6].text))

    return pd.DataFrame({
        'Date': dates,
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': volumes,
        'Change': changes
    })

# Funzione per salvare il risultato della previsione in un file HTML
def save_prediction_to_html(symbol, prediction):
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)  # Creare la cartella "results" se non esiste
    file_path = results_dir / f"{symbol}_RESULT.html"
    
    with open(file_path, "w") as f:
        f.write(f"<html><body><h2>Prediction for {symbol}</h2>")
        f.write(f"<p>Probabilità di crescita: {prediction:.2f}%</p>")
        f.write("</body></html>")
    
    logging.info(f"Salvato il risultato della previsione per {symbol} in {file_path}")

# Funzione per calcolare la previsione di crescita del simbolo
def predict_growth_probability(data):
    if data is None or len(data) < 2:
        logging.error("Dati insufficienti per effettuare una previsione.")
        return None

    # Costruire il dataset di caratteristiche e target
    features = data[['Open', 'Close', 'High', 'Low', 'Volume', 'Change']].values[1:]
    targets = (data['Close'].values[1:] > data['Close'].values[:-1]).astype(int)
    
    # Addestrare il modello Random Forest
    model = RandomForestClassifier(n_estimators=NUM_TREES, max_depth=MAX_DEPTH, random_state=42)
    model.fit(features, targets)
    
    # Effettuare la previsione per l'ultimo campione
    last_sample = features[-1].reshape(1, -1)
    growth_probability = model.predict_proba(last_sample)[0][1] * 100
    return growth_probability

# Funzione per generare il file HTML con la classifica delle previsioni
def generate_ranking_file(predictions):
    # Ordinare le previsioni in ordine decrescente, in caso di parità per ordine alfabetico
    sorted_predictions = sorted(predictions, key=lambda x: (-x[1], x[0]))
    
    # Creare il file HTML classifica.html
    results_dir = Path("results")
    file_path = results_dir / "classifica.html"
    
    with open(file_path, "w") as f:
        f.write("<html><body><h2>Classifica delle Previsioni</h2>")
        f.write("<table border='1'><tr><th>Simbolo</th><th>Probabilità di Crescita (%)</th></tr>")
        for symbol, prediction in sorted_predictions:
            f.write(f"<tr><td>{symbol}</td><td>{prediction:.2f}</td></tr>")
        f.write("</table></body></html>")
    
    logging.info(f"Classifica delle previsioni salvata in {file_path}")

# Funzione principale
def main():
    predictions = []  # Lista per memorizzare simboli e le rispettive previsioni

    for symbol in STOCK_SYMBOLS:
        logging.info(f"Ottenimento dei dati per {symbol}")
        data = get_stock_data(symbol)
        if data is not None:
            growth_probability = predict_growth_probability(data)
            if growth_probability is not None:
                save_prediction_to_html(symbol, growth_probability)
                predictions.append((symbol, growth_probability))  # Aggiungere simbolo e previsione alla lista
            else:
                logging.error(f"Impossibile calcolare la probabilità di crescita per {symbol}")
    
    # Generare il file classifica.html con la classifica delle previsioni
    generate_ranking_file(predictions)

if __name__ == "__main__":
    main()
