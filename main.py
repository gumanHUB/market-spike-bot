import os
import time
import threading
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time
import pytz
from flask import Flask, jsonify
# Initialize logger
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
# Initialize Flask app
app = Flask(__name__)
# ——— Configuration ———
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage" if BOT_TOKEN else ""
# Stocks to monitor - Top 10 Indian stocks
SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LT.NS"
]
# Market configuration
IST = pytz.timezone('Asia/Kolkata')
MARKET_OPEN = dt_time(9, 15)  # 9:15 AM IST
MARKET_CLOSE = dt_time(15, 30)  # 3:30 PM IST
SCAN_INTERVAL = 900  # 15 minutes
# Technical analysis parameters
SMA_PERIOD = 20
RSI_PERIOD = 14
VOLUME_MULTIPLIER = 1.5
# Global variables for tracking
bot_status = {
    "running": False,
    "last_scan": None,
    "total_scans": 0,
    "errors": 0,
    "last_error": None,
    "telegram_enabled": bool(BOT_TOKEN and CHAT_ID)
}
# ——— Utility Functions ———
def is_market_open():
    """Check if Indian stock market is currently open"""
    now = datetime.now(IST)
    current_time = now.time()
    current_day = now.weekday()
    
    # Check if it's a weekday (Monday=0, Sunday=6)
    if current_day >= 5:  # Saturday or Sunday
        return False
    
    # Check if current time is within market hours
    return MARKET_OPEN <= current_time <= MARKET_CLOSE
def send_telegram_alert(message):
    """Send alert message to Telegram"""
    if not bot_status["telegram_enabled"]:
        logger.info(f"Telegram disabled - Would send: {message[:50]}...")
        return True
    
    try:
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(TELEGRAM_URL, data=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"Alert sent successfully: {message[:50]}...")
            return True
        else:
            logger.error(f"Telegram API error: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("Telegram request timed out")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Telegram request failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending alert: {e}")
        return False
# ——— Technical Analysis Functions ———
def calculate_sma(series, window):
    """Calculate Simple Moving Average"""
    try:
        return series.rolling(window=window, min_periods=window).mean()
    except Exception as e:
        logger.error(f"Error calculating SMA: {e}")
        return pd.Series(index=series.index, dtype=float)
