import asyncio
import datetime
import json
import os
from sqlalchemy.orm import Session
from database import SessionLocal
from models import TradeSignal
from sqlalchemy.orm import Session
from order_flow import engine
from dotenv import load_dotenv
from market_resolver import get_active_tokens, get_current_token_price, get_live_token_price, get_polymarket_orderbook
from polymarket_executor import executor
from telegram_bot import send_alert
import ml_data_collector
from ml_brain import ml_brain
from llm_news_oracle import news_oracle
import strategy_logic

# Path Config
META_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "meta_config.json")

def load_meta_config():
    try:
        with open(META_CONFIG_PATH, "r") as f:
            return json.load(f)
    except:
        return {"obi_threshold": 0.65, "confidence_threshold": 60, "min_sentiment_score": -0.3}

load_dotenv()

# ===================== CONFIG =====================
TRADE_AMOUNT_USD_DEFAULT = float(os.getenv("TRADE_AMOUNT_USD", 5.0))
INITIAL_BALANCE = 10.0
CIRCUIT_TARGET = 100.0
CIRCUIT_BREAKER_ENABLED = False  # DISABLED by user request 2026-09-13: bot never halts on balance
IMBALANCE_THRESHOLD = 0.65  # 65% minimal
STATE_FILE = os.path.join(os.path.dirname(__file__), ".bot_state.json")

# Inisialisasi tabel ML saat module dimuat
try:
    ml_data_collector.init_ml_table()
except Exception as e:
    print(f"[ML_INIT ERROR] Gagal inisialisasi ML table saat startup: {e}")

