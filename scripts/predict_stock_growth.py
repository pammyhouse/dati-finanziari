import requests
from bs4 import BeautifulSoup
from sklearn.ensemble import RandomForestClassifier
import numpy as np
import logging

# Configura il logging per monitorare le operazioni
logging.basicConfig(level=logging.DEBUG)

# Parametri modello
NUM_TREES = 80
MAX_DEPTH = 8

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

def get_stock_data(symbol):
    """
    Funzione per scaricare e analizzare i dati di un asset dal GitHub.
    """
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
    logging.info(f"Probabilità di crescita: {growth_probability * 100:.2f}%")

def main():
    # Esempio: preleva i dati per "AAPL"
    symbol = "AAPL"
    get_stock_data(symbol)
    
    # Prepara i dati e addestra il modello
    features, targets = prepare_features_and_targets()
    if len(features) > 0 and len(targets) > 0:
        model = train_random_forest(features, targets)
        
        # Effettua la previsione e mostra la probabilità di crescita
        predict_growth_probability(model)
    else:
        logging.error("Dati insufficienti per l'addestramento.")

if __name__ == "__main__":
    main()
