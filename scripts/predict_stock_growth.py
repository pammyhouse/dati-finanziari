import requests
from bs4 import BeautifulSoup
import pandas as pd

# Dati delle azioni
prices = []
opens = []
high = []
low = []
volumes = []
changes = []
dates = []

num_trees = 80  # Numero di alberi nella foresta
max_depth = 8   # Profondità massima per ciascun albero

stock_symbols = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK.A", "V", "JPM", "JNJ",
    "WMT", "NVDA", "PYPL", "DIS", "NFLX", "NIO", "NRG", "ADBE", "INTC", "CSCO", "PFE", "VZ",
    "KO", "PEP", "MRK", "ABT", "XOM", "CVX", "T", "MCD", "NKE", "HD",
    "IBM", "CRM", "BMY", "ORCL", "ACN", "LLY", "QCOM", "HON", "COST", "SBUX",
    "MDT", "TXN", "MMM", "NEE", "PM", "BA", "UNH", "MO", "DHR", "SPGI",
    "CAT", "LOW", "MS", "GS", "AXP", "INTU", "AMGN", "GE", "FIS", "CVS",
    "TGT", "ANTM", "SYK", "BKNG", "MDLZ", "BLK", "DUK", "USB", "ISRG", "CI",
    "DE", "BDX", "NOW", "SCHW", "LMT", "ADP", "C", "PLD", "NSC", "TMUS",
    "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
    "DASHUSD", "XMRUSD", "ETCUSD", "ZECUSD", "BNBUSD", "DOGEUSD", "USDTUSD",
    "ITW", "FDX", "PNC", "SO", "APD", "ADI", "ICE", "ZTS", "TJX", "CL",
    "MMC", "EL", "GM", "CME", "EW", "AON", "D", "PSA", "AEP", "TROW"
]

def get_stock_data(symbol):
    url = f"https://raw.githubusercontent.com/pammyhouse/dati-finanziari/main/{symbol.upper()}.html"
    
    # Richiesta HTTP per scaricare il contenuto HTML
    try:
        response = requests.get(url)
        response.raise_for_status()  # Verifica che la richiesta abbia avuto successo
        
        # Parsing del documento HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.select("table tbody tr")  # Selettore per le righe della tabella
        
        # Estrazione dei dati dalle righe della tabella
        for row in rows:
            columns = row.select("td")
            if len(columns) >= 7:
                date = columns[0].get_text()
                open_price = float(columns[1].get_text())
                close_price = float(columns[2].get_text())
                high_price = float(columns[3].get_text())
                low_price = float(columns[4].get_text())
                volume = float(columns[5].get_text())
                change = float(columns[6].get_text())

                # Aggiungi i dati alle rispettive liste
                dates.append(date)
                opens.append(open_price)
                high.append(high_price)
                low.append(low_price)
                prices.append(close_price)
                volumes.append(volume)
                changes.append(change)

        # Inverti l'ordine delle liste (simile alla funzione Collections.reverse())
        prices.reverse()
        high.reverse()
        low.reverse()
        opens.reverse()
        volumes.reverse()
        changes.reverse()

        print(f"Dati caricati correttamente per {symbol.upper()}")

        # Esegui altre elaborazioni o salvataggi se necessario
        log_daily_data(symbol.upper())

    except requests.exceptions.RequestException as e:
        print(f"Errore nel caricamento dei dati per {symbol.upper()}: {e}")

def log_daily_data(symbol):
    # Funzione per loggare i dati giornalieri
    print(f"Log dei dati giornalieri per {symbol}:")
    for i in range(len(dates)):
        print(f"{dates[i]} - Open: {opens[i]}, High: {high[i]}, Low: {low[i]}, Close: {prices[i]}, Volume: {volumes[i]}, Change: {changes[i]}")

# Esempio di utilizzo con il primo simbolo
get_stock_data("AAPL")
