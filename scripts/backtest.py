import sqlite3
import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime

# Paths
DB_PATH = "C:/Users/Raka Alfarezi/Documents/dev_learn/poly/backend/trading.db"
MODEL_PATH = "C:/Users/Raka Alfarezi/Documents/dev_learn/poly/backend/xgboost_meta_model.pkl"

def run_backtest():
    print(f"[{datetime.now()}] Starting Institutional Backtest Report...")
    
    if not os.path.exists(MODEL_PATH):
        print("Error: Model XGBoost belum dilatih. Jalankan training dulu!")
        return

    # 1. Load Data
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT * FROM ml_dataset WHERE target_win IS NOT NULL"
    df = pd.read_sql(query, conn)
    conn.close()

    if len(df) < 100:
        print(f"Data tidak cukup untuk backtest (hanya {len(df)} baris).")
        return

    # 2. Load Model
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)

    # 3. Prepare Features
    # Note: Historical data missing some real-time features (OBI/Spread), 
    # we fill with defaults to see price action performance.
    feature_cols = ['net_delta', 'cvd', 'bid_ask_imbalance', 'price_change_5m',
                    'orderbook_imbalance_ratio', 'cvd_momentum', 'volatility_range',
                    'rsi', 'atr', 'bb_width', 'ema_trend']
    
    # Ensure all columns exist, fill missing with 0 or neutral
    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0.5 if 'ratio' in col else 0.0

    X = df[feature_cols].fillna(0)
    
    # 4. Run Simulation
    print(f"Simulating {len(df)} trades...")
    df['prob'] = model.predict_proba(X)[:, 1]
    
    # Strategy: Trade only if probability > 60%
    THRESHOLD = 0.60
    df['take_trade'] = df['prob'] >= THRESHOLD
    
    # Calculate Results
    trades = df[df['take_trade']].copy()
    total_trades = len(trades)
    
    if total_trades == 0:
        print(f"Strategi terlalu ketat! Tidak ada trade dengan probabilitas > {THRESHOLD*100}%")
        return

    wins = trades[trades['target_win'] == 1]
    win_rate = (len(wins) / total_trades) * 100
    
    # PnL Calculation ($5 position)
    # Win = +$2.25 (payout 1.45x avg), Loss = -$5.00
    trades['pnl'] = trades['target_win'].apply(lambda x: 2.25 if x == 1 else -5.00)
    total_pnl = trades['pnl'].sum()
    max_drawdown = trades['pnl'].cumsum().min()

    # 5. Output Report
    print("\n" + "="*40)
    print("       POLYBOT BACKTEST REPORT")
    print("="*40)
    print(f"Periode Data    : {df['timestamp'].min()} s/d {df['timestamp'].max()}")
    print(f"Total Sampel    : {len(df)}")
    print(f"Trades Eksekusi : {total_trades} (Threshold > {THRESHOLD*100}%)")
    print(f"Win Rate        : {win_rate:.2f}%")
    print(f"Total PnL ($)   : ${total_pnl:.2f}")
    print(f"Max Drawdown    : ${max_drawdown:.2f}")
    print(f"Profit Factor   : {abs(trades[trades['pnl']>0]['pnl'].sum() / trades[trades['pnl']<0]['pnl'].sum()):.2f}")
    print("="*40)

if __name__ == "__main__":
    run_backtest()
