import os
import requests
from bs4 import BeautifulSoup
import logging
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
from sklearn.preprocessing import MinMaxScaler
from joblib import Parallel, delayed
from github import Github, GithubException

# Configura TensorFlow per usare la GPU (se disponibile)
if tf.config.list_physical_devices('GPU'):
    logging.info("GPU rilevata. TensorFlow userà la GPU per il calcolo.")
else:
    logging.info("GPU non rilevata. TensorFlow userà la CPU.")

# Impostazioni globali
FMP_API_KEY = os.getenv("FMP_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "pammyhouse/dati-finanziari"

stockSymbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "V"]  # Lista abbreviata per esempio
symbol_probabilities = []

# Configura il logger
logging.basicConfig(level=logging.DEBUG)

# Funzione per recuperare i dati dal file HTML
def get_stock_data(symbol):
    url = f"https://raw.githubusercontent.com/pammyhouse/dati-finanziari/main/{symbol.upper()}.html"
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table')
        rows = table.find_all('tr')[1:]
        
        dates, opens, highs, lows, prices, volumes = [], [], [], [], [], []
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 6:
                dates.append(cols[0].text.strip())
                opens.append(float(cols[1].text.strip()))
                prices.append(float(cols[2].text.strip()))
                highs.append(float(cols[3].text.strip()))
                lows.append(float(cols[4].text.strip()))
                volumes.append(float(cols[5].text.strip()))
        
        # Inverti i dati (dalla data più vecchia alla più recente)
        return {
            "dates": dates[::-1],
            "opens": opens[::-1],
            "highs": highs[::-1],
            "lows": lows[::-1],
            "prices": prices[::-1],
            "volumes": volumes[::-1]
        }
    except Exception as e:
        logging.error(f"Errore durante il recupero dei dati per {symbol}: {e}")
        return None

# Funzione per invertire l'ordine dei dati
def reverse_data(data):
    for key in data.keys():
        data[key] = data[key][::-1]
    return data

# Funzione per stampare i dati giornalieri (log)
def log_daily_data(symbol, data):
    for i in range(len(data["dates"])):
        log_message = (
            f"Simbolo: {symbol}, Data: {data['dates'][i]}, Apertura: {data['opens'][i]}, "
            f"Chiusura: {data['prices'][i]}, Massimo: {data['highs'][i]}, Minimo: {data['lows'][i]}, "
            f"Volume: {data['volumes'][i]}"
        )
        logging.debug(log_message)

# Funzione per creare e addestrare il modello LSTM
def train_lstm_model(data, symbol):
    try:
        prices = np.array(data["prices"]).reshape(-1, 1)
        scaler = MinMaxScaler()
        scaled_prices = scaler.fit_transform(prices)
        
        # Crea sequenze temporali
        X, y = [], []
        for i in range(60, len(scaled_prices)):
            X.append(scaled_prices[i - 60:i])
            y.append(scaled_prices[i])
        
        X, y = np.array(X), np.array(y)
        
        # Costruzione del modello LSTM
        model = Sequential([
            LSTM(50, return_sequences=True, input_shape=(X.shape[1], X.shape[2])),
            LSTM(50),
            Dense(1)
        ])
        model.compile(optimizer='adam', loss='mean_squared_error')
        model.fit(X, y, epochs=10, batch_size=32, verbose=0)
        
        # Predizione
        last_sequence = scaled_prices[-60:].reshape(1, 60, 1)
        prediction = model.predict(last_sequence)[0][0]
        prediction = scaler.inverse_transform([[prediction]])[0][0]
        
        # Calcolo della probabilità di crescita
        probability = 1 if prediction > prices[-1] else 0
        logging.info(f"Simbolo: {symbol}, Probabilità di crescita: {probability * 100:.2f}%")
        return symbol, probability * 100
    except Exception as e:
        logging.error(f"Errore durante l'addestramento del modello per {symbol}: {e}")
        return symbol, 0

# Funzione per salvare la previsione in un file HTML
def upload_prediction_html(repo, symbol, probability):
    try:
        file_path = f"predictions/{symbol}.html"
        html_content = [
            f"<html><head><title>Previsione per {symbol}</title></head><body>",
            f"<h1>Previsione per {symbol}</h1>",
            f"<p>Probabilità di crescita: {probability:.2f}%</p>",
            "</body></html>"
        ]
        repo.create_file(file_path, f"Created probability for {symbol}", "\n".join(html_content))
        logging.info(f"File HTML per {symbol} salvato con successo.")
    except GithubException as e:
        logging.error(f"Errore durante il salvataggio del file HTML per {symbol}: {e}")

# Funzione che esegue l'operazione di gestione del modello
def operator_manager(symbol, repo):
    data = get_stock_data(symbol)
    if data:
        reverse_data(data)
        log_daily_data(symbol, data)
        symbol, probability = train_lstm_model(data, symbol)
        upload_prediction_html(repo, symbol, probability)
    else:
        logging.error(f"Impossibile processare i dati per {symbol}.")

# Funzione per caricare e classificare tutte le probabilità
def create_classification_file(repo, results):
    try:
        classification_file = "classification.html"
        sorted_results = sorted(results, key=lambda x: x[1], reverse=True)
        html_content = [
            "<html><head><title>Classificazione delle Probabilità</title></head><body>",
            "<h1>Classifica delle Probabilità di Crescita</h1>",
            "<table border='1'><tr><th>Simbolo</th><th>Probabilità (%)</th></tr>"
        ]
        for symbol, probability in sorted_results:
            html_content.append(f"<tr><td>{symbol}</td><td>{probability:.2f}</td></tr>")
        html_content.append("</table></body></html>")
        
        repo.create_file(classification_file, "Updated classification file", "\n".join(html_content))
        logging.info("Classifica aggiornata con successo.")
    except GithubException as e:
        logging.error(f"Errore durante la creazione del file di classifica: {e}")

# Parallelizzazione
if __name__ == "__main__":
    # Connettiti al repository GitHub
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)

    # Numero di processi paralleli
    num_cores = os.cpu_count() or 4
    logging.info(f"Avvio con parallelizzazione su {num_cores} core.")

    # Processa i simboli in parallelo
    results = Parallel(n_jobs=num_cores)(delayed(operator_manager)(symbol, repo) for symbol in stockSymbols)

    # Crea il file di classifica
    create_classification_file(repo, results)
