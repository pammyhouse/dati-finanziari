import requests
import pandas as pd
import random
from sklearn.ensemble import RandomForestClassifier
from bs4 import BeautifulSoup
import logging

# Configura logging per il debug
logging.basicConfig(level=logging.DEBUG)

# Parametri del modello
NUM_TREES = 80
MAX_DEPTH = 8

# Lista di simboli
STOCK_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK.A", "V", "JPM", "JNJ", "WMT", "NVDA"]

# Funzione per scaricare i dati dal file HTML di GitHub
def get_stock_data(symbol):
    url = f"https://raw.githubusercontent.com/pammyhouse/dati-finanziari/main/{symbol.upper()}.html"
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("table tbody tr")
        
        # Estrazione dei dati
        dates, opens, closes, highs, lows, volumes, changes = [], [], [], [], [], [], []
        
        for row in rows:
            columns = row.select("td")
            if len(columns) >= 7:
                dates.append(columns[0].text)
                opens.append(float(columns[1].text))
                closes.append(float(columns[2].text))
                highs.append(float(columns[3].text))
                lows.append(float(columns[4].text))
                volumes.append(float(columns[5].text))
                changes.append(float(columns[6].text))
        
        logging.debug(f"Dati scaricati per {symbol}")
        logging.debug("lastPrice: " + str(closes[-1]) + "firstPrice: " + str(closes[0]))
        return pd.DataFrame({
            "Date": dates, "Open": opens, "Close": closes, "High": highs,
            "Low": lows, "Volume": volumes, "Change": changes
        })

    except requests.RequestException as e:
        logging.error(f"Errore nel caricamento del file HTML per {symbol}: {e}")
        return None

# Funzione per addestrare la Random Forest e fare previsioni
def train_and_predict(data):
    if len(data) < 2:
        logging.error("Dati insufficienti per il calcolo.")
        return

    # Preparazione dei dati
    features = data[["Open", "Close", "High", "Low", "Volume", "Change"]].values[1:]
    targets = [1 if data["Close"].iloc[i] > data["Close"].iloc[i - 1] else 0 for i in range(1, len(data))]
    
    # Addestramento del modello
    model = RandomForestClassifier(n_estimators=NUM_TREES, max_depth=MAX_DEPTH, random_state=42)
    model.fit(features, targets)
    logging.info("Modello addestrato con successo.")

    # Previsione per il prossimo giorno
    last_sample = data[["Open", "Close", "High", "Low", "Volume", "Change"]].iloc[-1].values.reshape(1, -1)
    growth_probability = model.predict_proba(last_sample)[0][1]
    logging.debug(f"Probabilità di crescita per il prossimo giorno: {growth_probability * 100:.2f}%")
    return growth_probability * 100

# Funzione principale per il workflow GitHub Actions
def main():
    for symbol in STOCK_SYMBOLS:
        data = get_stock_data(symbol)
        if data is not None:
            growth_probability = train_and_predict(data)
            logging.info("Previsione per " + str(symbol) + ": " + str(growth_probability) + "% di crescita probabile.")

# Entry point del workflow
if __name__ == "__main__":
    main()
