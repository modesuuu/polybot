import urllib.request
import json
import sqlite3
import time
from datetime import datetime, timedelta
import os

# Configuration
SYMBOL = "BTCUSDT"
INTERVAL = "5m"
DAYS_BACK = 30  # Default 30 days, can be adjusted
DB_PATH = os.path.join(os.path.dirname(__file__), "../backend/trading.db")

def fetch_klines(symbol, interval, start_time, end_time=None):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&startTime={start_time}&limit=1000"
    if end_time:
        url += f"&endTime={end_time}"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())

def main():
    print(f"Starting historical data fetch for {SYMBOL} ({INTERVAL})...")
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=DAYS_BACK)
    
    current_ts = int(start_date.timestamp() * 1000)
    end_ts = int(end_date.timestamp() * 1000)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ml_dataset (
            timestamp TEXT PRIMARY KEY,
            net_delta FLOAT,
            cvd FLOAT,
            bid_ask_imbalance FLOAT,
            price_change_5m FLOAT,
            polymarket_entry_price FLOAT,
            target_win INTEGER
        )
    """)
    conn.commit()

    total_records = 0
    running_cvd = 0.0

    while current_ts < end_ts:
        print(f"Fetching chunk from {datetime.utcfromtimestamp(current_ts/1000)}...")
        try:
            klines = fetch_klines(SYMBOL, INTERVAL, current_ts, end_ts)
        except Exception as e:
            print(f"Fetch error: {e}. Retrying in 2s...")
            time.sleep(2)
            continue

        if not klines:
            break

        rows = []
        for k in klines:
            # kline format: [open_time, open, high, low, close, volume, close_time, quote_vol, trades, taker_buy_base, taker_buy_quote, ignore]
            open_time = k[0]
            ts_str = datetime.utcfromtimestamp(open_time/1000).isoformat()
            
            open_p = float(k[1])
            close_p = float(k[4])
            volume = float(k[5])
            taker_buy_vol = float(k[9])
            
            price_change_5m = close_p - open_p
            # Target Win: 1 if candle closes UP, 0 if DOWN
            target_win = 1 if price_change_5m > 0 else 0
            
            # Net Delta & CVD proxy
            net_delta = (taker_buy_vol * 2.0) - volume
            running_cvd += net_delta
            
            # Simulated entry price around $0.50
            polymarket_entry_price = 0.50

            rows.append((
                ts_str,
                net_delta,
                running_cvd,
                0.0, # bid_ask_imbalance default
                price_change_5m,
                polymarket_entry_price,
                target_win
            ))

        cursor.executemany("""
            INSERT OR REPLACE INTO ml_dataset (
                timestamp, net_delta, cvd, bid_ask_imbalance,
                price_change_5m, polymarket_entry_price, target_win
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()

        total_records += len(rows)
        current_ts = klines[-1][0] + 1
        time.sleep(0.1)

    conn.close()
    print(f"Successfully fetched and stored {total_records} historical records into trading.db!")

if __name__ == "__main__":
    main()
