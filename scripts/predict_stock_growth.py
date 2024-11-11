import requests
from bs4 import BeautifulSoup
from sklearn.ensemble import RandomForestClassifier
import numpy as np
import logging
import os

# Configura il logging per monitorare le operazioni
logging.basicConfig(level=logging.DEBUG)

# Parametri modello
NUM_TREES = 150
MAX_DEPTH = 15

# URL di esempio per simboli finanziari
SHEET_URL_TEMPLATE = "https://raw.githubusercontent.com/pammyhouse/dati-finanziari/main/{}.html"

# Dati storici
dates = []
opens = []
prices = []
highs = []
lows = []
volumes = []
changes = []

# Lista dei simboli da analizzare
symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK.A", "V", "JPM", "JNJ",
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

# Percorso della cartella per i risultati
RESULTS_FOLDER = "results"

# Crea la cartella per i risultati se non esiste
if not os.path.exists(RESULTS_FOLDER):
    os.makedirs(RESULTS_FOLDER)

def get_stock_data(symbol):
    """
    Funzione per scaricare e analizzare i dati di un asset dal GitHub.
    """
    global dates, opens, prices, highs, lows, volumes, changes
    # Reset delle liste per ogni simbolo
    dates.clear()
    opens.clear()
    prices.clear()
    highs.clear()
    lows.clear()
    volumes.clear()
    changes.clear()

    url = SHEET_URL_TEMPLATE.format(symbol.upper())
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        # Analizza l'HTML
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("table tbody tr")
        
        # Estrai i dati e aggiungili alle liste
        for row in rows:
            columns = row.find_all("td")
            if len(columns) >= 7:
                # Parsing dei dati
                dates.append(columns[0].text)
                opens.append(float(columns[1].text))
                prices.append(float(columns[2].text))
                highs.append(float(columns[3].text))
                lows.append(float(columns[4].text))
                volumes.append(float(columns[5].text))
                changes.append(float(columns[6].text))
        
        logging.info(f"Dati caricati per {symbol}")

    except Exception as e:
        logging.error(f"Errore nel caricamento del file HTML per {symbol}: {e}")

def prepare_features_and_targets():
    """
    Prepara i dati per addestrare il modello di Random Forest.
    """
    features = []
    targets = []
    for i in range(1, len(prices)):
        feature = [opens[i], prices[i], highs[i], lows[i], volumes[i], changes[i]]
        features.append(feature)
        # Il target è 1 se il prezzo aumenta rispetto al giorno precedente, altrimenti 0
        targets.append(1 if prices[i] > prices[i - 1] else 0)
    return np.array(features), np.array(targets)

def train_random_forest(features, targets):
    """
    Addestra il modello Random Forest con i dati forniti.
    """
    model = RandomForestClassifier(n_estimators=NUM_TREES, max_depth=MAX_DEPTH, random_state=42)
    model.fit(features, targets)
    return model

def predict_growth_probability(model):
    """
    Prevede la probabilità di crescita dell'asset usando l'ultimo set di dati.
    """
    last_sample = np.array([[opens[-1], prices[-1], highs[-1], lows[-1], volumes[-1], changes[-1]]])
    growth_probability = model.predict_proba(last_sample)[0][1]
    return growth_probability

def save_to_html(symbol, growth_probability):
    """
    Salva il risultato in un file HTML.
    """
    result_file_path = os.path.join(RESULTS_FOLDER, f"{symbol}_RESULT.htm")
    
    # Contenuto da scrivere nel file HTML
    html_content = f"""
    <html>
        <head>
            <title>Risultato per {symbol}</title>
        </head>
        <body>
            <h1>Probabilità di crescita per {symbol}</h1>
            <p>Probabilità di crescita dell'asset: {growth_probability * 100:.2f}%</p>
        </body>
    </html>
    """
    
    try:
        # Se esiste già un file con lo stesso nome, lo elimina e lo sostituisce
        if os.path.exists(result_file_path):
            os.remove(result_file_path)
        
        with open(result_file_path, "w") as file:
            file.write(html_content)
        logging.info(f"Risultato salvato in {result_file_path}")
    
    except Exception as e:
        logging.error(f"Errore nel salvataggio del file HTML per {symbol}: {e}")

def main():
    for symbol in symbols:
        # Preleva i dati per ogni simbolo
        get_stock_data(symbol)
        
        if len(prices) > 0:
            # Prepara i dati e addestra il modello
            features, targets = prepare_features_and_targets()
            model = train_random_forest(features, targets)
            
            # Prevedi la probabilità di crescita
            growth_probability = predict_growth_probability(model)
            
            # Salva il risultato in un file HTML
            save_to_html(symbol, growth_probability)
        else:
            logging.warning(f"Dati insufficienti per {symbol}. Saltando...")

if __name__ == "__main__":
    main()
