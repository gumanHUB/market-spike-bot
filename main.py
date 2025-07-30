import time, threading, requests, os
import yfinance as yf
import pandas as pd
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

# ——— Secure Telegram Config ———
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# ——— Stocks to Monitor ———
SYMBOLS = ["RELIANCE.NS","TCS.NS","HDFCBANK.NS","MARUTI.NS","HINDUNILVR.NS"]

# ——— Indicator Functions ———
def sma(series, window):
    return series.rolling(window).mean()

def rsi(series, window=14):
    delta = series.diff()
    up, down = delta.clip(lower=0), -delta.clip(upper=0)
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

# ——— Telegram Alert ———
def send_alert(msg):
    try:
        requests.post(TELEGRAM_URL, data={"chat_id": CHAT_ID, "text": msg, "parse_mode":"Markdown"})
    except Exception as e:
        print("Telegram error:", e)

# ——— Analyze One Stock ———
def analyze(symbol):
    df = yf.download(symbol, period="7d", interval="30m", progress=False)
    if df.empty or len(df) < 50:
        print(f"[{symbol}] Not enough data")
        return

    close = df["Close"]
    df["SMA20"] = sma(close, 20)
    df["RSI14"] = rsi(close, 14)
    macd_line, sig_line, hist = macd(close)
    df["MACD"], df["SIGNAL"], df["HIST"] = macd_line, sig_line, hist
    df.dropna(inplace=True)

    last = df.iloc[-1]
    price, sma20 = last.Close, last.SMA20
    r, m, s = last.RSI14, last.MACD, last.SIGNAL

    print(f"[{symbol}] Price: {price:.2f}, SMA: {sma20:.2f}, RSI: {r:.2f}, MACD: {m:.2f}, SIGNAL: {s:.2f}")

    if price > sma20 and r < 40 and m > s:
        send_alert(f"📈 *Test Bullish Alert*: {symbol}\nPrice: {price:.2f}\nRSI: {r:.1f}\nMACD ↑")
    elif price < sma20 and r > 60 and m < s:
        send_alert(f"📉 *Test Bearish Alert*: {symbol}\nPrice: {price:.2f}\nRSI: {r:.1f}\nMACD ↓")
    else:
        print(f"[{symbol}] No signal")

# ——— Bot Loop ———
def run_bot():
    print("Bot started — checking every 1 min (TEST MODE)…")
    while True:
        for sym in SYMBOLS:
            try:
                analyze(sym)
            except Exception as e:
                print(f"{sym} error:", e)
        time.sleep(60)

# ——— Web Server for Render ———
app = Flask(__name__)
@app.route('/')
def home():
    return "Stock Alert Bot Running"

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
