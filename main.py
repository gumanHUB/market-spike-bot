import time, threading, requests
import yfinance as yf
from flask import Flask
import os

# Load from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# Stocks
SYMBOLS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]

def send_alert(msg):
    try:
        response = requests.post(TELEGRAM_URL, data={"chat_id": CHAT_ID, "text": msg})
        print("Sent:", msg)
    except Exception as e:
        print("Telegram error:", e)

def test_price(symbol):
    df = yf.download(symbol, period="1d", interval="1m", progress=False)
    if df.empty:
        print(f"[{symbol}] No data")
        return
    price = float(df["Close"].iloc[-1])
    msg = f"🔔 {symbol} Latest Price: ₹{price:.2f}"
    send_alert(msg)

def run_test():
    print("Test Bot Running…")
    while True:
        for sym in SYMBOLS:
            test_price(sym)
        time.sleep(300)  # 5 min

# Flask app to keep alive
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is active"

if __name__ == "__main__":
    threading.Thread(target=run_test, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
