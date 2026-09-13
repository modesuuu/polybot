import os
import requests
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
# GUNAKAN ORDERARGS (Ini adalah class universal di Polymarket untuk Limit & Market)
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
from py_clob_client.exceptions import PolyApiException
import time

load_dotenv()

PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY")
CHAIN_ID = int(os.getenv("POLYMARKET_CHAIN_ID", 137))
HOST = "https://clob.polymarket.com"

class PolymarketExecutor:
    def __init__(self):
        self.is_configured = bool(PRIVATE_KEY and PRIVATE_KEY != "your_evm_private_key_here")
        self.client = None
        
        if self.is_configured:
            try:
                self.client = ClobClient(HOST, key=PRIVATE_KEY, chain_id=CHAIN_ID)
                self.client.set_creds(self.client.create_or_derive_creds())
                print("[PolymarketExecutor] ClobClient initialized successfully.")
            except Exception as e:
                print(f"[PolymarketExecutor] Failed to initialize ClobClient: {e}")
                self.is_configured = False
        else:
            print("[PolymarketExecutor] Private key not configured.")

    def check_liquidity_and_execute(self, token_id, amount_usd, max_price=0.75):
        """Eksekusi instan (FOK)"""
        if not self.is_configured: return False
        try:
            order_book = self.client.get_order_book(token_id)
            asks = order_book.asks
            if not asks: return False
                
            best_ask = sorted(asks, key=lambda x: float(x.price))[0]
            best_ask_price = float(best_ask.price)
            
            if best_ask_price > max_price:
                print(f"[FOK] Harga {best_ask_price} > Limit {max_price}. Skip.")
                return False

            shares = amount_usd / best_ask_price
            order_args = OrderArgs(price=best_ask_price, size=shares, side=BUY, token_id=token_id)
            signed_order = self.client.create_order(order_args)
            resp = self.client.post_order(signed_order, OrderType.FOK)
            return bool(resp and resp.get('success'))
        except Exception as e:
            print(f"[FOK Error] {e}")
            return False

    def smart_order_router(self, token_id, amount_usd, max_price=0.75):
        """
        INI ADALAH FUNGSI LIMIT ORDER YANG KAMU MAU.
        Menggunakan OrderArgs + OrderType.GTC agar order TETAP ANTRI (pasif).
        """
        # 1. Coba beli langsung dulu (FOK)
        if self.check_liquidity_and_execute(token_id, amount_usd, max_price):
            print("[SOR] Berhasil eksekusi instan (FOK).")
            return True

        # 2. Jika gagal beli langsung, pasang LIMIT ORDER (Antri)
        print(f"[SOR] Likuiditas tipis, beralih ke LIMIT ORDER (Antri di pasar)...")
        try:
            # Ambil harga terakhir/mid untuk antri di harga bagus
            res = requests.get(f"{HOST}/price?token_id={token_id}", timeout=5)
            mid_price = float(res.json().get('price', 0.5))
            
            # Pasang harga sedikit di bawah mid (agar dapat harga diskon)
            # Ini yang bikin bot profesional: dapet harga lebih murah dari market price.
            limit_price = round(mid_price * 0.99, 4) 
            shares = amount_usd / limit_price
            
            # --- FUNGSI LIMIT ORDER ASLI ---
            order_args = OrderArgs(
                price=limit_price,
                size=shares,
                side=BUY,
                token_id=token_id
            )
            signed_order = self.client.create_order(order_args)
            
            # OrderType.GTC = Good Till Cancel (Order TETAP ADA di market sesi depan)
            resp = self.client.post_order(signed_order, OrderType.GTC)
            
            if resp and resp.get('success'):
                print(f"[LIMIT SUCCESS] Order ID: {resp.get('orderID')} dipasang di harga ${limit_price}")
                return True
            return False
        except Exception as e:
            print(f"[SOR Limit Error] {e}")
            return False

executor = PolymarketExecutor()
