"""
strategy_logic.py — Central Strategy Module (AI-editable)
Semua rumus trading, risk scoring, dan entry/exit logic ada di sini.
AI Agent diperbolehkan memodifikasi fungsi-fungsi ini.
"""
import numpy as np
import json
import os
import datetime

# ============================================================
# 1. TECHNICAL INDICATORS
# ============================================================

def calculate_custom_indicators(prices, params=None):
    """
    Hitung semua indikator teknikal dari array harga.
    Return: dict {rsi, atr, ema_short, ema_long, ema_trend, bb_upper, bb_lower, bb_width, regime}
    """
    if params is None:
        params = {}
    try:
        if len(prices) < 30:
            return {"rsi": 50, "atr": 0, "ema_short": 0, "ema_long": 0,
                    "ema_trend": 0, "bb_upper": 0, "bb_lower": 0,
                    "bb_width": 0, "regime": "NEUTRAL"}

        prices_arr = np.array(prices, dtype=float)

        # --- RSI ---
        rsi_period = params.get("rsi_period", 14)
        deltas = np.diff(prices_arr)
        gain = np.where(deltas > 0, deltas, 0)
        loss = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gain[-rsi_period:]) if len(gain) >= rsi_period else np.mean(gain)
        avg_loss = np.mean(loss[-rsi_period:]) if len(loss) >= rsi_period else np.mean(loss)
        rs = avg_gain / avg_loss if avg_loss > 0.001 else 100
        rsi = float(100 - (100 / (1 + rs)))

        # --- ATR (Average True Range) ---
        atr_period = params.get("atr_period", 14)
        if len(prices_arr) >= atr_period + 1:
            high = prices_arr[-(atr_period):]
            low = prices_arr[-(atr_period):]
            tr_vals = np.abs(np.diff(high)) if len(high) > 1 else np.array([0])
            atr = float(np.mean(tr_vals)) if len(tr_vals) > 0 else 0.0
        else:
            atr = float(np.std(prices_arr))

        # --- EMA ---
        ema_short_p = params.get("ema_short", 9)
        ema_long_p = params.get("ema_long", 21)
        ema_short = float(np.mean(prices_arr[-ema_short_p:])) if len(prices_arr) >= ema_short_p else float(prices_arr[-1])
        ema_long = float(np.mean(prices_arr[-ema_long_p:])) if len(prices_arr) >= ema_long_p else float(prices_arr[-1])
        ema_trend = 1 if ema_short > ema_long else -1  # 1=bullish, -1=bearish

        # --- Bollinger Bands ---
        bb_period = params.get("bb_period", 20)
        bb_mult = params.get("bb_multiplier", 2.0)
        if len(prices_arr) >= bb_period:
            bb_mean = float(np.mean(prices_arr[-bb_period:]))
            bb_std = float(np.std(prices_arr[-bb_period:]))
            bb_upper = bb_mean + (bb_mult * bb_std)
            bb_lower = bb_mean - (bb_mult * bb_std)
            bb_width = float((bb_upper - bb_lower) / bb_mean) if bb_mean > 0 else 0
        else:
            bb_upper = bb_lower = float(prices_arr[-1])
            bb_width = 0

        # --- Market Regime ---
        regime = _classify_regime(rsi, atr, ema_trend, bb_width, prices_arr)

        return {
            "rsi": round(rsi, 2),
            "atr": round(atr, 4),
            "ema_short": round(ema_short, 2),
            "ema_long": round(ema_long, 2),
            "ema_trend": ema_trend,
            "bb_upper": round(bb_upper, 2),
            "bb_lower": round(bb_lower, 2),
            "bb_width": round(bb_width, 6),
            "regime": regime
        }
    except Exception as e:
        print(f"[STRATEGY ERROR] calculate_custom_indicators: {e}")
        return {"rsi": 50, "atr": 0, "ema_short": 0, "ema_long": 0,
                "ema_trend": 0, "bb_upper": 0, "bb_lower": 0,
                "bb_width": 0, "regime": "NEUTRAL"}


