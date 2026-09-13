from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
import asyncio
import os
import json
import datetime
from typing import List

from database import init_db, get_db
from models import TradeSignal
from order_flow import engine
from worker import trading_worker, mark_to_market_worker
from telegram_bot import run_telegram_bot
import ml_data_collector
from ml_brain import ml_brain

app = FastAPI(title="Polymarket Algo Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    print("Inisialisasi Database...")
    init_db()

    # Inisialisasi tabel ML dataset
    try:
        ml_data_collector.init_ml_table()
    except Exception as e:
        print(f"[STARTUP] Gagal inisialisasi ML table: {e}")

    print("Memulai background tasks...")
    asyncio.create_task(engine.connect_and_listen())
    asyncio.create_task(trading_worker())
    asyncio.create_task(mark_to_market_worker())
    asyncio.create_task(run_telegram_bot())


@app.get("/")
def read_root():
    return {"status": "Bot is running", "current_price": engine.get_current_price()}


@app.get("/metrics")
def get_metrics(db: Session = Depends(get_db), since: str = None):
    # Optional session filter: kalau sejak diberikan, cuma count trade baru sejak timestamp itu
    query = db.query(TradeSignal).filter(TradeSignal.status.in_(['WIN', 'LOSS']))
    hist_query = db.query(TradeSignal).filter(TradeSignal.status == 'OPEN')
    if since:
        try:
            cutoff = datetime.datetime.fromisoformat(since.replace('Z', '+00:00'))
            query = query.filter(TradeSignal.timestamp >= cutoff)
            hist_query = hist_query.filter(TradeSignal.timestamp >= cutoff)
        except Exception:
            pass  # invalid since → ignore filter

    closed_trades = query.all()
    open_trades = hist_query.all()

    total_trades = len(closed_trades)
    realized_pnl = 0.0
    realized_pnl = sum(t.pnl for t in closed_trades if t.pnl)
    unrealized_pnl = sum(t.unrealized_pnl for t in open_trades if t.unrealized_pnl is not None)
    winning_trades = sum(1 for t in closed_trades if t.pnl and t.pnl > 0)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    return {
        "total_pnl": round(realized_pnl, 2),
        "balance": round(10.0 + realized_pnl, 2),
        "unrealized_pnl": unrealized_pnl,
        "win_rate": round(win_rate, 2),
        "total_trades": total_trades,
        "open_trades": len(open_trades),
        "session_cutoff": since
    }


@app.get("/api/active-trade")
def get_active_trade(db: Session = Depends(get_db)):
    """
    Endpoint khusus untuk sinyal aktif (status=OPEN) dengan data Polymarket live.
    Mengembalikan: up_price, down_price, unrealized_pnl, dll.
    """
    trade = db.query(TradeSignal).filter(TradeSignal.status == 'OPEN').order_by(TradeSignal.timestamp.desc()).first()
    if not trade:
        return None

    current_token_price = trade.current_token_price if trade.current_token_price is not None else trade.entry_price_share
    entry_price_share = trade.entry_price_share or 0.5
    shares_bought = trade.shares_bought or (trade.quantity / entry_price_share if entry_price_share > 0 else 0)

    return {
        "id": trade.id,
        "timestamp": trade.timestamp.isoformat() if trade.timestamp else None,
        "symbol": trade.symbol,
        "direction": trade.direction,
        "btc_entry_price": trade.entry_price,
        "token_id": trade.token_id,
        "up_price": current_token_price,
        "down_price": (1 - current_token_price) if current_token_price is not None else None,
        "current_token_price": current_token_price,
        "entry_price_share": trade.entry_price_share,
        "shares_bought": shares_bought,
        "position_size": trade.quantity,
        "potential_win": (shares_bought * 1.00) - trade.quantity,
        "unrealized_pnl": (current_token_price - entry_price_share) * shares_bought if current_token_price is not None else 0.0,
        "spread": trade.spread,
        "status": trade.status,
    }


@app.get("/history")
@app.get("/api/signals")
def get_history(limit: int = 50, since: str = None, db: Session = Depends(get_db)):
    query = db.query(TradeSignal)
    if since:
        try:
            cutoff = datetime.datetime.fromisoformat(since.replace('Z', '+00:00'))
            query = query.filter(TradeSignal.timestamp >= cutoff)
        except Exception:
            pass
    trades = query.order_by(TradeSignal.timestamp.desc()).limit(limit).all()

    result = []
    for t in trades:
        current_token_price = t.current_token_price if t.current_token_price is not None else t.entry_price_share
        entry_price_share = t.entry_price_share or 0.5
        shares_bought = t.shares_bought or (t.quantity / entry_price_share if entry_price_share > 0 else 0)

        result.append({
            "id": t.id,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            "symbol": t.symbol,
            "direction": t.direction,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "quantity": t.quantity,
            "entry_price_share": t.entry_price_share,
            "shares_bought": shares_bought,
            "current_token_price": current_token_price,
            "unrealized_pnl": t.unrealized_pnl,
            "up_price": current_token_price,
            "down_price": (1 - current_token_price) if current_token_price is not None else None,
            "position_size": t.quantity,
            "potential_win": (shares_bought * 1.00) - t.quantity if t.status != 'OPEN' else (shares_bought * 1.00) - t.quantity,
            "status": t.status,
            "pnl": t.pnl,
            "spread": t.spread,
        })
    return result


@app.get("/api/ml/dataset-count")
def get_ml_dataset_count():
    """
    Mengembalikan jumlah baris data ML yang sudah terkumpul di tabel ml_dataset.
    """
    try:
        total_records = ml_data_collector.get_ml_dataset_count()
        stats = ml_data_collector.get_ml_dataset_count_with_target()
        return {
            "total_records": total_records,
            "with_target": stats.get("with_target", 0),
            "win_count": stats.get("win_count", 0),
            "loss_count": stats.get("loss_count", 0)
        }
    except Exception as e:
        return {"total_records": 0, "error": str(e)}


@app.post("/api/ml/train")
def train_ml_model():
    """
    Manual training trigger untuk XGBoost.
    """
    success = ml_brain.train_model()
    return {
        "success": success, 
        "message": "Model XGBoost berhasil dilatih" if success else "Gagal melatih model"
    }

@app.get("/api/ml/audit-history")
def get_audit_history(db: Session = Depends(get_db)):
    """Mengambil riwayat audit AI Agent (PostgreSQL compatible)"""
    try:
        cursor = db.execute(text("SELECT timestamp, daily_pnl, win_rate, total_trades, ai_reasoning FROM ai_audit_logs ORDER BY timestamp DESC LIMIT 10"))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "timestamp": str(r[0]),
                "daily_pnl": r[1],
                "win_rate": r[2],
                "total_trades": r[3],
                "ai_reasoning": r[4]
            })
        return result
    except Exception as e:
        return []

@app.get("/api/ml/meta-config")
def get_meta_config():
    """Mengambil konfigurasi dinamis yang disetel AI"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), "meta_config.json")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)
        return {}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/ml/reset-config")
def reset_meta_config():
    """Reset konfigurasi ke default"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), "meta_config.json")
        default_config = {
            "obi_threshold": 0.65,
            "confidence_threshold": 45,
            "min_sentiment_score": -0.1,
            "strategy_parameters": {
                "rsi_period": 14,
                "ema_short": 9,
                "ema_long": 21,
                "ema_period": 24,
                "bb_period": 20,
                "bb_multiplier": 2.0,
                "volatility_threshold_multiplier": 0.04,
                "profit_target_multiplier": 1.2,
                "stop_loss_multiplier": 0.95,
                "atr_period": 14
            },
            "last_ai_tuning": datetime.utcnow().strftime("%Y-%m-%d"),
            "ai_recommendation": "Reset to factory defaults."
        }
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=4)
        return {"success": True, "message": "Config reset to default"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
