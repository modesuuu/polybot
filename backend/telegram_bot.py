import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from database import SessionLocal
from models import TradeSignal
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

async def send_alert(message: str):
    """Fungsi untuk mengirim alert ke user."""
    if not TOKEN or not CHAT_ID or CHAT_ID == "123456789":
        print(f"[TELEGRAM] Alert batal dikirim (Token/ChatID belum diatur): {message}")
        return
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        await app.initialize()
        await app.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")
        await app.shutdown()
    except Exception as e:
        print(f"[TELEGRAM ALERT ERROR] {e}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /status"""
    db = SessionLocal()
    try:
        today = datetime.utcnow().replace(hour=0, minute=0, second=0)
        trades = db.query(TradeSignal).filter(TradeSignal.timestamp >= today).all()
        wins = sum(1 for t in trades if t.status == 'WIN')
        total = len(trades)
        pnl = sum(t.pnl for t in trades if t.pnl is not None)
        
        msg = f"*🤖 PolyBot Status*\n\n"
        msg += f"✅ Trades Hari Ini: {total}\n"
        msg += f"🏆 Wins: {wins}\n"
        msg += f"💰 Realized PnL: ${pnl:.2f}\n"
        msg += f"🕰️ UTC Time: {datetime.utcnow().strftime('%H:%M:%S')}"
        
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error mengambil status: {e}")
    finally:
        db.close()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk mendapatkan ChatID"""
    chat_id = update.effective_chat.id
    msg = f"Halo Raka! Bot aktif.\nChat ID kamu adalah: `{chat_id}`\n\nMasukkan angka ini ke file `.env` bagian `TELEGRAM_CHAT_ID=`"
    print(f"[TELEGRAM] Menerima /start dari Chat ID: {chat_id}")
    await update.message.reply_text(msg, parse_mode="Markdown")

async def run_telegram_bot():
    if not TOKEN:
        print("[TELEGRAM] Token tidak ditemukan, bot tidak aktif.")
        return
        
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("status", status_command))
        
        # Gunakan lifecycle yang benar untuk asyncio event loop FastAPI
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        print("[TELEGRAM] Bot polling started successfully in background task...")
    except Exception as e:
        print(f"[TELEGRAM START ERROR] {e}")