def _classify_regime(rsi, atr, ema_trend, bb_width, prices_arr):
    """Klasifikasi market regime berdasarkan multi-indikator."""
    try:
        if atr == 0:
            return "NEUTRAL"

        # High volatility: BB width lebar + ATR tinggi
        avg_atr = float(np.std(prices_arr[-50:])) if len(prices_arr) >= 50 else atr
        if atr > avg_atr * 1.5:
            return "HIGH_VOLATILITY"

        # Trending
        if abs(rsi - 50) > 15:
            if rsi > 65:
                return "TRENDING_UP"
            elif rsi < 35:
                return "TRENDING_DOWN"

        # EMA trend confirmation
        if ema_trend == 1 and rsi > 55:
            return "TRENDING_UP"
        elif ema_trend == -1 and rsi < 45:
            return "TRENDING_DOWN"

        return "SIDEWAYS"
    except Exception:
        return "NEUTRAL"


# ============================================================
# 2. RISK SCORING ENGINE
# ============================================================

def calculate_risk_score(indicators, orderbook_data, config):
    """
    Composite risk score dari 0 (terbaik) ke 100 (terburuk).
    Skor rendah = market tenang, mudah prediksi.
    Skor tinggi = market chaos, hindari trade.
    """
    try:
        score = 0
        reasons = []

        rsi = indicators.get("rsi", 50)
        atr = indicators.get("atr", 0)
        bb_width = indicators.get("bb_width", 0)
        regime = indicators.get("regime", "SIDEWAYS")

        # --- RSI Risk ---
        if rsi > 75 or rsi < 25:
            score += 25
            reasons.append(f"RSI extreme ({rsi:.0f})")
        elif rsi > 65 or rsi < 35:
            score += 10
            reasons.append(f"RSI elevated ({rsi:.0f})")

        # --- Volatility Risk ---
        vol_threshold = config.get("strategy_parameters", {}).get("volatility_threshold_multiplier", 0.04)
        if bb_width > vol_threshold * 2:
            score += 20
            reasons.append(f"BB Width terlalu lebar ({bb_width:.4f})")
        elif bb_width > vol_threshold:
            score += 10
            reasons.append(f"BB Width moderat ({bb_width:.4f})")

        # --- Regime Risk ---
        if regime == "HIGH_VOLATILITY":
            score += 20
            reasons.append("HIGH_VOLATILITY regime")
        elif regime == "SIDEWAYS":
            score += 15
            reasons.append("SIDEWAYS regime")

        # --- Orderbook Risk ---
        obi = orderbook_data.get("orderbook_imbalance_ratio", 0.5)
        if 0.45 < obi < 0.55:
            score += 10
            reasons.append(f"OBI netral ({obi:.3f})")

        # --- Consecutive Loss Penalty ---
        consec = orderbook_data.get("consecutive_losses", 0)
        if consec >= 5:
            score += 30
            reasons.append(f"Consecutive loss {consec}x")
        elif consec >= 3:
            score += 15
            reasons.append(f"Consecutive loss {consec}x")

        score = min(100, max(0, score))
        return {"score": score, "reasons": reasons, "grade": _grade_risk(score)}
    except Exception as e:
        return {"score": 50, "reasons": [f"error: {e}"], "grade": "C"}


def _grade_risk(score):
    if score <= 15: return "A"  # Excellent — full size
    if score <= 30: return "B"  # Good — normal size
    if score <= 50: return "C"  # Caution — reduced size
    if score <= 70: return "D"  # Bad — minimum size
    return "F"                   # Terrible — skip


# ============================================================
# 3. POSITION SIZING
# ============================================================

