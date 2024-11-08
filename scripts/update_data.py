import requests
from github import Github
import os

FMP_API_KEY = os.getenv("FMP_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "pammyhouse/dati-finanziari"

def fetch_company_profile(symbol):
    response = requests.get(f"https://financialmodelingprep.com/api/v3/profile/{symbol}", params={"apikey": FMP_API_KEY})
    if response.ok:
        profile_data = response.json()
        if profile_data:
            return profile_data[0]
    print(f"Errore nel recupero del profilo per {symbol}")
    return None

def fetch_stock_data(symbol):
    response = requests.get(f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}", params={"apikey": FMP_API_KEY})
    if response.ok:
        return response.json()
    else:
        print(f"Errore nel recupero dei dati per {symbol}")
        return None

def delete_old_files(repo):
    contents = repo.get_contents("")
    for content in contents:
        if content.name.endswith(".html"):
            repo.delete_file(content.path, "Deleting old data", content.sha)

def generate_html(symbol, company_data, historical_data):
    company_name = company_data.get("companyName", "N/A")
    description = company_data.get("description", "")
    image_url = company_data.get("image", "")

    html_content = []
    html_content.append(f"<html><head><title>Dati Finanziari per {company_name}</title></head><body>")
    html_content.append(f"<h1>Dati finanziari per: {company_name} ({symbol})</h1>")

    # Aggiungi immagine e descrizione
    if image_url:
        html_content.append(f"<img src='{image_url}' alt='{company_name} logo' style='width:100px;height:auto;'/>")
    if description:
        html_content.append(f"<p>{description}</p>")

    # Crea tabella per i dati storici
    html_content.append("<table border='1'><tr><th>Data</th><th>Apertura</th><th>Chiusura</th><th>Massimo</th><th>Minimo</th><th>Volume</th><th>Cambiamento</th></tr>")
    for entry in historical_data["historical"]:
        html_content.append("<tr>")
        html_content.append(f"<td>{entry['date']}</td>")
        html_content.append(f"<td>{entry['open']}</td>")
        html_content.append(f"<td>{entry['close']}</td>")
        html_content.append(f"<td>{entry['high']}</td>")
        html_content.append(f"<td>{entry['low']}</td>")
        html_content.append(f"<td>{entry['volume']}</td>")
        html_content.append(f"<td>{entry.get('change', 'N/A')}</td>")
        html_content.append("</tr>")
    html_content.append("</table></body></html>")
    
    return "\n".join(html_content)

def upload_html_file(repo, symbol, html_content):
    file_path = f"{symbol}.html"
    repo.create_file(file_path, f"Updated data for {symbol}", html_content)

def main():
    github = Github(GITHUB_TOKEN)
    repo = github.get_repo(REPO_NAME)

    # Elimina i vecchi file
    delete_old_files(repo)

    # Lista dei simboli da aggiornare
    stock_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK.A", "V", "JPM", "JNJ",
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
    for symbol in stock_symbols:
        # Step 1: Recupera profilo della compagnia
        company_profile = fetch_company_profile(symbol)
        if not company_profile:
            continue

        # Step 2: Recupera dati storici
        stock_data = fetch_stock_data(symbol)
        if not stock_data:
            continue

        # Step 3: Genera contenuto HTML
        html_content = generate_html(symbol, company_profile, stock_data)

        # Step 4: Carica il file HTML su GitHub
        upload_html_file(repo, symbol, html_content)
        print(f"Dati finanziari per {symbol} aggiornati e caricati.")

if __name__ == "__main__":
    main()







