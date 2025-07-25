import os
import requests
from bs4 import BeautifulSoup
import logging
from xgboost import XGBClassifier  # Import XGBoost
import numpy as np
from github import Github, GithubException
import pandas as pd

FMP_API_KEY = os.getenv("FMP_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "pammyhouse/dati-finanziari"

# Lista per raccogliere i dati finanziari
dates = []
opens = []
highs = []
lows = []
prices = []
volumes = []
changes = []

# Lista globale per memorizzare le probabilità di ciascun simbolo
symbol_probabilities = []

'''stockSymbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "V", "JPM", "JNJ", "WMT",
        "NVDA", "PYPL", "DIS", "NFLX", "NIO", "NRG", "ADBE", "INTC", "CSCO", "PFE",
        "KO", "PEP", "MRK", "ABT", "XOM", "CVX", "T", "MCD", "NKE", "HD",
        "IBM", "CRM", "BMY", "ORCL", "ACN", "LLY", "QCOM", "HON", "COST", "SBUX",
        "CAT", "LOW", "MS", "GS", "AXP", "INTU", "AMGN", "GE", "FIS", "CVS",
        "DE", "BDX", "NOW", "SCHW", "LMT", "ADP", "C", "PLD", "NSC", "TMUS",
        "ITW", "FDX", "PNC", "SO", "APD", "ADI", "ICE", "ZTS", "TJX", "CL",
        "MMC", "EL", "GM", "CME", "EW", "AON", "D", "PSA", "AEP", "TROW", 
        "LNTH", "HE", "BTDR", "NAAS", "SCHL", "TGT", "SYK", "BKNG", "DUK", "USB",
        "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
        "AUDJPY", "CADJPY", "CHFJPY", "EURAUD", "EURNZD", "EURCAD", "EURCHF", "GBPCHF", "GBPJPY", "AUDCAD",
        "BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "BCHUSD", "EOSUSD", "XLMUSD", "ADAUSD", "TRXUSD", "NEOUSD",
        "DASHUSD", "XMRUSD", "ETCUSD", "ZECUSD", "BNBUSD", "DOGEUSD", "USDTUSD", "LINKUSD", "ATOMUSD", "XTZUSD",
        "CCUSD", "XAUUSD", "XAGUSD", "GCUSD", "ZSUSX", "CTUSX", "ZCUSX", "OJUSX", "RBUSD"]'''

stockSymbols = [
    # New Stocks Only
    "BABA",   # Alibaba
    "HTZ",    # Hertz
    "UBER",   # Uber
    "LYFT",   # Lyft
    "PLTR",   # Palantir
    "SNOW",   # Snowflake
    "ROKU",   # Roku
    "TWLO",   # Twilio
    "SQ",     # Square (Block)
    "COIN",   # Coinbase
    "RIVN",   # Rivian
    "LCID",   # Lucid
    "DDOG",   # Datadog
    "NET",    # Cloudflare
    "SHOP",   # Shopify
    "ZI",     # ZoomInfo
    "ZM",     # Zoom Video
    "BIDU",   # Baidu
    "PDD",    # Pinduoduo
    "JD",     # JD.com
    "ARM",    # ARM Holdings
    "DUOL",   # Duolingo
    # Major Indices
    "^GSPC",       # S&P 500
    "^DJI",        # Dow Jones Industrial Average
    "^IXIC",       # Nasdaq Composite
    "^NDX",        # Nasdaq 100
    "^RUT",        # Russell 2000
    "^VIX",        # CBOE Volatility Index

    # European Indices
    "^STOXX50E",   # Euro Stoxx 50
    "^GDAXI",      # DAX (Germany)
    "^FCHI",       # CAC 40 (France)
    "^FTSE",       # FTSE 100 (UK)
    "^SSMI",       # Swiss Market Index
    "^IBEX",       # IBEX 35 (Spain)
    "^AEX",        # AEX Index (Netherlands)

    # Asian Indices
    "^N225",       # Nikkei 225 (Japan)
    "^HSI",        # Hang Seng Index (Hong Kong)
    "000001.SS",   # Shanghai Composite Index (China)
    "^NSEI",       # Nifty 50 (India)
    "^KS11"        # KOSPI (South Korea)
]


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

        # Esegui l'operazione con XGBoost
        operator_manager(symbol)
        
        # Verifica se i dati sono stati correttamente estratti
        print("Dati caricati correttamente:")
        
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


def calculate_technical_indicators():
    df = pd.DataFrame({
        'Open': opens,
        'Close': prices,
        'High': highs,
        'Low': lows,
        'Volume': volumes
    })
    
    # Media Mobile Semplice (SMA)
    df['SMA_20'] = df['Close'].rolling(window=20).mean()

    # Media Mobile Esponenziale (EMA)
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()

    # Relative Strength Index (RSI)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Moving Average Convergence Divergence (MACD)
    df['MACD'] = df['EMA_20'] - df['EMA_20'].ewm(span=26, adjust=False).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

    # Bollinger Bands
    df['Rolling Mean'] = df['Close'].rolling(window=20).mean()
    df['Upper Band'] = df['Rolling Mean'] + 2 * df['Close'].rolling(window=20).std()
    df['Lower Band'] = df['Rolling Mean'] - 2 * df['Close'].rolling(window=20).std()
    
    return df

# Funzione che esegue l'operazione con XGBoost
def operator_manager(symbol):
    if len(prices) < 2:
        logging.error("Dati insufficienti per il calcolo.")
        return

    # Calcolare gli indicatori tecnici
    df = calculate_technical_indicators()

    # Creazione dei dati di addestramento per XGBoost
    features = []
    targets = []
    
    # Iniziamo a calcolare le features a partire da un indice più alto per non avere NaN nei calcoli degli indicatori
    for i in range(20, len(prices)):  # Iniziamo da 20 per evitare NaN da indicatori come SMA e Bollinger Bands
        sample = [
            df['Open'][i], df['Close'][i], df['High'][i], df['Low'][i],
            df['Volume'][i], df['RSI'][i], df['SMA_20'][i], df['EMA_20'][i],
            df['MACD'][i], df['Signal_Line'][i], df['Upper Band'][i], df['Lower Band'][i]
        ]
        features.append(sample)
        targets.append(1 if df['Close'][i] > df['Close'][i - 1] else 0)
    
    # Addestramento del modello XGBoost
    model = XGBClassifier(n_estimators=300, max_depth=8)
    model.fit(features, targets)

    # Previsione per il prossimo giorno
    last_sample = [
        df['Open'].iloc[-1], df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1],
        df['Volume'].iloc[-1], df['RSI'].iloc[-1], df['SMA_20'].iloc[-1], df['EMA_20'].iloc[-1],
        df['MACD'].iloc[-1], df['Signal_Line'].iloc[-1], df['Upper Band'].iloc[-1], df['Lower Band'].iloc[-1]
    ]
    
    prediction = model.predict([last_sample])
    prediction_probability = model.predict_proba([last_sample])[0][1]  # Probabilità di crescita
    
    prediction_text = f"Probabilità di crescita: {prediction_probability * 100:.2f}%"
    logging.debug(prediction_text)
    # Salva la previsione in un file HTML
    github = Github(GITHUB_TOKEN)
    repo = github.get_repo(REPO_NAME)
    upload_prediction_html(repo, symbol, prediction_probability * 100)