def determine_position_size(balance, risk_score_data, config):
    """
    Adaptive position sizing berdasarkan balance + risk score + consecutive loss.
    Returns: (size_usd, reason)
    """
    try:
        risk_score = risk_score_data.get("score", 50)
        grade = risk_score_data.get("grade", "C")
        consecutive_losses = 0
        for r in risk_score_data.get("reasons", []):
            if "Consecutive loss" in r:
                consecutive_losses = int(r.split("loss ")[1].split("x")[0])
                break

        sp = config.get("strategy_parameters", {})

        # Base tier dari balance
        if balance >= 10:
            base = 5.0
        elif balance >= 5:
            base = 3.0
        elif balance >= 2:
            base = 2.0
        elif balance >= 1:
            base = 1.0
        else:
            return 0, "Balance habis"

        # Risk-adjusted sizing
        if grade == "A":
            size = base
        elif grade == "B":
            size = base * 0.8
        elif grade == "C":
            size = max(1.0, base * 0.5)
        elif grade == "D":
            size = 1.0
        else:
            return 1.0, "Risk F — minimum"

        # Consecutive loss recovery
        if consecutive_losses >= 5:
            size = 1.0
        elif consecutive_losses >= 3:
            size = max(1.0, size * 0.5)

        # Circuit breaker recovery mode
        if balance <= 5:
            size = 1.0

        size = round(max(0, min(size, balance)), 2)
        reason = f"Grade {grade} (Risk {risk_score}) | Balance ${balance:.2f} | ConsecLoss {consecutive_losses}"
        return size, reason
    except Exception as e:
        return 1.0, f"Error sizing: {e}"


# ============================================================
# 4. ENTRY CONDITIONS (FINAL GO/NO-GO)
# ============================================================

def check_entry_conditions(direction, indicators, trend_ema200, risk_score_data, quant_snapshot, config):
    """
    Final gate: bolehkah masuk trade?
    Return: (allowed: bool, adjusted_direction: str|None, reason: str)
    """
    try:
        rsi = indicators.get("rsi", 50)
        ema_trend = indicators.get("ema_trend", 0)
        regime = indicators.get("regime", "SIDEWAYS")
        risk_score = risk_score_data.get("score", 50)
        grade = risk_score_data.get("grade", "C")

        reasons = []

        # Gate 1: Risk too high
        if grade == "F":
            return False, None, f"SKIP: Risk Grade F ({risk_score})"

        # Gate 2: Trend filter (EMA 200) — mode-aware
        # mode: "ON" = block against trend (legacy), "OFF" = no filter (delta murni),
        #       "REVERSAL" = dorong melawan tren (mean-reversion 5m)
        trend_mode = (config or {}).get("trend_filter_mode", "ON")

        if trend_mode == "OFF":
            pass  # no trend gate, delta murni
        elif trend_mode == "REVERSAL":
            if direction == "UP" and trend_ema200 == "BEARISH":
                return True, "DOWN", f"REVERSAL: Trend BEARISH flip UP → DOWN"
            elif direction == "DOWN" and trend_ema200 == "BULLISH":
                return True, "UP", f"REVERSAL: Trend BULLISH flip DOWN → UP"
        else:  # ON (default)
            if direction == "UP" and trend_ema200 == "BEARISH":
                reasons.append("Trend BEARISH blocks UP")
                # Allow if RSI oversold (reversal signal)
                if rsi < 30:
                    reasons.append(f"RSI oversold ({rsi}) — reversal allowed")
                else:
                    return False, None, f"SKIP: {', '.join(reasons)}"
            elif direction == "DOWN" and trend_ema200 == "BULLISH":
                reasons.append("Trend BULLISH blocks DOWN")
                if rsi > 70:
                    reasons.append(f"RSI overbought ({rsi}) — reversal allowed")
                else:
                    return False, None, f"SKIP: {', '.join(reasons)}"

        # Gate 3: Extreme RSI — reverse direction
        if direction == "UP" and rsi > 80:
            return True, "DOWN", f"REVERSE: RSI overbought ({rsi:.0f}) → DOWN"
        if direction == "DOWN" and rsi < 20:
            return True, "UP", f"REVERSE: RSI oversold ({rsi:.0f}) → UP"

        # Gate 4: High volatility — reduce caution
        if regime == "HIGH_VOLATILITY" and risk_score > 50:
            return False, None, f"SKIP: HIGH_VOLATILITY + Risk {risk_score}"

        return True, direction, f"PASS: Grade {grade} RSI={rsi:.0f} Regime={regime}"
    except Exception as e:
        return True, direction, f"PASS (error fallback): {e}"


# ============================================================
# 5. SPREAD COST ESTIMATION
# ============================================================