def calculate_rsi(series, window=14):
    """Calculate Relative Strength Index"""
    try:
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        avg_gain = gain.ewm(com=window-1, adjust=False).mean()
        avg_loss = loss.ewm(com=window-1, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    except Exception as e:
        logger.error(f"Error calculating RSI: {e}")
        return pd.Series(index=series.index, dtype=float)
def calculate_macd(series, fast=12, slow=26, signal=9):
    """Calculate MACD (Moving Average Convergence Divergence)"""
    try:
        exp1 = series.ewm(span=fast, adjust=False).mean()
        exp2 = series.ewm(span=slow, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    except Exception as e:
        logger.error(f"Error calculating MACD: {e}")
        return (pd.Series(index=series.index, dtype=float),
                pd.Series(index=series.index, dtype=float),
                pd.Series(index=series.index, dtype=float))
def analyze_symbol(symbol):
    """Analyze a single stock symbol for trading signals"""
    try:
        logger.info(f"Analyzing {symbol}")
        
        # Fetch stock data with explicit auto_adjust=False to suppress warning
        df = yf.download(
            symbol, 
            period="7d", 
            interval="30m", 
            progress=False,
            auto_adjust=False
        )
        
        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        
        if df.empty or len(df) < 50:
            logger.warning(f"[{symbol}] Not enough data")
            return None
        
        # Calculate technical indicators
        df["SMA20"] = calculate_sma(df["Close"], SMA_PERIOD)
        df["RSI14"] = calculate_rsi(df["Close"], RSI_PERIOD)
        
        macd_line, signal_line, histogram = calculate_macd(df["Close"])
        df["MACD"] = macd_line
        df["MACD_Signal"] = signal_line
        df["MACD_Histogram"] = histogram
        
        df["Volume_Avg"] = df["Volume"].rolling(20).mean()
        
        # Remove rows with NaN values
        df = df.dropna()
        
        if df.empty:
            logger.warning(f"[{symbol}] No data after adding indicators")
            return None
        
        # Get latest values and ensure they're Python floats (not pandas Series)
        latest = df.iloc[-1]
        
        # Extract scalar values safely to avoid pandas boolean ambiguity
        try:
            price = float(latest["Close"]) if pd.notna(latest["Close"]) else None
        except (TypeError, ValueError):
            price = None
            
        try:
            sma20 = float(latest["SMA20"]) if pd.notna(latest["SMA20"]) else None
        except (TypeError, ValueError):
            sma20 = None
            
        try:
            rsi14 = float(latest["RSI14"]) if pd.notna(latest["RSI14"]) else None
        except (TypeError, ValueError):
            rsi14 = None
            
        try:
            macd_val = float(latest["MACD"]) if pd.notna(latest["MACD"]) else None
        except (TypeError, ValueError):
            macd_val = None
            
        try:
            signal_val = float(latest["MACD_Signal"]) if pd.notna(latest["MACD_Signal"]) else None
        except (TypeError, ValueError):
            signal_val = None
            
        try:
            volume = float(latest["Volume"]) if pd.notna(latest["Volume"]) else None
        except (TypeError, ValueError):
            volume = None
            
        try:
            volume_avg = float(latest["Volume_Avg"]) if pd.notna(latest["Volume_Avg"]) else None
        except (TypeError, ValueError):
            volume_avg = None
        
        # Format values safely for logging
        price_str = f"₹{price:.2f}" if price is not None else "N/A"
        sma_str = f"₹{sma20:.2f}" if sma20 is not None else "N/A"
        rsi_str = f"{rsi14:.1f}" if rsi14 is not None else "N/A"
        macd_str = f"{macd_val:.3f}" if macd_val is not None else "N/A"
        volume_str = f"{volume:.0f}" if volume is not None else "N/A"
        
        logger.info(f"[{symbol}] Price={price_str}, SMA20={sma_str}, RSI={rsi_str}, MACD={macd_str}, Volume={volume_str}")
        
        # Generate signals if we have all required data
        if all(v is not None for v in [sma20, rsi14, macd_val, signal_val, volume, volume_avg]):
            signal_type = None
            volume_spike = volume > (VOLUME_MULTIPLIER * volume_avg) if volume_avg > 0 else False
            
            # High accuracy signals - strong breakout with volume confirmation
            if (price > sma20 and rsi14 < 30 and macd_val > signal_val and volume_spike):
                signal_type = "HIGH_BULLISH"
            elif (price < sma20 and rsi14 > 70 and macd_val < signal_val and volume_spike):
                signal_type = "HIGH_BEARISH"
            # Mild accuracy signals - trend/momentum without volume requirement
            elif (price > sma20 and rsi14 < 40 and macd_val > signal_val):
                signal_type = "MILD_BULLISH"
            elif (price < sma20 and rsi14 > 60 and macd_val < signal_val):
                signal_type = "MILD_BEARISH"
            
            # Send alerts for detected signals
            if signal_type:
                message = format_alert_message(symbol, signal_type, price, rsi14, macd_val, signal_val, volume_spike)
                if message:
                    send_telegram_alert(message)
                    logger.info(f"Alert sent for {symbol}: {signal_type}")
            else:
                logger.info(f"[{symbol}] No signal detected")
        else:
            logger.warning(f"[{symbol}] Incomplete indicator data")
        
        return {
            "symbol": symbol,
            "price": price,
            "sma20": sma20,
            "rsi14": rsi14,
            "macd": macd_val,
            "signal": signal_val,
            "volume": volume,
            "volume_avg": volume_avg,
            "timestamp": datetime.now(IST).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")
        return None
def format_alert_message(symbol, signal_type, price, rsi14, macd_val, signal_val, volume_spike=False):
    """Format alert message based on signal type"""
    try:
        base_info = f"Price: ₹{price:.2f}\nRSI14: {rsi14:.1f}"
        
        if signal_type == "HIGH_BULLISH":
            message = (
                f"📈 *HIGH Spike Detected* — {symbol}\n"
                f"{base_info} (<30)\n"
                f"MACD: {macd_val:.3f} > {signal_val:.3f} ↑\n"
                f"Volume Spike Confirmed ✅"
            )
        elif signal_type == "HIGH_BEARISH":
            message = (
                f"📉 *HIGH Fall Detected* — {symbol}\n"
                f"{base_info} (>70)\n"
                f"MACD: {macd_val:.3f} < {signal_val:.3f} ↓\n"
                f"Volume Spike Confirmed ✅"
            )
        elif signal_type == "MILD_BULLISH":
            message = (
                f"⚠️ *Mild Bullish Signal* — {symbol}\n"
                f"{base_info}\n"
                f"MACD: {macd_val:.3f} > {signal_val:.3f} ↑"
            )
        elif signal_type == "MILD_BEARISH":
            message = (
                f"⚠️ *Mild Bearish Signal* — {symbol}\n"
                f"{base_info}\n"
                f"MACD: {macd_val:.3f} < {signal_val:.3f} ↓"
            )
        else:
            return None
        
        return message
        
    except Exception as e:
        logger.error(f"Error formatting alert message: {e}")
        return None
def run_market_scanner():
    """Main bot loop that scans the market periodically"""
    global bot_status
    
    logger.info("Market scanner started")
    bot_status["running"] = True
    
    scan_count = 0
    
    while bot_status["running"]:
        try:
            scan_count += 1
            current_time = datetime.now(IST)
            
            logger.info(f"Starting scan #{scan_count} at {current_time.strftime('%H:%M:%S')}")
            
            # Check if market is open
            if not is_market_open():
                logger.info("Market is closed, waiting for next scan")
                bot_status["last_scan"] = current_time.isoformat()
                time.sleep(SCAN_INTERVAL)
                continue
            
            # Analyze all symbols
            results = []
            for symbol in SYMBOLS:
                try:
                    result = analyze_symbol(symbol)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Error analyzing {symbol}: {e}")
                    continue
            
            # Update status
            bot_status.update({
                "last_scan": current_time.isoformat(),
                "total_scans": scan_count
            })
            
            logger.info(f"Scan #{scan_count} completed, analyzed {len(results)} symbols")
            
            # Remove periodic status updates - only send trading alerts
            
        except Exception as e:
            error_msg = f"Error in scanner loop: {e}"
            logger.error(error_msg)
            
            bot_status["errors"] += 1
            bot_status["last_error"] = error_msg
            
            # Log errors but don't send Telegram alerts for system errors
        
        # Wait for next scan
        time.sleep(SCAN_INTERVAL)
# ——— Helper Functions ———
def get_market_status():
    """Get current market status"""
    try:
        now = datetime.now(IST)
        is_open = is_market_open()
        
        return {
            "is_open": is_open,
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "status": "OPEN" if is_open else "CLOSED"
        }
    except Exception as e:
        logger.error(f"Error getting market status: {e}")
        return {"is_open": False, "status": "ERROR", "current_time": "Unknown"}
# ——— Flask Routes ———
@app.route('/')
def dashboard():
    """Main dashboard page"""
    telegram_status = "enabled" if bot_status["telegram_enabled"] else "disabled (credentials missing)"
    warning_div = f"<div class='status warning'><strong>⚠️ Telegram:</strong> {telegram_status}</div>" if not bot_status["telegram_enabled"] else ""
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Market Spike Bot</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .status {{ padding: 10px; margin: 10px 0; border-radius: 5px; }}
            .running {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
            .warning {{ background: #fff3cd; color: #856404; border: 1px solid #ffeaa7; }}
            .info {{ background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }}
            h1 {{ color: #333; }}
            .api-link {{ margin: 10px 0; }}
            .api-link a {{ color: #007bff; text-decoration: none; }}
            .api-link a:hover {{ text-decoration: underline; }}
        </style>
        <script>
            setTimeout(() => location.reload(), 30000); // Auto-refresh every 30 seconds
        </script>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Market Spike Bot Dashboard</h1>
            <div class="status running">
                <strong>✅ Bot Status:</strong> Running
            </div>
            {warning_div}
            <div class="info">
                <strong>📊 Monitoring:</strong> 10 Indian stocks (RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, HINDUNILVR, ITC, SBIN, BHARTIARTL, LT)
            </div>
            <div class="info">
                <strong>⏱️ Scan Interval:</strong> 15 minutes
            </div>
            <div class="info">
                <strong>🕐 Market Hours:</strong> 9:15 AM - 3:30 PM IST
            </div>
            <div class="info">
                <strong>📈 Technical Analysis:</strong> SMA(20), RSI(14), MACD
            </div>
            <div class="api-link">
                <strong>📡 API Endpoints:</strong><br>
                <a href="/status">Bot Status</a> | 
                <a href="/market">Market Status</a> | 
                <a href="/health">Health Check</a>
            </div>
            <div class="info">
                <strong>🔄 Auto-refresh:</strong> Page refreshes every 30 seconds
            </div>
        </div>
    </body>
    </html>
    """
@app.route('/status')
def status():
    """Return bot status as JSON"""
    try:
        market_status = get_market_status()
        
        return jsonify({
            "bot": bot_status,
            "market": market_status,
            "symbols": SYMBOLS,
            "config": {
                "scan_interval_minutes": SCAN_INTERVAL // 60,
                "data_period": "7d",
                "data_interval": "30m",
                "telegram_enabled": bot_status["telegram_enabled"],
                "operation_mode": "market_hours_only"
            }
        })
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({"error": str(e)}), 500
@app.route('/market')
def market():
    """Return market status"""
    try:
        return jsonify(get_market_status())
    except Exception as e:
        logger.error(f"Error getting market status: {e}")
        return jsonify({"error": str(e)}), 500
@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        current_time = datetime.now(IST)
        return jsonify({
            "status": "healthy",
            "timestamp": current_time.isoformat(),
            "bot_running": bot_status["running"],
            "uptime_scans": bot_status["total_scans"],
            "telegram_enabled": bot_status["telegram_enabled"],
            "operation_mode": "market_hours_only"
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500
def shutdown_handler():
    """Graceful shutdown handler"""
    global bot_status
    logger.info("Shutting down market scanner...")
    bot_status["running"] = False
if __name__ == "__main__":
    # Log startup information
    logger.info("Starting Market Spike Bot...")
    logger.info(f"Telegram enabled: {bot_status['telegram_enabled']}")
    logger.info(f"Monitoring symbols: {', '.join(SYMBOLS)}")
    logger.info(f"Scan interval: {SCAN_INTERVAL // 60} minutes")
    logger.info("Operation mode: Market hours only (9:15 AM - 3:30 PM IST)")
    
    # Start the market scanner in a background thread
    scanner_thread = threading.Thread(target=run_market_scanner, daemon=True)
    scanner_thread.start()
    
    try:
        # Start Flask server - Use port from environment variable or default to 5000
        port = int(os.environ.get('PORT', 5000))
        logger.info(f"Starting Flask server on port {port}...")
        app.run(host="0.0.0.0", port=port, debug=False)
    except KeyboardInterrupt:
        shutdown_handler()
    except Exception as e:
        logger.error(f"Flask server error: {e}")
        pass  # Don't send system error alerts
    finally:
        shutdown_handler()
