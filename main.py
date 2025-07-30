import os, time, threading, requests
import yfinance as yf
from flask import Flask

# Telegram credentials from Render Environment tab
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# Stock symbols to monitor
SYMBOLS = ["RELIANCE.NS", "TCS.NS"]

# Send message to Telegram
def send_telegram_message(message):
    try:
        res = requests.post(TELEGRAM_URL, data={
            "chat_id": CHAT_ID,
            "text": message
        })
        print("Sent:", message)
    except Exception as e:
        print("Telegram error:", e)

# Simple function to get latest price
def analyze(symbol):
    try:
        df = yf.download(symbol, period="1d", interval="1m", progress=False)
        if df.empty:
            print(f"[{symbol}] No data")
            return
        price = df["Close"].iloc[-1]
        send_telegram_message(f"🔔 {symbol} Latest Price: ₹{price:.2f}")
    except Exception as e:
        print(f"{symbol} error:", e)

# Repeated background job
def run_bot():
    print("Test Bot Running…")
    while True:
        for sym in SYMBOLS:
            analyze(sym)
        time.sleep(60)

# Keep bot alive on Render
app = Flask(__name__)
@app.route('/')
def home():
    return "Simple test bot is running."

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
