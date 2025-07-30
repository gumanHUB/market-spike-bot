import os
import time
import threading
import requests
import yfinance as yf
import pandas as pd
from flask import Flask

# ——— Load Telegram credentials from Render environment ———
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# ——— Stocks to Monitor ———
SYMBOLS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]

# ——— Technical Indicator Functions ———
def sma(series, window): 
    return series.rolling(window).mean()

def rsi(series, window=14):
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=window-1, adjust=False).mean()
    avg_loss = loss.ewm(com=window-1, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd(series):
    exp1 = series.ewm(span=12, adjust=False).mean()
    exp2 = series.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

# ——— Send to Telegram ———
def send_alert(text):
    try:
        resp = requests.post(TELEGRAM_URL, data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)
        if resp.status_code != 200:
            print("Telegram Error:", resp.status_code, resp.text)
    except Exception as e:
        print("Telegram exception:", e)

# ——— Analyze one symbol ———
def analyze(symbol):
    df = yf.download(symbol, period="7d", interval="30m", progress=False)
    if df.empty or len(df) < 50:
        print(f"[{symbol}] Not enough data.")
        return

    # Calculate indicators
    df["SMA20"] = sma(df["Close"], 20)
    df["RSI14"] = rsi(df["Close"], 14)
    macd_line, sig_line, hist = macd(df["Close"])
    df["MACD"], df["SIGNAL"], df["HIST"] = macd_line, sig_line, hist
    df["VOL_AVG"] = df["Volume"].rolling(20).mean()

    df.dropna(inplace=True)
    last = df.iloc[-1]

    price   = last.Close
    sma20   = last.SMA20
    rsi14   = last.RSI14
    macd_v  = last.MACD
    sig_v   = last.SIGNAL
    vol     = last.Volume
    vol_avg = last.VOL_AVG

    print(f"[{symbol}] Price={price:.2f}, RSI={rsi14:.1f}, MACD={macd_v:.2f}, Vol={vol}")

    # — High‑Accuracy: strong breakout with volume confirmation —
    if price > sma20 and rsi14 < 30 and macd_v > sig_v and vol > 1.5 * vol_avg:
        send_alert(
            f"📈 *HIGH Spike Detected* — {symbol}\n"
            f"Price: ₹{price:.2f}\n"
            f"RSI14: {rsi14:.1f} (<30)\n"
            f"MACD↑ & Volume Spike"
        )
    elif price < sma20 and rsi14 > 70 and macd_v < sig_v and vol > 1.5 * vol_avg:
        send_alert(
            f"📉 *HIGH Fall Detected* — {symbol}\n"
            f"Price: ₹{price:.2f}\n"
            f"RSI14: {rsi14:.1f} (>70)\n"
            f"MACD↓ & Volume Spike"
        )

    # — Mild‑Accuracy: trend/momentum signals without volume —
    elif price > sma20 and rsi14 < 40 and macd_v > sig_v:
        send_alert(
            f"⚠️ *Mild Bullish Signal* — {symbol}\n"
            f"Price: ₹{price:.2f}\n"
            f"RSI14: {rsi14:.1f}\n"
            f"MACD↑"
        )
    elif price < sma20 and rsi14 > 60 and macd_v < sig_v:
        send_alert(
            f"⚠️ *Mild Bearish Signal* — {symbol}\n"
            f"Price: ₹{price:.2f}\n"
            f"RSI14: {rsi14:.1f}\n"
            f"MACD↓"
        )
    else:
        print(f"[{symbol}] No alert.")

# ——— Bot Loop ———
def run_bot():
    print("Bot started — scanning every 15 minutes.")
    while True:
        for sym in SYMBOLS:
            try:
                analyze(sym)
            except Exception as e:
                print(sym, "analysis error:", e)
        time.sleep(900)  # 15 minutes

# ——— Flask Keep‑Alive ———
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is alive"

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
