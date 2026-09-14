import asyncio
import json
import websockets
import time
import requests
import numpy as np
import pandas as pd
from datetime import datetime
from collections import deque
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BINANCE_DEPTH_URL = "https://api3.binance.com/api/v3/depth"
BINANCE_TICKER_URL = "https://api3.binance.com/api/v3/ticker/price"
BINANCE_PERP_DEPTH_URL = "https://fapi.binance.com/fapi/v1/depth"
BINANCE_PERP_PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
BINANCE_PERP_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36"}

class OrderFlowEngine:
    def __init__(self, symbol="btcusdt"):
        self.symbol = symbol.lower()
        self.ws_url = f"wss://data-stream.binance.vision/ws/{self.symbol}@aggTrade"
        self.ws_depth_url = f"wss://data-stream.binance.vision/ws/{self.symbol}@depth10@100ms"

        # Core state
        self.current_window_start = None
        self.net_delta = 0.0
        self.cvd = 0.0
        self.current_price = 0.0

        # Quant extensions
        self._cvd_history = deque(maxlen=300)
        self._price_history = deque(maxlen=300)
        self._price_window_start = 0.0
        self._window_start_ts = time.time()
        self.cvd_momentum = 0.0

        # Orderbook cache
        self._ob_cache = None
        self._ob_cache_ts = 0
        self._ob_cache_ttl = 2.0
        self.orderbook_imbalance_ratio = 0.5
        self.orderbook_imbalance_raw = 0.0
        self._obi_fresh = False

        # VWAP & Volatility
        self.vwap = 0.0
        self.vwap_volume_sum = 0.0
        self.vwap_pv_sum = 0.0
        self._volatility = 0.0
        self.funding_rate = 0.0

    def _safe_fetch(self, url, params=None, timeout=5):
        for attempt in range(2):
            try:
                r = requests.get(url, params=params, headers=HEADERS, timeout=timeout, verify=False)
                if r.status_code == 200 and r.text.strip():
                    return r.json()
            except Exception as e:
                if attempt == 1:
                    print(f"[OrderFlow] Fetch error {url}: {e}")
            time.sleep(0.5)
        return None

    def calculate_market_regime(self):
        try:
            if len(self._price_history) < 20:
                return "SIDEWAYS", 50, 0, 0, 0
            prices = [p for _, p in self._price_history]
            series = pd.Series(prices)
            delta = series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-10)
            rsi = float(100 - (100 / (1 + rs.iloc[-1])))
            ema20 = series.ewm(span=20).mean().iloc[-1]
            ema50 = series.ewm(span=50).mean().iloc[-1]
            atr = float((series.rolling(14).max() - series.rolling(14).min()).iloc[-1])
            std = float(series.rolling(20).std().iloc[-1])
            sma20 = float(series.rolling(20).mean().iloc[-1])
            bb_width = float((4 * std) / (sma20 + 1e-10))
            
            regime = "SIDEWAYS"
            if ema20 > ema50 and rsi > 55:
                regime = "TRENDING_UP"
            elif ema20 < ema50 and rsi < 45:
                regime = "TRENDING_DOWN"
            elif bb_width < 0.005:
                regime = "SQUEEZE"
                
            ema_trend = 1 if ema20 > ema50 else -1
            return regime, rsi, atr, bb_width, ema_trend
        except Exception:
            return "SIDEWAYS", 50, 0, 0, 0

    def update_vwap(self, price, volume):
        try:
            self.vwap_pv_sum += price * volume
            self.vwap_volume_sum += volume
            if self.vwap_volume_sum > 0:
                self.vwap = self.vwap_pv_sum / self.vwap_volume_sum
        except Exception:
            pass

    def get_vwap_delta(self):
        try:
            if self.vwap > 0 and self.current_price > 0:
                return self.current_price - self.vwap
            return 0.0
        except Exception:
            return 0.0

    def get_orderbook_imbalance_ratio(self, use_cache=True):
        try:
            now = time.time()
            # 1. Jika data dari WebSocket depth masih fresh (< 2 detik), gunakan langsung tanpa panggil REST!
            if self._ob_cache and (now - self._ob_cache_ts) < self._ob_cache_ttl:
                return self._ob_cache

            # 2. Fallback jika WebSocket sempat disconnect (REST call aman)
            data = self._safe_fetch(BINANCE_DEPTH_URL, params={"symbol": self.symbol.upper(), "limit": 10})
            if not data:
                # Jika cache sebelumnya masih ada (meskipun agak lewat TTL), gunakan daripada SKIP
                if self._ob_cache:
                    return self._ob_cache
                self._obi_fresh = False
                return {"ratio": 0.5, "raw": 0.0, "bid_vol": 0, "ask_vol": 0, "stale": True}

            bids = data.get("bids", [])[:10]
            asks = data.get("asks", [])[:10]
            bid_vol = sum(float(b[1]) for b in bids)
            ask_vol = sum(float(a[1]) for a in asks)
            total = bid_vol + ask_vol
            
            if total <= 0:
                result = {"ratio": 0.5, "raw": 0.0, "bid_vol": bid_vol, "ask_vol": ask_vol}
            else:
                ratio = bid_vol / total
                raw = (bid_vol - ask_vol) / total
                result = {"ratio": ratio, "raw": raw, "bid_vol": bid_vol, "ask_vol": ask_vol}

            self._ob_cache = result
            self._ob_cache_ts = now
            self._obi_fresh = True
            self.orderbook_imbalance_ratio = result["ratio"]
            self.orderbook_imbalance_raw = result["raw"]
            return result
        except Exception as e:
            print(f"[OrderFlow] OBI error: {e}")
            self._obi_fresh = False
            return {"ratio": 0.5, "raw": 0.0, "bid_vol": 0, "ask_vol": 0, "stale": True}

    def get_cvd_momentum(self):
        try:
            return float(self.cvd_momentum)
        except Exception:
            return 0.0

    def get_price_change_5m(self):
        try:
            if self._price_window_start and self.current_price:
                return self.current_price - self._price_window_start
            if len(self._price_history) >= 2:
                base = self._price_history[0][1]
                return self.current_price - base
            return 0.0
        except Exception:
            return 0.0

    def get_volatility_metrics(self):
        try:
            if len(self._price_history) < 5:
                return {"range_usd": 0.0, "stdev": 0.0, "is_sideways": False}
            prices = [p for _, p in self._price_history]
            prange = max(prices) - min(prices)
            mean = sum(prices) / len(prices)
            var = sum((x - mean) ** 2 for x in prices) / len(prices)
            stdev = var ** 0.5
            is_sideways = prange < 35 and stdev < 12
            self._volatility = prange
            return {"range_usd": prange, "stdev": stdev, "is_sideways": is_sideways}
        except Exception:
            return {"range_usd": 0.0, "stdev": 0.0, "is_sideways": False}

    def get_trend_filter(self, prices):
        try:
            if len(prices) < 200:
                return "NEUTRAL"
            ema200 = np.mean(prices[-200:])
            current_price = prices[-1]
            return "BULLISH" if current_price > ema200 else "BEARISH"
        except:
            return "NEUTRAL"

    def get_funding_rate(self):
        try:
            data = self._safe_fetch(BINANCE_PERP_FUNDING_URL, params={"symbol": "BTCUSDT"})
            if data and isinstance(data, list) and data:
                return float(data[0].get("fundingRate", 0))
        except Exception:
            pass
        return 0.0

    def get_quant_snapshot(self):
        try:
            regime, rsi, atr, bb_width, ema_trend = self.calculate_market_regime()
        except Exception:
            regime, rsi, atr, bb_width, ema_trend = "SIDEWAYS", 50, 0, 0, 0

        try:
            ob = self.get_orderbook_imbalance_ratio()
        except Exception:
            ob = {"ratio": 0.5, "raw": 0.0, "bid_vol": 0, "ask_vol": 0, "stale": True}
        
        try:
            price_change = self.get_price_change_5m()
        except Exception:
            price_change = 0.0
        
        try:
            vol = self.get_volatility_metrics()
        except Exception:
            vol = {"range_usd": 0.0, "stdev": 0.0, "is_sideways": False}
        
        try:
            cvd_mom = self.get_cvd_momentum()
        except Exception:
            cvd_mom = 0.0

        try:
            funding_rate = self.get_funding_rate()
        except Exception:
            funding_rate = 0.0

        try:
            vwap_delta = self.get_vwap_delta()
        except Exception:
            vwap_delta = 0.0
        
        return {
            "net_delta": self.net_delta,
            "cvd": self.cvd,
            "cvd_momentum": cvd_mom,
            "orderbook_imbalance_ratio": ob["ratio"],
            "orderbook_imbalance_raw": ob["raw"],
            "bid_vol": ob["bid_vol"],
            "ask_vol": ob["ask_vol"],
            "obi_fresh": self._obi_fresh,
            "obi_stale": ob.get("stale", False),
            "price_change_5m": price_change,
            "volatility_range": vol["range_usd"],
            "volatility_stdev": vol["stdev"],
            "is_sideways": vol["is_sideways"],
            "current_price": self.current_price,
            "vwap_delta": vwap_delta,
            "funding_rate": funding_rate,
            "market_regime": regime,
            "rsi": rsi,
            "atr": atr,
            "bb_width": bb_width,
            "ema_trend": ema_trend
        }

    def get_and_reset_delta(self):
        delta = self.net_delta
        self.net_delta = 0.0
        try:
            self._price_window_start = self.current_price if self.current_price else self._price_window_start
            self._window_start_ts = time.time()
        except Exception:
            pass
        return delta

    def get_current_price(self):
        if self.current_price > 0:
            return self.current_price
        try:
            data = self._safe_fetch(BINANCE_TICKER_URL, params={"symbol": self.symbol.upper()})
            if data:
                self.current_price = float(data.get("price", 0))
        except Exception:
            pass
        return self.current_price

    async def connect_and_listen(self):
        """WebSocket listener untuk aggTrade (SPOT) dan depth10 (Orderbook)."""
        asyncio.create_task(self._connect_depth_ws())
        while True:
            try:
                print(f"[OrderFlow] Connecting to Trade WS: {self.ws_url}...")
                async with websockets.connect(self.ws_url) as ws:
                    print("[OrderFlow] Connected to Binance Trade WS.")
                    while True:
                        msg = await ws.recv()
                        self._process_message(json.loads(msg))
            except Exception as e:
                print(f"[OrderFlow] Trade WS Error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _connect_depth_ws(self):
        """WebSocket listener terpisah untuk orderbook depth (100ms real-time)."""
        while True:
            try:
                print(f"[OrderFlow] Connecting to Depth WS: {self.ws_depth_url}...")
                async with websockets.connect(self.ws_depth_url) as ws:
                    print("[OrderFlow] Connected to Binance Depth WS (Real-time OBI).")
                    while True:
                        msg = await ws.recv()
                        self._process_depth_message(json.loads(msg))
            except Exception as e:
                print(f"[OrderFlow] Depth WS Error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    def _process_depth_message(self, msg):
        """Proses pesan depth10@100ms real-time untuk update OBI cache secara instan."""
        try:
            bids = msg.get("bids", [])[:10]
            asks = msg.get("asks", [])[:10]
            bid_vol = sum(float(b[1]) for b in bids)
            ask_vol = sum(float(a[1]) for a in asks)
            total = bid_vol + ask_vol
            
            if total <= 0:
                result = {"ratio": 0.5, "raw": 0.0, "bid_vol": bid_vol, "ask_vol": ask_vol}
            else:
                ratio = bid_vol / total
                raw = (bid_vol - ask_vol) / total
                result = {"ratio": ratio, "raw": raw, "bid_vol": bid_vol, "ask_vol": ask_vol}

            self._ob_cache = result
            self._ob_cache_ts = time.time()
            self._obi_fresh = True
            self.orderbook_imbalance_ratio = result["ratio"]
            self.orderbook_imbalance_raw = result["raw"]
        except Exception as e:
            print(f"[OrderFlow] _process_depth_message error: {e}")

    def _process_message(self, msg):
        """Proses aggTrade message untuk CVD dan Delta."""
        try:
            # m: msg type (aggTrade), p: price, q: quantity, m: is_buyer_maker
            p = float(msg['p'])
            q = float(msg['q'])
            is_buyer_maker = msg['m']
            
            self.current_price = p
            if self._price_window_start == 0:
                self._price_window_start = p
            
            # Buyer maker = SELL (hit bid), Not buyer maker = BUY (hit lift)
            side_delta = -q if is_buyer_maker else q
            self.net_delta += side_delta
            self.cvd += side_delta
            
            # Update VWAP
            self.update_vwap(p, q)
            
            # History untuk indikator
            ts = time.time()
            self._price_history.append((ts, p))
            self._cvd_history.append((ts, self.cvd))
            
            # CVD Momentum (slope 60s)
            if len(self._cvd_history) > 60:
                self.cvd_momentum = self.cvd - self._cvd_history[0][1]
        except Exception as e:
            print(f"[OrderFlow] _process_message error: {e}")

engine = OrderFlowEngine()
