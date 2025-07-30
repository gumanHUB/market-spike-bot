import time, threading, requests
import yfinance as yf
import pandas as pd
from flask import Flask

# ——— Telegram Config ———
BOT_TOKEN = "7964796555:AAGt4OdqCaui7HtJBD9QFGz2P8rk3CSMIZ4"
CHAT_ID   = "-1002525487392"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# ——— Stocks to Monitor ———
SYMBOLS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "MARUTI.NS", "HINDUNILVR.NS"]

# ——— Indicator Functions ———
def sma(series, window):
    return series.rolling(window).mean()

def rsi(series, window=14):
    delta = series.diff()
    up, down = delta.clip(lower=0), -delta.clip(upper=0)
    ema_up   = up.ewm(span=window, adjust=False).mean()
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
        res = requests.post(TELEGRAM_URL, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        print("✅ Sent alert:", res.status_code)
    except Exception as e:
        print("Telegram error:", e)

# ——— Analyze One Stock ———
def analyze(symbol):
    df = yf.download(symbol, period="30d", interval="30m", progress=False)
    print(f"[{symbol}] Fetched {len(df)} rows")

    if df.empty or len(df) < 50:
        print(f"[{symbol}] Insufficient data")
        return

    close = df["Close"]
    df["SMA20"] = sma(close, 20)
    df["RSI14"] = rsi(close, 14)
    macd_line, sig_line, hist = macd(close)
    df["MACD"], df["SIGNAL"], df["HIST"] = macd_line, sig_line, hist

    last = df.iloc[-1]
    price, sma20 = last.Close, last.SMA20
    r, m, s = last.RSI14, last.MACD, last.SIGNAL

    # ✅ Debug print to console
    print(f"[{symbol}] Price: {price:.2f}, SMA20: {sma20:.2f}, RSI14: {r:.2f}, MACD: {m:.2f}, SIGNAL: {s:.2f}")

    # ✅ Send test alert unconditionally
    send_alert(f"🚨 *Test Signal*: {symbol}\nPrice: {price:.2f}\nRSI: {r:.1f}\nMACD: {m:.2f} vs {s:.2f}")

# ——— Bot Loop & Web Server ———
def run_bot():
    print("Bot starting — testing alerts every 1 minute…")
    while True:
        for sym in SYMBOLS:
            try:
                analyze(sym)
            except Exception as e:
                print(sym, "error:", e)
        time.sleep(60)  # Test every 1 minute

app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is alive"

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
