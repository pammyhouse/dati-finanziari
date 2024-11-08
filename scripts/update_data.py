
import requests
from github import Github
import os

FMP_API_KEY = os.getenv("FMP_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "pammyhouse/dati-finanziari"  # Sostituisci con il nome del tuo repository


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




def generate_html(symbol, data):
    html_content = f"<html><head><title>{symbol} Data</title></head><body>"
    html_content += f"<h1>Financial Data for {symbol}</h1><table border='1'><tr><th>Date</th><th>Open</th><th>Close</th></tr>"
    for entry in data["historical"][:5]:  # Limita i dati per esempio
        html_content += f"<tr><td>{entry['date']}</td><td>{entry['open']}</td><td>{entry['close']}</td></tr>"
    html_content += "</table></body></html>"
    return html_content


def upload_html_file(repo, symbol, html_content):
    file_path = f"{symbol}.html"
    repo.create_file(file_path, f"Updated data for {symbol}", html_content)



#Funzione principale
def main():
    github = Github(GITHUB_TOKEN)
    repo = github.get_repo(REPO_NAME)

    # Elimina file esistenti
    delete_old_files(repo)

    # Lista dei simboli da aggiornare
    stock_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]
    for symbol in stock_symbols:
        data = fetch_stock_data(symbol)
        if data:
            html_content = generate_html(symbol, data)
            upload_html_file(repo, symbol, html_content)

if __name__ == "__main__":
    main()