def estimate_spread_cost(entry_price, spread=None):
    """
    Estimasi biaya spread Polymarket.
    Spread tinggi = profit margin berkurang.
    """
    try:
        if spread is not None and spread > 0:
            return float(spread)
        # Default estimasi berdasarkan harga entry
        # Spread Polymarket tipikal: $0.01-0.05
        if entry_price > 0.7:
            return 0.03  # Deep in/out of money = wider spread
        elif entry_price < 0.3:
            return 0.03
        else:
            return 0.015  # Near ATM = tighter spread
    except Exception:
        return 0.02


# ============================================================
# 6. ADAPTIVE MIN MOVE THRESHOLD
# ============================================================

def get_min_btc_move(atr, balance, config):
    """
    Minimum BTC price movement yang dibutuhkan agar trade layak masuk.
    Jika BTC tidak bergerak lebih dari ini, spread fee akan menghabiskan profit.
    """
    try:
        sp = config.get("strategy_parameters", {})
        profit_mult = sp.get("profit_target_multiplier", 1.2)

        # Minimum move = ATR * multiplier
        # ATR sudah dalam satuan BTC price, multiplier menyesuaikan
        min_move = atr * profit_mult * 0.1  # 10% dari ATR * multiplier

        # Jika balance kecil, threshold lebih ketat
        if balance <= 5:
            min_move *= 1.5

        return max(min_move, 5.0)  # Minimal $5 BTC move
    except Exception:
        return 10.0


# ============================================================
# 7. CONFIG VALIDATION
# ============================================================

def validate_config(config):
    """Validasi dan clamp meta_config agar tetap dalam range aman."""
    try:
        sp = config.get("strategy_parameters", {})

        # Clamp RSI period
        sp["rsi_period"] = max(5, min(50, sp.get("rsi_period", 14)))
        sp["ema_short"] = max(3, min(30, sp.get("ema_short", 9)))
        sp["ema_long"] = max(10, min(100, sp.get("ema_long", 21)))
        sp["bb_period"] = max(10, min(50, sp.get("bb_period", 20)))
        sp["bb_multiplier"] = max(1.0, min(4.0, sp.get("bb_multiplier", 2.0)))

        # Clamp profit/loss
        sp["profit_target_multiplier"] = max(0.5, min(3.0, sp.get("profit_target_multiplier", 1.2)))
        sp["stop_loss_multiplier"] = max(0.5, min(1.0, sp.get("stop_loss_multiplier", 0.95)))

        config["strategy_parameters"] = sp

        # Clamp global
        config["obi_threshold"] = max(0.3, min(0.95, config.get("obi_threshold", 0.65)))
        config["confidence_threshold"] = max(20, min(90, config.get("confidence_threshold", 50)))
        config["min_sentiment_score"] = max(-1.0, min(1.0, config.get("min_sentiment_score", -0.3)))

        # Clamp trend filter mode — only allow ON/OFF/REVERSAL (anti AI hallucination)
        tfm = str(config.get("trend_filter_mode", "ON")).upper()
        if tfm not in ("ON", "OFF", "REVERSAL"):
            tfm = "ON"
        config["trend_filter_mode"] = tfm

        return config
    except Exception:
        return config


# ============================================================
# 8. BOT STATE PERSISTENCE (consecutive loss tracking)
# ============================================================

STATE_FILE = os.path.join(os.path.dirname(__file__), ".strategy_state.json")

def load_strategy_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"consecutive_losses": 0, "consecutive_wins": 0, "last_trade_result": None}

def save_strategy_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass

def update_trade_result(is_win):
    """Update consecutive loss/win counter setelah trade selesai."""
    try:
        state = load_strategy_state()
        if is_win:
            state["consecutive_losses"] = 0
            state["consecutive_wins"] = state.get("consecutive_wins", 0) + 1
        else:
            state["consecutive_wins"] = 0
            state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1
        state["last_trade_result"] = "WIN" if is_win else "LOSS"
        state["last_updated"] = datetime.datetime.utcnow().isoformat()
        save_strategy_state(state)
        return state
    except Exception:
        return {"consecutive_losses": 0, "consecutive_wins": 0}
