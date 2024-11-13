import os
import requests
from bs4 import BeautifulSoup
import logging
from sklearn.ensemble import RandomForestClassifier
import numpy as np
from github import Github, GithubException

# Creazione del repository GitHub usando il token

g = Github(os.getenv("GITHUB_TOKEN"))
repo = g.get_repo("pammyhouse/dati-finanziari")

# Lista per raccogliere i dati finanziari
dates = []
opens = []
highs = []
lows = []
prices = []
volumes = []
changes = []


stockSymbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK.A", "V", "JPM", "JNJ",
        "WMT", "NVDA", "PYPL", "DIS", "NFLX", "NIO", "NRG", "ADBE", "INTC", "CSCO",
        "PFE", "VZ", "KO", "PEP", "MRK", "ABT", "XOM", "CVX", "T", "MCD", "NKE", "HD",
        "IBM", "CRM", "BMY", "ORCL", "ACN", "LLY", "QCOM", "HON", "COST", "SBUX",
        "MDT", "TXN", "MMM", "NEE", "PM", "BA", "UNH", "MO", "DHR", "SPGI",
        "CAT", "LOW", "MS", "GS", "AXP", "INTU", "AMGN", "GE", "FIS", "CVS",
        "TGT", "ANTM", "SYK", "BKNG", "MDLZ", "BLK", "DUK", "USB", "ISRG", "CI",
        "DE", "BDX", "NOW", "SCHW", "LMT", "ADP", "C", "PLD", "NSC", "TMUS",
        "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
        "DASHUSD", "XMRUSD", "ETCUSD", "ZECUSD", "BNBUSD", "DOGEUSD", "USDTUSD",
        "ITW", "FDX", "PNC", "SO", "APD", "ADI", "ICE", "ZTS", "TJX", "CL",
        "MMC", "EL", "GM", "CME", "EW", "AON", "D", "PSA", "AEP", "TROW"]

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
        #log_daily_data(symbol)
        
        # Esegui l'operazione con Random Forest
        operator_manager(symbol)
        
        # Verifica se i dati sono stati correttamente estratti
        print("Dati caricati correttamente:")
        #for i in range(len(dates)):
            #print(f"Data: {dates[i]}, Apertura: {opens[i]}, Chiusura: {prices[i]}, Massimo: {highs[i]}, Minimo: {lows[i]}, Volume: {volumes[i]}, Cambiamento: {changes[i]}")
        
        #return dates, opens, highs, lows, prices, volumes, changes
    
    except requests.exceptions.RequestException as e:
        print(f"Errore durante il recupero dei dati: {e}")
    

# Funzione per invertire l'ordine dei dati
def reverse_data():
    global prices, highs, lows, opens, volumes, changes
    prices = prices[::-1]
    highs = highs[::-1]
    lows = lows[::-1]
    opens = opens[::-1]
    volumes = volumes[::-1]
    changes = changes[::-1]

# Funzione per stampare i dati giornalieri (log)
def log_daily_data(symbol):
    for i in range(len(dates)):
        date = dates[i]
        open_price = opens[i]
        high_price = highs[i]
        low_price = lows[i]
        close = prices[i]
        volume = volumes[i]
        change = changes[i]
        
        log_message = f"Symbol: {symbol}, Date: {date}, Open: {open_price:.2f}, Close: {close:.2f}, High: {high_price:.2f}, Low: {low_price:.2f}, Volume: {volume:.2f}, Change: {change:.2f}"
        logging.debug(log_message)

# Funzione che esegue l'operazione di Random Forest
def operator_manager(symbol):
    if len(prices) < 2:
        logging.error("Dati insufficienti per il calcolo.")
        return

    # Creazione dei dati di addestramento per Random Forest
    features = []
    targets = []
    
    for i in range(1, len(prices)):
        sample = [
            opens[i], prices[i], highs[i], lows[i],
            volumes[i], changes[i]
        ]
        features.append(sample)
        targets.append(1 if prices[i] > prices[i - 1] else 0)
    
    # Addestramento del modello Random Forest
    model = RandomForestClassifier(n_estimators=80, max_depth=8)
    model.fit(features, targets)

    # Previsione per il prossimo giorno
    last_sample = [
        opens[-1], prices[-1], highs[-1], lows[-1],
        volumes[-1], changes[-1]
    ]
    
    prediction = model.predict([last_sample])
    prediction_probability = model.predict_proba([last_sample])[0][1]  # Probabilità di crescita
    
    prediction_text = f"Probabilità di crescita: {prediction_probability * 100:.2f}%"
    logging.debug(prediction_text)
    # Salva la previsione in un file HTML
    upload_prediction_html(repo, symbol, prediction_probability)

# Funzione per salvare la previsione in un file HTML
def upload_prediction_html(repo, symbol, probability):
    # Specifica il percorso nella cartella results del repository
    file_path = f"results/{symbol}.RESULT.html"
    
    # Contenuto HTML del file di previsione
    html_content = f"""
    <html>
        <head><title>Prediction Result for {symbol}</title></head>
        <body>
            <h1>Prediction Result for {symbol}</h1>
            <p>Prediction: {"Growth" if probability >= 51 else "Decline"}</p>
            <p>Probability of Growth: {probability * 100:.2f}%</p>
        </body>
    </html>
    """
    
    try:
        # Tenta di ottenere il contenuto del file per vedere se esiste
        contents = repo.get_contents(file_path)
        # Se il file esiste, lo aggiorna
        repo.update_file(contents.path, f"Updated prediction for {symbol}", html_content, contents.sha)
        logging.info(f"Updated prediction for {symbol} in {file_path}")
    except Exception as e:
        # Se il file non esiste, lo crea
        repo.create_file(file_path, f"Created prediction for {symbol}", html_content)
        logging.info(f"Created prediction for {symbol} in {file_path}")

# Esegui il recupero dei dati per ogni simbolo nella lista stockSymbols
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configura il logging
    for symbol in stockSymbols:
        get_stock_data(symbol)
        dates = []
        opens = []
        highs = []
        lows = []
        prices = []
        volumes = []
        changes = []
