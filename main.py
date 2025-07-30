import os
import time
import threading
import requests
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from flask import Flask

# ——— Load Secrets ———
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# ——— Stock List (Test) ———
SYMBOLS = ["RELIANCE.NS", "TCS.NS"]

# ——— Indicators ———
def sma(series, window):
    return series.rolling(window).mean()

def rsi(series, window=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ema_up = up.ewm(span=window, adjust=False).mean()
    ema_down = down.ewm(span=window, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

def macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

# ——— Send Telegram Alert ———
def send_alert(message):
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(TELEGRAM_URL, data=payload)
        print("Alert sent:", res.status_code)
    except Exception as e:
        print("Telegram Error:", e)

# ——— Analyze ———
def analyze(symbol):
    print(f"Checking {symbol}...")
    df = yf.download(symbol, period="15d", interval="30m", progress=False)

    if df.empty or len(df) < 50:
        print(f"[{symbol}] Insufficient data")
        return

    close = df["Close"]
    df["SMA20"] = sma(close, 20)
    df["RSI14"] = rsi(close, 14)
    macd_line, sig_line, hist = macd(close)
    df["MACD"], df["SIGNAL"], df["HIST"] = macd_line, sig_line, hist
    df.dropna(inplace=True)

    last = df.iloc[-1]
    price = last["Close"]
    rsi_val = last["RSI14"]

    # 💡 For testing: Alert if RSI is between 40–60 (neutral zone)
    if 40 < rsi_val < 60:
        send_alert(f"🔔 *Test Alert*: {symbol}\nPrice: ₹{price:.2f}\nRSI: {rsi_val:.2f}")
    else:
        print(f"[{symbol}] No signal yet")

# ——— Bot Loop ———
def run_bot():
    print("Bot starting — testing alerts every 1 minute…")
    while True:
        for symbol in SYMBOLS:
            try:
                analyze(symbol)
            except Exception as e:
                print(f"{symbol} error: {e}")
        time.sleep(60)  # test faster

# ——— Web Server to keep alive ———
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is alive"

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