# Funzione per caricare e classificare tutte le probabilità
def create_classification_file():
    # Ordina la lista di simboli per probabilità (decrescente) e per nome (alfabetico) in caso di probabilità uguali
    sorted_symbols = sorted(symbol_probabilities, key=lambda x: (-x[1], x[0]))

    # Crea il contenuto del file HTML
    html_content = []
    html_content.append("<html><head><title>Classifica dei Simboli</title></head><body>")
    html_content.append("<h1>Classifica dei Simboli in Base alla Probabilità di Crescita</h1>")
    html_content.append("<table border='1'><tr><th>Simbolo</th><th>Probabilità</th></tr>")
    
    # Aggiungi ogni simbolo e la sua probabilità alla tabella HTML
    for symbol, probability in sorted_symbols:
        html_content.append(f"<tr><td>{symbol}</td><td>{probability:.2f}%</td></tr>")
    
    html_content.append("</table></body></html>")

    # Salva il file HTML nella cartella 'results'
    file_path = "results/classifica.html"
    
    # Salva il file su GitHub
    github = Github(GITHUB_TOKEN)
    repo = github.get_repo(REPO_NAME)
    try:
        contents = repo.get_contents(file_path)
        repo.update_file(contents.path, "Updated classification", "\n".join(html_content), contents.sha)
    except GithubException:
        # Se il file non esiste, creiamo un nuovo file
        repo.create_file(file_path, "Created classification", "\n".join(html_content))
    
    print("Classifica aggiornata con successo!")

# Funzione per salvare la previsione in un file HTML (modificata per registrare la probabilità)
def upload_prediction_html(repo, symbol, probability):
    # Aggiungi la probabilità al dizionario delle probabilità
    symbol_probabilities.append((symbol, probability))

    file_path = f"results/{symbol.upper()}_RESULT.html"

    html_content = []
    html_content.append(f"<html><head><title>Previsione per {symbol}</title></head><body>")
    html_content.append(f"<h1>Previsione per: ({symbol})</h1>")

    html_content.append("<table border='1'><tr><th>Probability</th></tr>")
    html_content.append("<tr>")
    html_content.append(f"<td>{probability}</td>")
    html_content.append("</table></body></html>")
        
    try:
        contents = repo.get_contents(file_path)
        repo.update_file(contents.path, f"Updated probability for {symbol}", "\n".join(html_content), contents.sha)
    except Exception as e:
        # Se il file non esiste, lo creiamo
        repo.create_file(file_path, f"Created probability for {symbol}", "\n".join(html_content))

# Funzione principale che carica i dati e esegue le operazioni per ogni simbolo
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

    # Dopo aver completato il processo per tutti i simboli, creiamo la classifica
    create_classification_file()
