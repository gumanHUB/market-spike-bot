import os, time, threading, requests, yfinance as yf, pandas as pd
from flask import Flask

# Load from Render environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID   = os.environ.get("CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

SYMBOLS = ["RELIANCE.NS", "TCS.NS"]

def send_alert(msg):
    try:
        requests.post(TELEGRAM_URL, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram error:", e)

def analyze(symbol):
    df = yf.download(symbol, period="7d", interval="30m", progress=False)
    if df.empty or len(df) < 20:
        print(f"[{symbol}] Not enough data")
        return

    price = df["Close"].iloc[-1]
    sma = df["Close"].rolling(5).mean().iloc[-1]

    print(f"{symbol} | Price: {price:.2f} | SMA: {sma:.2f}")

    if price > sma:
        send_alert(f"📈 Test Spike Alert for {symbol}\nPrice above short SMA.")
    elif price < sma:
        send_alert(f"📉 Test Drop Alert for {symbol}\nPrice below short SMA.")

def run_bot():
    print("Test Bot running every 1 min...")
    while True:
        for symbol in SYMBOLS:
            try:
                analyze(symbol)
            except Exception as e:
                print(f"{symbol} Error:", e)
        time.sleep(60)

app = Flask(__name__)
@app.route('/')
def home():
    return "Test bot is alive."

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
