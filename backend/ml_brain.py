"""
ML Brain Module — XGBoost Meta-Labeling & Model Management
"""
import os
import sqlite3
import pandas as pd
import numpy as np
import pickle
from datetime import datetime

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "trading.db")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "xgboost_meta_model.pkl")

class MLBrain:
    def __init__(self):
        self.model = None
        self.is_trained = False
        self.load_model()

    def load_model(self):
        try:
            if os.path.exists(MODEL_PATH):
                with open(MODEL_PATH, "rb") as f:
                    self.model = pickle.load(f)
                    self.is_trained = True
                print(f"[{datetime.now()}] [ML BRAIN] Model XGBoost berhasil dimuat.")
        except Exception as e:
            print(f"[{datetime.now()}] [ML BRAIN] Gagal memuat model: {e}")

    def train_model(self):
        """
        Melatih model XGBoost menggunakan data dari tabel ml_dataset.
        Meta-Labeling: Fitur Order Flow + Teknikal -> Target Win (1/0).
        """
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            query = """
                SELECT timestamp, net_delta, cvd, bid_ask_imbalance, price_change_5m, 
                       orderbook_imbalance_ratio, cvd_momentum, volatility_range, 
                       rsi, atr, bb_width, ema_trend, target_win,
                       vwap_delta, funding_rate
                FROM ml_dataset
                WHERE target_win IS NOT NULL
                ORDER BY timestamp ASC
            """
            df = pd.read_sql(query, conn)
            conn.close()

            if len(df) < 50:
                print(f"[{datetime.now()}] [ML BRAIN] Data training tidak cukup ({len(df)} baris). Minimal 50 baris.")
                return False

            # Walk-forward split (time-ordered): no lookahead, no leakage
            split_idx = int(len(df) * 0.8)
            train_df = df.iloc[:split_idx]
            test_df = df.iloc[split_idx:]

            # Feature list: 11 base + 2 new quant (vwap_delta, funding_rate)
            feat_cols = ['net_delta', 'cvd', 'bid_ask_imbalance', 'price_change_5m',
                         'orderbook_imbalance_ratio', 'cvd_momentum', 'volatility_range',
                         'rsi', 'atr', 'bb_width', 'ema_trend',
                         'vwap_delta', 'funding_rate']
            # Backward compat: kolom baru belum ada di DB lama → fill 0
            for c in feat_cols:
                if c not in df.columns:
                    df[c] = 0.0

            X = train_df[feat_cols].fillna(0)
            y = train_df['target_win']
            X_test = test_df[feat_cols].fillna(0)
            y_test = test_df['target_win']

            # Lazy import xgboost
            try:
                import xgboost as xgb
            except ImportError:
                print("[ML BRAIN] XGBoost tidak terinstal. Silakan pip install xgboost.")
                return False

            # Handle class imbalance in walk-forward train set
            n_pos = int(y.sum())
            n_neg = int(len(y) - y.sum())
            scale_pos_weight = max(1.0, n_neg / n_pos) if n_pos > 0 else 1.0

            model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.05,
                random_state=42,
                scale_pos_weight=scale_pos_weight,
                eval_metric='logloss'
            )
            model.fit(X, y)

            # Honest evaluation: walk-forward AUC on unseen (future) trades
            auc_report = "N/A"
            try:
                from sklearn.metrics import roc_auc_score
                if len(X_test) >= 5 and len(set(y_test)) > 1:
                    y_prob = model.predict_proba(X_test)[:, 1]
                    test_auc = roc_auc_score(y_test, y_prob)
                    auc_report = f"{test_auc:.3f}"
            except Exception as e:
                auc_report = f"ERR:{e}"

            # Simpan model
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(model, f)

            self.model = model
            self.is_trained = True
            print(f"[{datetime.now()}] [ML BRAIN] Training XGBoost selesai ({len(df)} sampel, walk-forward AUC={auc_report}, train {len(train_df)}/test {len(test_df)})")
            return True

        except Exception as e:
            print(f"[{datetime.now()}] [ML BRAIN ERROR] Training gagal: {e}")
            return False

    def predict_probability(self, features_dict):
        """
        Lapisan Meta-Labeling: Memprediksi probabilitas sukses (0.0 - 1.0) dari sinyal.
        """
        if not self.is_trained or self.model is None:
            # Fallback jika model belum dilatih
            return 0.5

        try:
            features = pd.DataFrame([{
                'net_delta': features_dict.get('net_delta', 0),
                'cvd': features_dict.get('cvd', 0),
                'bid_ask_imbalance': features_dict.get('bid_ask_imbalance', 0),
                'price_change_5m': features_dict.get('price_change_5m', 0),
                'orderbook_imbalance_ratio': features_dict.get('orderbook_imbalance_ratio', 0.5),
                'cvd_momentum': features_dict.get('cvd_momentum', 0),
                'volatility_range': features_dict.get('volatility_range', 0),
                'rsi': features_dict.get('rsi', 50),
                'atr': features_dict.get('atr', 0),
                'bb_width': features_dict.get('bb_width', 0),
                'ema_trend': features_dict.get('ema_trend', 0),
                'vwap_delta': features_dict.get('vwap_delta', 0),
                'funding_rate': features_dict.get('funding_rate', 0),
            }])

            # Probabilitas kelas 1 (WIN)
            prob = self.model.predict_proba(features)[0][1]
            return float(prob)
        except Exception as e:
            print(f"[{datetime.now()}] [ML BRAIN ERROR] Prediksi gagal: {e}")
            return 0.5

# Singleton
ml_brain = MLBrain()
