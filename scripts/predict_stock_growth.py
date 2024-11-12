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

# Funzione per recuperare i dati dal file HTML
def get_stock_data(symbol):
    url = f"https://raw.githubusercontent.com/pammyhouse/dati-finanziari/main/{symbol.upper()}.html"
    
    try:
        # Scarica il contenuto della pagina HTML
        response = requests.get(url)
        response.raise_for_status()  # Verifica che la richiesta sia andata a buon fine
        
        # Analizza il contenuto HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Trova la tabella con i dati
        table = soup.find('table')  # Trova la prima tabella nella pagina
        
        # Trova tutte le righe della tabella (tr)
        rows = table.find_all('tr')[1:]  # Ignora la prima riga, che è l'intestazione
        
        # Itera attraverso ogni riga della tabella
        for row in rows:
            cols = row.find_all('td')  # Estrai tutte le celle (td) della riga
            
            if len(cols) >= 7:  # Assicurati che ci siano almeno 7 colonne (come previsto)
                date = cols[0].text.strip()  # Estrai la data
                open_price = float(cols[1].text.strip())  # Estrai il prezzo di apertura
                close_price = float(cols[2].text.strip())  # Estrai il prezzo di chiusura
                high_price = float(cols[3].text.strip())  # Estrai il prezzo massimo
                low_price = float(cols[4].text.strip())  # Estrai il prezzo minimo
                volume = float(cols[5].text.strip())  # Estrai il volume
                change = float(cols[6].text.strip())  # Estrai il cambiamento
                
                # Aggiungi i valori alle liste
                dates.append(date)
                opens.append(open_price)
                highs.append(high_price)
                lows.append(low_price)
                prices.append(close_price)
                volumes.append(volume)
                changes.append(change)

        # Dopo aver caricato i dati, invertiamo l'ordine per processarli dalla più vecchia alla più recente
        reverse_data()

        # Stampa i dati (log)
        log_daily_data(symbol)
        
        # Esegui l'operazione con Random Forest
        operator_manager()
        
        # Verifica se i dati sono stati correttamente estratti
        print("Dati caricati correttamente:")
        for i in range(len(dates)):
            print(f"Data: {dates[i]}, Apertura: {opens[i]}, Chiusura: {prices[i]}, Massimo: {highs[i]}, Minimo: {lows[i]}, Volume: {volumes[i]}, Cambiamento: {changes[i]}")
        
        #return dates, opens, highs, lows, prices, volumes, changes
    
    except requests.exceptions.RequestException as e:
        print(f"Errore durante il recupero dei dati: {e}")
    

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
