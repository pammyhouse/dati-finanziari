import requests
from bs4 import BeautifulSoup
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import logging
import random

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# List of stock symbols
stock_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK.A", "V", "JPM", "JNJ",
                 "WMT", "NVDA", "PYPL", "DIS", "NFLX", "NIO", "NRG", "ADBE", "INTC", "CSCO", "PFE", "VZ",
                 "KO", "PEP", "MRK", "ABT", "XOM", "CVX", "T", "MCD", "NKE", "HD", "IBM", "CRM", "BMY",
                 "ORCL", "ACN", "LLY", "QCOM", "HON", "COST", "SBUX", "MDT", "TXN", "MMM", "NEE", "PM", "BA",
                 "UNH", "MO", "DHR", "SPGI", "CAT", "LOW", "MS", "GS", "AXP", "INTU", "AMGN", "GE", "FIS",
                 "CVS", "TGT", "ANTM", "SYK", "BKNG", "MDLZ", "BLK", "DUK", "USB", "ISRG", "CI", "DE", "BDX",
                 "NOW", "SCHW", "LMT", "ADP", "C", "PLD", "NSC", "TMUS", "EURUSD", "USDJPY", "GBPUSD", "AUDUSD",
                 "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "DASHUSD", "XMRUSD", "ETCUSD", 
                 "ZECUSD", "BNBUSD", "DOGEUSD", "USDTUSD", "ITW", "FDX", "PNC", "SO", "APD", "ADI", "ICE",
                 "ZTS", "TJX", "CL", "MMC", "EL", "GM", "CME", "EW", "AON", "D", "PSA", "AEP", "TROW"]

# Define function to fetch stock data
def get_stock_data(symbol):
    url = f"https://raw.githubusercontent.com/pammyhouse/dati-finanziari/main/{symbol.upper()}.html"
    
    try:
        # Fetch the data
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception if the request was unsuccessful
        
        # Parse the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.select('table tbody tr')
        
        data = []
        
        # Process the data rows
        for row in rows:
            columns = row.find_all('td')
            if len(columns) >= 7:
                date = columns[0].text.strip()
                open_price = float(columns[1].text.strip())
                close_price = float(columns[2].text.strip())
                high_price = float(columns[3].text.strip())
                low_price = float(columns[4].text.strip())
                volume = float(columns[5].text.strip())
                change = float(columns[6].text.strip())
                
                # Append data to list
                data.append([date, open_price, close_price, high_price, low_price, volume, change])
        
        # Return data as DataFrame
        df = pd.DataFrame(data, columns=['Date', 'Open', 'Close', 'High', 'Low', 'Volume', 'Change'])
        return df
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching data for {symbol}: {e}")
        return None

# Function to log daily data
def log_daily_data(symbol, df):
    for _, row in df.iterrows():
        log_message = f"Symbol: {symbol}, Date: {row['Date']}, Open: {row['Open']}, Close: {row['Close']}, " \
                      f"High: {row['High']}, Low: {row['Low']}, Volume: {row['Volume']}, Change: {row['Change']}"
        logging.debug(log_message)

# Train a Random Forest Model
def train_random_forest(df):
    # Prepare feature columns and target
    features = df[['Open', 'Close', 'High', 'Low', 'Volume', 'Change']].values
    target = (df['Close'] > df['Open']).astype(int)  # 1 if close > open, else 0
    
    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(features, target, test_size=0.2, random_state=42)
    
    # Train the Random Forest model
    model = RandomForestClassifier(n_estimators=80, max_depth=8, random_state=42)
    model.fit(X_train, y_train)
    
    # Evaluate the model
    accuracy = model.score(X_test, y_test)
    logging.info(f"Model Accuracy: {accuracy * 100:.2f}%")
    
    return model

# Predict stock growth for the next day
def predict_growth(model, df):
    last_sample = df.iloc[-1][['Open', 'Close', 'High', 'Low', 'Volume', 'Change']].values
    growth_probability = model.predict_proba([last_sample])[0][1]  # Probability of class 1 (growth)
    logging.info(f"Probability of growth: {growth_probability * 100:.2f}%")
    return growth_probability

# Main function to simulate the workflow
def main():
    symbol = 'AAPL'  # Example: use AAPL as the stock symbol
    df = get_stock_data(symbol)
    
    if df is not None:
        log_daily_data(symbol, df)
        model = train_random_forest(df)
        growth_probability = predict_growth(model, df)
        
        print(f"Prediction for {symbol}: Probability of growth = {growth_probability * 100:.2f}%")

if __name__ == "__main__":
    main()
