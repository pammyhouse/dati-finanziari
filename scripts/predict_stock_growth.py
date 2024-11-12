import requests
from bs4 import BeautifulSoup
import logging
from sklearn.ensemble import RandomForestClassifier
import numpy as np

# Lista per raccogliere i dati finanziari
dates = []
opens = []
high = []
low = []
prices = []
volumes = []
changes = []

# Funzione per ottenere i dati dal file HTML
def get_stock_data(symbol):
    url = f"https://raw.githubusercontent.com/pammyhouse/dati-finanziari/main/{symbol.upper()}.html"
    
    try:
        # Ottieni il contenuto del file HTML
        response = requests.get(url)
        response.raise_for_status()  # Verifica se la richiesta ha avuto successo

        # Usa BeautifulSoup per analizzare l'HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Seleziona tutte le righe della tabella
        rows = soup.select('table tbody tr')  # Modifica il selettore in base alla struttura del file HTML
        
        # Estrai i dati da ogni riga della tabella
        for row in rows:
            columns = row.find_all('td')
            if len(columns) >= 7:  # Assicurati che ci siano almeno 7 colonne
                date = columns[0].text.strip()
                open_price = float(columns[1].text.strip())
                close_price = float(columns[2].text.strip())
                high_price = float(columns[3].text.strip())
                low_price = float(columns[4].text.strip())
                volume = float(columns[5].text.strip())
                change = float(columns[6].text.strip())
                
                # Aggiungi i dati alle rispettive liste
                dates.append(date)
                opens.append(open_price)
                high.append(high_price)
                low.append(low_price)
                prices.append(close_price)
                volumes.append(volume)
                changes.append(change)
        
        # Dopo aver caricato i dati, invertiamo l'ordine per processarli dalla più vecchia alla più recente
        reverse_data()

        # Stampa i dati (log)
        log_daily_data(symbol)
        
        # Esegui l'operazione con Random Forest
        operator_manager()

    except requests.exceptions.RequestException as e:
        logging.error(f"Errore nel recupero dei dati: {e}")

# Funzione per invertire l'ordine dei dati
def reverse_data():
    global prices, high, low, opens, volumes, changes
    prices = prices[::-1]
    high = high[::-1]
    low = low[::-1]
    opens = opens[::-1]
    volumes = volumes[::-1]
    changes = changes[::-1]

# Funzione per stampare i dati giornalieri (log)
def log_daily_data(symbol):
    for i in range(len(dates)):
        date = dates[i]
        open_price = opens[i]
        high_price = high[i]
        low_price = low[i]
        close = prices[i]
        volume = volumes[i]
        change = changes[i]
        
        log_message = f"Symbol: {symbol}, Date: {date}, Open: {open_price:.2f}, Close: {close:.2f}, High: {high_price:.2f}, Low: {low_price:.2f}, Volume: {volume:.2f}, Change: {change:.2f}"
        logging.debug(log_message)

# Funzione che esegue l'operazione di Random Forest
def operator_manager():
    if len(prices) < 2:
        logging.error("Dati insufficienti per il calcolo.")
        return

    # Creazione dei dati di addestramento per Random Forest
    features = []
    targets = []
    
    for i in range(1, len(prices)):
        sample = [
            opens[i], prices[i], high[i], low[i],
            volumes[i], changes[i]
        ]
        features.append(sample)
        targets.append(1 if prices[i] > prices[i - 1] else 0)
    
    # Addestramento del modello Random Forest
    model = RandomForestClassifier(n_estimators=80, max_depth=8)
    model.fit(features, targets)

    # Previsione per il prossimo giorno
    last_sample = [
        opens[-1], prices[-1], high[-1], low[-1],
        volumes[-1], changes[-1]
    ]
    
    prediction = model.predict([last_sample])
    prediction_probability = model.predict_proba([last_sample])[0][1]  # Probabilità di crescita
    
    prediction_text = f"Probabilità di crescita: {prediction_probability * 100:.2f}%"
    logging.info(prediction_text)

# Esegui il recupero dei dati per un simbolo specifico
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configura il logging
    symbol = "AAPL"  # Cambia simbolo se necessario
    get_stock_data(symbol)
