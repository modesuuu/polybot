"""
ML Data Collector Module — enhanced with Moss-type quant features
- Backward-compatible migration for new columns
- All ops try-except safe, never crashes worker
"""
import sqlite3
import datetime
import os
from typing import Optional, Dict, Any

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "trading.db")

def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

# --- schema ---
BASE_COLUMNS = {
    "timestamp": "TEXT PRIMARY KEY",
    "net_delta": "FLOAT",
    "cvd": "FLOAT",
    "bid_ask_imbalance": "FLOAT",
    "price_change_5m": "FLOAT",
    "polymarket_entry_price": "FLOAT",
    "target_win": "INTEGER",
}
# Moss-adapted extensions
EXT_COLUMNS = {
    "orderbook_imbalance_ratio": "FLOAT",  # 0..1
    "orderbook_imbalance_raw": "FLOAT",    # -1..1
    "cvd_momentum": "FLOAT",
    "volatility_range": "FLOAT",
    "volatility_stdev": "FLOAT",
    "is_sideways": "INTEGER",  # 0/1
    "confidence_score": "FLOAT",
    "position_size": "FLOAT",
    "imbalance_pass": "INTEGER",
    # Advanced Brain Features
    "market_regime": "TEXT",       # TRENDING_UP, TRENDING_DOWN, SIDEWAYS, HIGH_VOLATILITY
    "rsi": "FLOAT",
    "atr": "FLOAT",
    "bb_width": "FLOAT",
    "ema_trend": "FLOAT",          # 1 for up, -1 for down
    "xgboost_prob": "FLOAT",       # Model's prediction probability
    # Quant extras (Plan B)
    "vwap_delta": "FLOAT",         # price vs volume-weighted avg price
    "funding_rate": "FLOAT",       # perp 8h funding rate (futures signal, ML only)
}

def _migrate_table():
    """Add missing columns if table already exists."""
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ml_dataset'")
        if not cur.fetchone():
            conn.close()
            return
        cur.execute("PRAGMA table_info(ml_dataset)")
        existing = {row[1] for row in cur.fetchall()}
        for col, typ in {**BASE_COLUMNS, **EXT_COLUMNS}.items():
            if col not in existing:
                try:
                    # strip PRIMARY KEY for ALTER
                    col_def = typ.replace(" PRIMARY KEY", "")
                    cur.execute(f"ALTER TABLE ml_dataset ADD COLUMN {col} {col_def}")
                    print(f"[ML_DATA MIGRATE] Added column {col}")
                except Exception as e:
                    print(f"[ML_DATA MIGRATE] Skip {col}: {e}")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ML_DATA MIGRATE ERROR] {e}")

def init_ml_table() -> bool:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        # create with base columns
        cur.execute("""
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
        conn.close()
        _migrate_table()
        print(f"[{datetime.datetime.now()}] [ML_DATA] Tabel ml_dataset ready.")
        return True
    except Exception as e:
        print(f"[{datetime.datetime.now()}] [ML_DATA ERROR] init: {e}")
        return False

def log_ml_feature(data_dict: Dict[str, Any]) -> bool:
    try:
        timestamp = data_dict.get('timestamp')
        if not timestamp:
            print(f"[{datetime.datetime.now()}] [ML_DATA ERROR] timestamp wajib.")
            return False
        # ensure table + columns exist
        _migrate_table()
        conn = _get_connection()
        cur = conn.cursor()
        # build dynamic insert — only columns that exist, use INSERT OR REPLACE
        # collect all possible keys
        all_keys = ["timestamp", "net_delta", "cvd", "bid_ask_imbalance", "price_change_5m",
                     "polymarket_entry_price", "target_win",
                     "orderbook_imbalance_ratio", "orderbook_imbalance_raw",
                     "cvd_momentum", "volatility_range", "volatility_stdev",
                     "is_sideways", "confidence_score", "position_size", "imbalance_pass",
                     # Brain features (was missing — caused 6 NULL columns)
                     "market_regime", "rsi", "atr", "bb_width", "ema_trend", "xgboost_prob",
                     # Quant extras (Plan B)
                     "vwap_delta", "funding_rate"]
        # filter to columns that actually exist in DB after migration
        cur.execute("PRAGMA table_info(ml_dataset)")
        existing = {row[1] for row in cur.fetchall()}
        keys = [k for k in all_keys if k in existing]
        # prepare values
        vals = []
        for k in keys:
            if k == "is_sideways":
                v = data_dict.get(k)
                # bool -> int
                if isinstance(v, bool):
                    v = 1 if v else 0
                elif v is None:
                    v = None
                else:
                    v = int(v)
                vals.append(v)
            elif k == "imbalance_pass":
                v = data_dict.get(k)
                if isinstance(v, bool):
                    v = 1 if v else 0
                vals.append(v)
            else:
                vals.append(data_dict.get(k))
        placeholders = ",".join(["?"] * len(keys))
        cols = ",".join(keys)
        # OR REPLACE keeps PK semantics
        cur.execute(f"INSERT OR REPLACE INTO ml_dataset ({cols}) VALUES ({placeholders})", vals)
        conn.commit()
        conn.close()
        print(f"[{datetime.datetime.now()}] [ML_DATA] Logged ts={timestamp} net_delta={data_dict.get('net_delta',0):.2f} obi={data_dict.get('orderbook_imbalance_ratio',0.5):.2f} cvd_mom={data_dict.get('cvd_momentum',0):.2f}")
        return True
    except Exception as e:
        print(f"[{datetime.datetime.now()}] [ML_DATA ERROR] log: {e}")
        return False

def update_ml_target(timestamp: str, is_win: bool) -> bool:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        target_value = 1 if is_win else 0
        cur.execute("UPDATE ml_dataset SET target_win = ? WHERE timestamp = ?", (target_value, timestamp))
        if cur.rowcount == 0:
            print(f"[{datetime.datetime.now()}] [ML_DATA WARNING] No record ts={timestamp}")
            conn.close()
            return False
        conn.commit()
        conn.close()
        print(f"[{datetime.datetime.now()}] [ML_DATA] Target ts={timestamp} -> {'WIN' if is_win else 'LOSS'}")
        return True
    except Exception as e:
        print(f"[{datetime.datetime.now()}] [ML_DATA ERROR] update target: {e}")
        return False

def get_ml_dataset_count() -> int:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ml_dataset")
        c = cur.fetchone()[0]
        conn.close()
        return c
    except Exception as e:
        print(f"[ML_DATA ERROR] count: {e}")
        return 0

def get_ml_dataset_count_with_target() -> Dict[str, int]:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ml_dataset")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ml_dataset WHERE target_win IS NOT NULL")
        with_target = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ml_dataset WHERE target_win = 1")
        win_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ml_dataset WHERE target_win = 0")
        loss_count = cur.fetchone()[0]
        conn.close()
        return {"total": total, "with_target": with_target, "win_count": win_count, "loss_count": loss_count}
    except Exception as e:
        print(f"[ML_DATA ERROR] stats: {e}")
        return {"total": 0, "with_target": 0, "win_count": 0, "loss_count": 0}

def get_latest_ml_record() -> Optional[Dict[str, Any]]:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM ml_dataset ORDER BY timestamp DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row is None:
            return None
        return dict(row)
    except Exception as e:
        print(f"[ML_DATA ERROR] latest: {e}")
        return None
