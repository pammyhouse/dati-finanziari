import requests
from bs4 import BeautifulSoup

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
        
        # Liste per contenere i dati
        dates = []
        opens = []
        highs = []
        lows = []
        prices = []
        volumes = []
        changes = []
        
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
        
        # Verifica se i dati sono stati correttamente estratti
        print("Dati caricati correttamente:")
        for i in range(len(dates)):
            print(f"Data: {dates[i]}, Apertura: {opens[i]}, Chiusura: {prices[i]}, Massimo: {highs[i]}, Minimo: {lows[i]}, Volume: {volumes[i]}, Cambiamento: {changes[i]}")
        
        return dates, opens, highs, lows, prices, volumes, changes
    
    except requests.exceptions.RequestException as e:
        print(f"Errore durante il recupero dei dati: {e}")

# Esempio di utilizzo della funzione
symbol = "MSFT"  # Inserisci il simbolo dell'asset
get_stock_data(symbol)
