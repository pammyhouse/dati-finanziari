import requests
from github import Github
import os

FMP_API_KEY = os.getenv("FMP_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "pammyhouse/dati-finanziari"

stock_symbols = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "V", "JPM", "JNJ", "WMT",
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
        "CCUSD", "XAUUSD", "XAGUSD", "GCUSD", "ZSUSX", "CTUSX", "ZCUSX", "OJUSX", "RBUSD"
    ]

    only_actions = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "V", "JPM", "JNJ", "WMT",
        "NVDA", "PYPL", "DIS", "NFLX", "NIO", "NRG", "ADBE", "INTC", "CSCO", "PFE",
        "KO", "PEP", "MRK", "ABT", "XOM", "CVX", "T", "MCD", "NKE", "HD",
        "IBM", "CRM", "BMY", "ORCL", "ACN", "LLY", "QCOM", "HON", "COST", "SBUX",
        "CAT", "LOW", "MS", "GS", "AXP", "INTU", "AMGN", "GE", "FIS", "CVS",
        "DE", "BDX", "NOW", "SCHW", "LMT", "ADP", "C", "PLD", "NSC", "TMUS",
        "ITW", "FDX", "PNC", "SO", "APD", "ADI", "ICE", "ZTS", "TJX", "CL",
        "MMC", "EL", "GM", "CME", "EW", "AON", "D", "PSA", "AEP", "TROW", 
        "LNTH", "HE", "BTDR", "NAAS", "SCHL", "TGT", "SYK", "BKNG", "DUK", "USB"
    ]

def fetch_company_profile(symbol):
    # Recupera i dati della compagnia solo per i simboli in only_actions
    if symbol in only_actions:
        response = requests.get(f"https://financialmodelingprep.com/api/v3/profile/{symbol}", params={"apikey": FMP_API_KEY})
        if response.ok:
            profile_data = response.json()
            if profile_data:
                return profile_data[0]
    return {
        "companyName": "",
        "description": "",
        "image": ""
    }

def fetch_stock_data(symbol):
    response = requests.get(f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}", params={"apikey": FMP_API_KEY})
    if response.ok:
        return response.json()
    else:
        print(f"Errore nel recupero dei dati per {symbol}")
        return None

def generate_html(symbol, company_data, historical_data):
    company_name = company_data.get("companyName", "N/A")
    description = company_data.get("description", "")
    image_url = company_data.get("image", "")

    html_content = []
    html_content.append(f"<html><head><title>Dati Finanziari per {company_name}</title></head><body>")
    html_content.append(f"<h1>Dati finanziari per: {company_name} ({symbol})</h1>")

    if image_url:
        html_content.append(f"<img src='{image_url}' alt='{company_name} logo' style='width:100px;height:auto;'/>")
    if description:
        html_content.append(f"<p>{description}</p>")

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
    try:
        contents = repo.get_contents(file_path)
        repo.update_file(contents.path, f"Updated data for {symbol}", html_content, contents.sha)
    except Exception as e:
        # Se il file non esiste, lo creiamo
        repo.create_file(file_path, f"Created data for {symbol}", html_content)

def main():
    github = Github(GITHUB_TOKEN)
    repo = github.get_repo(REPO_NAME)

    for symbol in stock_symbols:
        company_profile = fetch_company_profile(symbol)
        stock_data = fetch_stock_data(symbol)
        
        html_content = generate_html(symbol, company_profile, stock_data)

        upload_html_file(repo, symbol, html_content)
        print(f"Dati finanziari per {symbol} aggiornati e caricati.")

if __name__ == "__main__":
    main()