# ===================== BOT STATE (persist) =====================
def _load_state():
    """Load bot state dari file — aman, never throw."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return {
                    "peak_20_hit": bool(data.get("peak_20_hit", False)),
                    "circuit_until": data.get("circuit_until"),
                    "low_balance_active": bool(data.get("low_balance_active", False)),
                    "peak_drawdown_active": bool(data.get("peak_drawdown_active", False)),
                }
    except Exception as e:
        print(f"[STATE LOAD ERROR] {e}")
    return {"peak_20_hit": False, "circuit_until": None, "low_balance_active": False, "peak_drawdown_active": False}

def _save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"[STATE SAVE ERROR] {e}")

def is_circuit_breaker_active():
    try:
        if not CIRCUIT_BREAKER_ENABLED:
            return False
        s = _load_state()
        cu = s.get("circuit_until")
        if not cu:
            return False
        until = datetime.datetime.fromisoformat(cu)
        # handle naive vs aware
        now = datetime.datetime.utcnow()
        if until.tzinfo is not None:
            until = until.replace(tzinfo=None)
        return now < until
    except Exception:
        return False

def _trigger_circuit_breaker(now):
    try:
        until = now + datetime.timedelta(hours=24)
        s = _load_state()
        s["circuit_until"] = until.isoformat()
        _save_state(s)
        print(f"[CIRCUIT BREAKER] Balance >= ${CIRCUIT_TARGET} — trading dihentikan hingga {until} (24 jam)")
    except Exception as e:
        print(f"[CIRCUIT TRIGGER ERROR] {e}")

def get_current_balance(db: Session):
    """Hitung balance real-time: INITIAL + sum realized PnL."""
    try:
        closed = db.query(TradeSignal).filter(TradeSignal.status.in_(['WIN', 'LOSS'])).all()
        realized = sum(t.pnl for t in closed if t.pnl is not None)
        return round(INITIAL_BALANCE + realized, 2)
    except Exception as e:
        print(f"[BALANCE ERROR] {e}")
        return INITIAL_BALANCE

def calculate_position_size(current_balance):
    """
    LOGIKA MANAJEMEN MODAL RAKA — adaptasi Moss money-management
    - balance >= $10: $5
    - balance <= $5: $1 sampai kembali >= $10
    - balance pernah >= $20 lalu turun ke $15: $1 sampai kembali >= $20
    - balance >= $100: halt 24 jam (return 0)

    Mapping Moss: Moss `riskManager` memakai tiered sizing + drawdown halt;
    kita persist trigger flag di .bot_state.json agar survive restart.
    """
    try:
        now = datetime.datetime.utcnow()
        # Circuit breaker check
        if is_circuit_breaker_active():
            return 0
        if current_balance >= CIRCUIT_TARGET and CIRCUIT_BREAKER_ENABLED:
            _trigger_circuit_breaker(now)
            return 0

        state = _load_state()
        # Track peak 20
        if current_balance >= 20:
            if not state["peak_20_hit"]:
                state["peak_20_hit"] = True
                _save_state(state)
            # jika sebelumnya drawdown, clear saat kembali >=20 / >=10
            if state["peak_drawdown_active"] and current_balance >= 20:
                state["peak_drawdown_active"] = False
                _save_state(state)
            if state["low_balance_active"] and current_balance >= 10:
                state["low_balance_active"] = False
                _save_state(state)

        # Trigger low-balance mode
        if current_balance <= 5:
            if not state["low_balance_active"]:
                state["low_balance_active"] = True
                _save_state(state)
            return 1

        # If in low-balance recovery
        if state["low_balance_active"]:
            if current_balance >= 10:
                state["low_balance_active"] = False
                _save_state(state)
                # lanjut cek peak drawdown di bawah
            else:
                return 1

        # Trigger peak drawdown mode: pernah peak 20, lalu turun <=15
        if state["peak_20_hit"] and current_balance <= 15:
            if not state["peak_drawdown_active"]:
                state["peak_drawdown_active"] = True
                _save_state(state)
            return 1

        if state["peak_drawdown_active"]:
            if current_balance >= 20:
                state["peak_drawdown_active"] = False
                _save_state(state)
            else:
                return 1

        # Default
        return 5
    except Exception as e:
        print(f"[POSITION SIZE ERROR] {e}")
        return 1  # paling konservatif jika error

def evaluate_trade_confidence(direction, quant_snapshot):
    """Confidence score 0-100. Menggabungkan OBI, CVD, Sentiment, XGBoost, dan Risk Score."""
    try:
        config = load_meta_config()

        ratio = quant_snapshot.get("orderbook_imbalance_ratio", 0.5)
        cvd_mom = quant_snapshot.get("cvd_momentum", 0.0)
        is_sideways = quant_snapshot.get("is_sideways", False)
        vol_range = quant_snapshot.get("volatility_range", 0)

        reasons = []
        score = 50

        # === XGBoost Meta-Labeling ===
        xgb_prob = 0.5
        try:
            xgb_prob = ml_brain.predict_probability(quant_snapshot)
            score += (xgb_prob - 0.5) * 60  # ±30 poin
            reasons.append(f"XGB {xgb_prob:.2f}")
        except Exception as xgb_e:
            reasons.append(f"XGB err")

        # === News Sentiment (relaxed) ===
        sentiment = 0.0
        try:
            sentiment = news_oracle.get_sentiment_score()
            min_sent = config.get("min_sentiment_score", -0.1)
            if direction == "UP" and sentiment < min_sent:
                score -= 15
                reasons.append(f"Sent bearish {sentiment:.2f}")
            elif direction == "DOWN" and sentiment > abs(min_sent):
                score -= 15
                reasons.append(f"Sent bullish {sentiment:.2f}")
        except Exception:
            pass

        if is_sideways:
            score -= 10
            reasons.append(f"sideways (${vol_range:.1f})")

        # === OBI Component ===
        obi_limit = config.get("obi_threshold", 0.65)
        if direction == "UP":
            score += (ratio - 0.5) * 80
            reasons.append(f"OBI {ratio:.2f}")
        elif direction == "DOWN":
            score += (0.5 - ratio) * 80
            reasons.append(f"OBI {ratio:.2f}")

        # === CVD Momentum ===
        if direction == "UP" and cvd_mom > 0:
            score += min(15, abs(cvd_mom) * 2)
        elif direction == "DOWN" and cvd_mom < 0:
            score += min(15, abs(cvd_mom) * 2)

        score = max(0, min(100, round(score)))
        return (True, score, f"SCORE {score} (XGB:{xgb_prob:.2f} Sent:{sentiment:.2f}) — " + ", ".join(reasons))
    except Exception as e:
        print(f"[CONFIDENCE ERROR] {e}")
        return (True, 50, f"ERROR {e}")

async def close_open_signals(db: Session, current_price: float, now: datetime.datetime, force_all: bool = False):
    """
    Menutup sinyal berstatus OPEN.
    Jika force_all=True: tutup semua sinyal OPEN (misal saat pergantian siklus 5 menit).
    Jika force_all=False: hanya tutup sinyal yang usianya sudah >= 300 detik (5 menit).
    """
    try:
        open_trades = db.query(TradeSignal).filter(TradeSignal.status == 'OPEN').all()
        closed_any = False

        for trade in open_trades:
            trade_time = trade.timestamp
            if isinstance(trade_time, str):
                try:
                    trade_time = datetime.datetime.fromisoformat(trade_time.replace('Z', ''))
                except Exception:
                    trade_time = now

            age_seconds = (now - trade_time).total_seconds() if trade_time else 9999

            if force_all or age_seconds >= 300:
                trade.exit_price = current_price

                if not trade.entry_price_share or trade.entry_price_share <= 0:
                    trade.entry_price_share = 0.5
                if not trade.shares_bought or trade.shares_bought <= 0:
                    trade.shares_bought = trade.quantity / trade.entry_price_share

                is_win = False
                if trade.direction == 'UP' and trade.exit_price > trade.entry_price:
                    is_win = True
                elif trade.direction == 'DOWN' and trade.exit_price < trade.entry_price:
                    is_win = True

                trade.status = 'WIN' if is_win else 'LOSS'

                # === AI-TUNABLE PROFIT/LOSS TARGETS (meta_config) ===
                try:
                    cfg = load_meta_config()
                    sp = cfg.get("strategy_parameters", {})
                    profit_mult = float(sp.get("profit_target_multiplier", 1.0))
                    stop_mult = float(sp.get("stop_loss_multiplier", 1.0))
                except Exception:
                    profit_mult, stop_mult = 1.0, 1.0

                # Realized PnL — payout disesuaikan dengan profit_target_multiplier
                if is_win:
                    payout = trade.shares_bought * 1.00 * profit_mult
                    trade.pnl = payout - trade.quantity
                else:
                    # stop_loss_multiplier: 0.95 berarti rugi 95% modal
                    trade.pnl = -trade.quantity * stop_mult

                trade.unrealized_pnl = None
                trade.current_token_price = None

                # Update consecutive win/loss counter (AI sizing feedback)
                try:
                    strategy_logic.update_trade_result(is_win)
                except Exception:
                    pass

                closed_any = True
                print(f"[{now}] [AUTO-CLOSE] Trade #{trade.id} [{trade.direction}] usia {age_seconds:.1f}s -> {trade.status} | Entry: ${trade.entry_price} | Exit: ${trade.exit_price} | Realized PNL: ${trade.pnl:.2f}")

                # Kirim Alert Telegram HANYA untuk Trade Selesai
                status_emoji = "🏆 WIN" if is_win else "❌ LOSS"
                alert_text = f"*{status_emoji} (Trade #{trade.id})*\n"
                alert_text += f"Arah: {trade.direction}\n"
                alert_text += f"PnL: ${trade.pnl:.2f}"
                asyncio.create_task(send_alert(alert_text))

                try:
                    trade_ts_str = trade_time.isoformat() if trade_time else now.isoformat()
                    ml_data_collector.update_ml_target(trade_ts_str, is_win)
                except Exception as ml_err:
                    print(f"[{now}] [ML_DATA ERROR] Gagal update target untuk trade #{trade.id}: {ml_err}")

        if closed_any:
            db.commit()
    except Exception as e:
        print(f"[{now}] Error closing open signals: {e}")
        try:
            db.rollback()
        except Exception:
            pass

async def mark_to_market_worker():
    """
    Background task setiap 3 detik — mark-to-market via CLOB best_bid.
    """
    print(f"[{datetime.datetime.now()}] Mark-to-Market Worker started (3s interval)...")

    while True:
        try:
            db = SessionLocal()
            try:
                open_trades = db.query(TradeSignal).filter(TradeSignal.status == 'OPEN').all()
                if open_trades:
                    for trade in open_trades:
                        try:
                            current_token_price = None
                            spread_value = None

                            if trade.token_id:
                                try:
                                    orderbook = await asyncio.to_thread(get_polymarket_orderbook, trade.token_id)
                                    if orderbook and orderbook.get('best_bid') is not None:
                                        current_token_price = orderbook['best_bid']
                                        spread_value = orderbook.get('spread')
                                except Exception as ob_err:
                                    print(f"[MTM ORDERBOOK ERROR] Trade #{trade.id}: {ob_err}")

                                if current_token_price is None:
                                    try:
                                        current_token_price = await asyncio.to_thread(get_current_token_price, trade.token_id)
                                    except Exception as price_err:
                                        print(f"[MTM PRICE FALLBACK ERROR] Trade #{trade.id}: {price_err}")

                            if current_token_price is not None:
                                trade.current_token_price = current_token_price
                            else:
                                # SAFETY FALLBACK: Jika orderbook/price API gagal, gunakan harga entry
                                # agar PnL tidak terjun ke -$1.00 secara tidak adil
                                current_token_price = trade.entry_price_share
                                trade.current_token_price = current_token_price
                                print(f"[MTM SAFETY] Orderbook kosong, PnL fallback ke entry: ${current_token_price}")

                            shares_bought = trade.shares_bought or (trade.quantity / (trade.entry_price_share or 0.5))
                            entry_price_share = trade.entry_price_share or 0.5
                            trade.unrealized_pnl = (current_token_price - entry_price_share) * shares_bought
                            if spread_value is not None:
                                trade.spread = spread_value
                            print(f"[MTM UPDATE] Trade #{trade.id} [{trade.direction}] | Price: ${current_token_price:.4f} | Spread: ${spread_value} | Unrealized PnL: ${trade.unrealized_pnl:.2f}")

                        except Exception as trade_err:
                            print(f"[MTM ERROR] Error updating trade #{trade.id}: {trade_err}")

                    db.commit()
            except Exception as db_err:
                print(f"[MTM DB ERROR]: {db_err}")
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        except Exception as e:
            print(f"[MTM OUTER ERROR]: {e}")

        await asyncio.sleep(3)

async def trading_worker():
    print(f"[{datetime.datetime.now()}] Trading Worker started...")
    current_cycle_minute = -1

    try:
        db_init = SessionLocal()
        init_price = engine.get_current_price()
        await close_open_signals(db_init, init_price, datetime.datetime.utcnow(), force_all=False)
        db_init.close()
    except Exception as e:
        print(f"[STARTUP CHECK] Error inspecting open signals: {e}")

    while True:
        now = datetime.datetime.utcnow()
        minute_bucket = (now.minute // 5) * 5

        # 1. Auto-close real-time tiap detik
        db = SessionLocal()
        try:
            current_price = engine.get_current_price()
            if current_price > 0:
                await close_open_signals(db, current_price, now, force_all=False)
        except Exception as e:
            print(f"[{now}] Error in continuous auto-close check: {e}")
        finally:
            try:
                db.close()
            except Exception:
                pass

        if current_cycle_minute == -1:
            current_cycle_minute = minute_bucket
            print(f"[{now}] Initialized at cycle minute: {minute_bucket}")

        if minute_bucket != current_cycle_minute:
            print(f"\n[{now}] === SIKLUS 5 MENIT BARU DIMULAI: Bucket {minute_bucket} ===")

            db = SessionLocal()
            try:
                current_price = engine.get_current_price()
                if current_price <= 0:
                    print(f"[{now}] Harga BTC belum tersedia. Menunggu data...")
                    current_cycle_minute = minute_bucket
                    continue

                # Circuit breaker check — Moss risk halt
                try:
                    bal_for_check = get_current_balance(db)
                    if is_circuit_breaker_active():
                        print(f"[{now}] [CIRCUIT BREAKER] Active — skip sinyal. Balance ${bal_for_check}")
                        current_cycle_minute = minute_bucket
                        continue
                    if bal_for_check >= CIRCUIT_TARGET and CIRCUIT_BREAKER_ENABLED:
                        _trigger_circuit_breaker(now)
                        print(f"[{now}] [CIRCUIT BREAKER] Target ${CIRCUIT_TARGET} tercapai — halt 24 jam")
                        current_cycle_minute = minute_bucket
                        continue
                except Exception as cb_e:
                    print(f"[CIRCUIT CHECK ERROR] {cb_e}")

                print(f"[{now}] [AUTO-CLOSE PRIORITY] Menutup semua posisi OPEN lama...")
                await close_open_signals(db, current_price, now, force_all=True)

                still_open = db.query(TradeSignal).filter(TradeSignal.status == 'OPEN').first()
                if still_open:
                    print(f"[{now}] [SINGLE-POSITION LOCK] Posisi #{still_open.id} masih OPEN. Skip.")
                    current_cycle_minute = minute_bucket
                    continue

                # Quant snapshot + confidence — Moss-adapted
                delta = engine.get_and_reset_delta()
                prices = [p for _, p in engine._price_history]
                trend = engine.get_trend_filter(prices)
                print(f"[{now}] Net Delta: {delta} | Trend (EMA200): {trend}")

                direction = 'UP' if delta > 0 else 'DOWN' if delta < 0 else None

                # Ambil snapshot quant (OBI, CVD momentum, volatility)
                quant_snapshot = {}
                obi_fresh = False
                obi_stale = True  # default: asumsi stale sampai terbukti fresh
                try:
                    quant_snapshot = engine.get_quant_snapshot()
                    quant_snapshot["net_delta"] = delta  # pakai delta siklus, bukan live
                    obi_fresh = quant_snapshot.get("obi_fresh", False)
                    obi_stale = quant_snapshot.get("obi_stale", True)
                    print(f"[{now}] [QUANT] OBI={quant_snapshot.get('orderbook_imbalance_ratio',0.5):.3f} CVDmom={quant_snapshot.get('cvd_momentum',0):.2f} fresh={obi_fresh} sideways={quant_snapshot.get('is_sideways')} range=${quant_snapshot.get('volatility_range',0):.1f}")
                except Exception as qs_e:
                    print(f"[QUANT SNAPSHOT ERROR] {qs_e}")
                    quant_snapshot = {"net_delta": delta, "orderbook_imbalance_ratio": 0.5, "orderbook_imbalance_raw": 0, "cvd_momentum": 0, "is_sideways": False, "volatility_range": 0}

                # === SAFETY: SKIP entry jika OBI basi (fetch gagal di siklus ini) ===
                if obi_stale:
                    print(f"[{now}] [SKIP CYCLE] OBI basi/stale — skip entry siklus ini agar tidak pakai data 5m lalu")
                    current_cycle_minute = minute_bucket
                    continue

                # === STRATEGY LOGIC: Indicators + Risk Score + Entry Gate ===
                indicators = {}
                risk_data = {"score": 50, "grade": "C", "reasons": []}
                if direction:
                    try:
                        cfg = load_meta_config()
                        params = cfg.get("strategy_parameters", {})
                        indicators = strategy_logic.calculate_custom_indicators(prices, params)
                        # inject consecutive loss state into snapshot for risk scoring
                        st = strategy_logic.load_strategy_state()
                        quant_snapshot["consecutive_losses"] = st.get("consecutive_losses", 0)
                        quant_snapshot.update({
                            "rsi": indicators.get("rsi", 50),
                            "atr": indicators.get("atr", 0),
                            "bb_width": indicators.get("bb_width", 0),
                            "ema_trend": indicators.get("ema_trend", 0),
                            "market_regime": indicators.get("regime", "SIDEWAYS"),
                        })
                        risk_data = strategy_logic.calculate_risk_score(indicators, quant_snapshot, cfg)
                        print(f"[{now}] [STRATEGY] RSI={indicators.get('rsi')} ATR={indicators.get('atr')} Regime={indicators.get('regime')} Risk={risk_data['score']}({risk_data['grade']}) | {', '.join(risk_data['reasons'][:3])}")

                        # Final entry gate (trend filter + reversal + risk)
                        allowed, adj_dir, gate_reason = strategy_logic.check_entry_conditions(
                            direction, indicators, trend, risk_data, quant_snapshot, cfg
                        )
                        print(f"[{now}] [GATE] {direction} -> {gate_reason}")
                        if not allowed:
                            direction = None
                        elif adj_dir and adj_dir != direction:
                            print(f"[{now}] [GATE] Direction reversed {direction} -> {adj_dir}")
                            direction = adj_dir
                    except Exception as sl_e:
                        print(f"[STRATEGY LOGIC ERROR] {sl_e}")
                        # Fallback to simple trend filter
                        if direction == 'UP' and trend == 'BEARISH':
                            direction = None
                        elif direction == 'DOWN' and trend == 'BULLISH':
                            direction = None

                if direction:
                    # === EXECUTION FILTER & CONFIDENCE ===
                    passed, score, reason = True, 50, "default"
                    try:
                        _, score, reason = evaluate_trade_confidence(direction, quant_snapshot)
                        print(f"[{now}] [CONFIDENCE] {direction} -> {reason}")
                    except Exception as cf_e:
                        print(f"[CONFIDENCE EVAL ERROR] {cf_e}")

                    # === DYNAMIC POSITION SIZING (AI risk-adaptive + drawdown guard) ===
                    trade_amount = TRADE_AMOUNT_USD_DEFAULT
                    try:
                        bal = get_current_balance(db)
                        cfg = load_meta_config()
                        # Risk-based sizing dari strategy_logic
                        sized, sz_reason = strategy_logic.determine_position_size(bal, risk_data, cfg)
                        print(f"[{now}] [SIZING] {sz_reason} -> ${sized}")

                        # Confidence override: score rendah tetap batasi ke $1
                        if score < cfg.get("confidence_threshold", 45):
                            trade_amount = 1.0
                            print(f"[{now}] [ADAPTIVE SIZING] Score {score} < threshold -> Force $1")
                        else:
                            trade_amount = sized

                        # Drawdown/peak-20 guard: cap ukuran ke aturan modal Raka
                        cap = calculate_position_size(bal)
                        if cap == 0:
                            print(f"[{now}] [SIZING] Circuit breaker / peak halt — skip entry")
                            current_cycle_minute = minute_bucket
                            continue
                        trade_amount = min(trade_amount, cap)

                        if trade_amount == 0:
                            print(f"[{now}] [SIZING] Circuit breaker active — skip entry")
                            current_cycle_minute = minute_bucket
                            continue

                        print(f"[{now}] [SIZING] Trade size: ${trade_amount} (Score: {score}, Cap: ${cap})")
                    except Exception as sz_e:
                        print(f"[[SIZING ERROR] {sz_e} — fallback ${TRADE_AMOUNT_USD_DEFAULT}")

                    try:
                        target_token_id = None
                        try:
                            tokens = await asyncio.to_thread(get_active_tokens)
                            if tokens:
                                target_token_id = tokens.get(direction)
                                print(f"[{now}] Token ID dinamis {direction}: {target_token_id}")
                            else:
                                print(f"[{now}] Gamma API tidak menemukan market aktif, mode simulasi.")
                        except Exception as e:
                            print(f"[{now}] [MARKET RESOLVER ERROR] {e}")

                        exec_success = False
                        entry_price_share = 0.5
                        shares_bought = trade_amount / entry_price_share
                        spread_value = None

                        if target_token_id:
                            try:
                                orderbook = await asyncio.to_thread(get_polymarket_orderbook, target_token_id)
                                if orderbook and orderbook.get('best_ask') is not None:
                                    best_ask = orderbook['best_ask']
                                    if best_ask > 0:
                                        entry_price_share = best_ask
                                        shares_bought = trade_amount / entry_price_share
                                        spread_value = orderbook.get('spread')
                                        print(f"[{now}] [ORDERBOOK ENTRY] best_ask=${best_ask} | spread=${spread_value}")
                            except Exception as e:
                                print(f"[{now}] [ORDERBOOK ERROR] Fallback price API: {e}")

                            if entry_price_share == 0.5:
                                try:
                                    live_share_price = await asyncio.to_thread(get_current_token_price, target_token_id)
                                    if live_share_price is not None and live_share_price > 0:
                                        entry_price_share = live_share_price
                                        shares_bought = trade_amount / entry_price_share
                                        print(f"[{now}] [FALLBACK PRICE API] price=${entry_price_share}")
                                except Exception as e:
                                    print(f"[{now}] [LIVE PRICE ERROR] Fallback $0.50: {e}")

                            try:
                                exec_success = await asyncio.to_thread(executor.check_liquidity_and_execute, target_token_id, trade_amount)
                            except Exception as e:
                                print(f"[{now}] [EXECUTION ERROR] {e}")

                        new_trade = TradeSignal(
                            timestamp=now,
                            symbol='BTC',
                            direction=direction,
                            entry_price=current_price,
                            quantity=trade_amount,
                            entry_price_share=entry_price_share,
                            shares_bought=shares_bought,
                            token_id=target_token_id,
                            current_token_price=entry_price_share,
                            unrealized_pnl=0.0,
                            status='OPEN',
                            spread=spread_value
                        )
                        db.add(new_trade)
                        db.commit()
                        db.refresh(new_trade)
                        print(f"[{now}] [NEW TRADE] #{new_trade.id} [{direction}] BTC ${current_price} | Share ${entry_price_share} | Shares {shares_bought:.2f} | Size ${trade_amount} | Conf {score} | Exec {exec_success}")

                        # === ML DATA & META-LABELING BRAIN ===
                        try:
                            price_change_5m = quant_snapshot.get("price_change_5m", 0.0)
                            
                            # Layer 2: XGBoost Meta-Labeling Prediction
                            xgb_prob = ml_brain.predict_probability(quant_snapshot)
                            print(f"[{now}] [ML BRAIN] Meta-Labeling XGBoost Win Probability: {xgb_prob:.2f}")

                            ml_features = {
                                'timestamp': now.isoformat(),
                                'net_delta': delta,
                                'cvd': engine.cvd,
                                'bid_ask_imbalance': quant_snapshot.get("orderbook_imbalance_raw", 0.0),
                                'price_change_5m': price_change_5m,
                                'polymarket_entry_price': entry_price_share,
                                'orderbook_imbalance_ratio': quant_snapshot.get("orderbook_imbalance_ratio", 0.5),
                                'orderbook_imbalance_raw': quant_snapshot.get("orderbook_imbalance_raw", 0.0),
                                'cvd_momentum': quant_snapshot.get("cvd_momentum", 0.0),
                                'volatility_range': quant_snapshot.get("volatility_range", 0.0),
                                'volatility_stdev': quant_snapshot.get("volatility_stdev", 0.0),
                                'is_sideways': quant_snapshot.get("is_sideways", False),
                                'confidence_score': score,
                                'position_size': trade_amount,
                                'imbalance_pass': True,
                                # Brain features
                                'market_regime': quant_snapshot.get("market_regime", "SIDEWAYS"),
                                'rsi': quant_snapshot.get("rsi", 50),
                                'atr': quant_snapshot.get("atr", 0),
                                'bb_width': quant_snapshot.get("bb_width", 0),
                                'ema_trend': quant_snapshot.get("ema_trend", 0),
                                'xgboost_prob': xgb_prob,
                                # Quant extras (Plan B)
                                'vwap_delta': quant_snapshot.get("vwap_delta", 0.0),
                                'funding_rate': quant_snapshot.get("funding_rate", 0.0)
                            }
                            ml_data_collector.log_ml_feature(ml_features)

                            # Auto-retrain check setiap 50 records baru
                            total_recs = ml_data_collector.get_ml_dataset_count()
                            with_target = ml_data_collector.get_ml_dataset_count_with_target().get("with_target", 0)
                            if total_recs > 0 and total_recs % 50 == 0 and with_target >= 50:
                                print(f"[{now}] [ML BRAIN] Mencapai {total_recs} record ({with_target} labeled). Auto-retrain...")
                                ml_brain.train_model()

                        except Exception as ml_err:
                            print(f"[{now}] [ML_DATA ERROR] {ml_err}")
                    except Exception as e:
                        print(f"[{now}] [CREATE SIGNAL ERROR] {e}")
                        try:
                            db.rollback()
                        except Exception:
                            pass
                else:
                    print(f"[{now}] Net Delta netral (0), tidak ada posisi baru dibuka.")

                current_cycle_minute = minute_bucket

            except Exception as e:
                print(f"[{now}] Error in trading worker cycle: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        await asyncio.sleep(1)
