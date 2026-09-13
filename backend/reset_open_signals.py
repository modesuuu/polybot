import datetime
import requests
from database import SessionLocal
from models import TradeSignal

def reset_stuck_signals():
    db = SessionLocal()
    try:
        # Ambil harga BTC live
        btc_price = 0.0
        try:
            r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5)
            if r.status_code == 200:
                btc_price = float(r.json()["price"])
        except Exception as e:
            print(f"Error fetching live BTC price: {e}")

        open_trades = db.query(TradeSignal).filter(TradeSignal.status == 'OPEN').all()
        print(f"Ditemukan {len(open_trades)} posisi berstatus OPEN.")

        if not open_trades:
            print("Tidak ada posisi yang perlu di-reset.")
            return

        now = datetime.datetime.utcnow()
        for trade in open_trades:
            exit_price = btc_price if btc_price > 0 else trade.entry_price
            trade.exit_price = exit_price

            # Hitung shares_bought jika belum ada
            if not trade.entry_price_share or trade.entry_price_share <= 0:
                trade.entry_price_share = 0.5
            if not trade.shares_bought or trade.shares_bought <= 0:
                trade.shares_bought = trade.quantity / trade.entry_price_share

            # Evaluasi WIN / LOSS
            is_win = False
            if trade.direction == 'UP' and trade.exit_price > trade.entry_price:
                is_win = True
            elif trade.direction == 'DOWN' and trade.exit_price < trade.entry_price:
                is_win = True

            trade.status = 'WIN' if is_win else 'LOSS'
            if is_win:
                payout = trade.shares_bought * 1.00
                trade.pnl = payout - trade.quantity
            else:
                trade.pnl = -trade.quantity

            trade.unrealized_pnl = None
            trade.current_token_price = None

            print(f"-> Reset Trade #{trade.id} [{trade.direction}] Entry: ${trade.entry_price} Exit: ${trade.exit_price} -> {trade.status} (PnL: ${trade.pnl:.2f})")

        db.commit()
        print("Semua posisi OPEN berhasil ditutup dan diselaraskan!")
    except Exception as e:
        print(f"Error saat reset signals: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    reset_stuck_signals()
