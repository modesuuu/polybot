import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import text
from database import SessionLocal

# Load env variables from backend/.env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Paths
BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "meta_config.json")
STRATEGY_PATH = os.path.join(BASE_DIR, "strategy_logic.py")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def run_neuro_optimizer():
    """
    Menjalankan riset kuantitatif menggunakan OpenRouter LLM.
    Mengevaluasi trade di NeonDB dan meng-update meta_config.json.
    """
    print(f"[{datetime.now()}] [NEURO-OPTIMIZER] Memulai Daily Quant Audit via NeonDB...")
    
    db = SessionLocal()
    try:
        # 1. Tarik Rekap dari DB (portable: SQLite & PostgreSQL)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        query = text("""
            SELECT status, pnl
            FROM trade_signals
            WHERE timestamp >= :cutoff
            AND status IN ('WIN', 'LOSS')
        """)
        trades = db.execute(query, {"cutoff": cutoff}).fetchall()

        total_trades = len(trades)
        if total_trades < 5:
            # Fallback: jika 24 jam kurang, ambil 10 trade terakhir tanpa batas waktu
            print("[NEURO-OPTIMIZER] Data 24 jam minim. Mengambil 10 trade terakhir untuk analisa...")
            query = text("SELECT status, pnl FROM trade_signals WHERE status IN ('WIN', 'LOSS') ORDER BY id DESC LIMIT 10")
            trades = db.execute(query).fetchall()
            total_trades = len(trades)

        if total_trades < 3:
            print("[NEURO-OPTIMIZER] Trade tidak cukup untuk optimasi.")
            return

        wins = sum(1 for t in trades if t[0] == 'WIN')
        win_rate = (wins / total_trades) * 100
        total_pnl = sum(float(t[1]) for t in trades if t[1] is not None)

        # 2. Baca Konfigurasi Saat Ini
        with open(CONFIG_PATH, "r") as f:
            current_config = json.load(f)

        # 3. Minta OpenRouter (Hermes/DeepSeek) Menganalisa & Menyetel Ulang
        prompt = f"""
        Kamu adalah Senior Quantitative Researcher Hedge Fund. Evaluasi performa trading bot BTC 5-menit berikut:
        - Sample Trades: {total_trades}
        - Win Rate: {win_rate:.2f}%
        - Total PnL: ${total_pnl:.2f}

        Konfigurasi Parameter Saat Ini:
        {json.dumps(current_config, indent=2)}

        Tugasmu:
        1. Berikan analisa objektif mengapa winrate/PnL tersebut terjadi berdasarkan parameter.
        2. Sesuaikan angka parameter (obi_threshold, confidence_threshold, rsi_period, dll) untuk meningkatkan winrate.
        
        Jawab HANYA dalam format JSON valid tanpa format markdown lain:
        {{
            "reasoning": "Penjelasan analisamu...",
            "new_config": {{ ...isi konfigurasi yang diperbarui... }}
        }}
        """

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "nousresearch/hermes-3-llama-3.1-405b",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2
            },
            timeout=60
        )
        
        if response.status_code != 200:
            print(f"[NEURO-OPTIMIZER ERROR] API Server mengembalikan error {response.status_code}: {response.text}")
            return

        result_json = response.json()
        if 'choices' not in result_json:
            print(f"[NEURO-OPTIMIZER ERROR] Format respon tidak valid: {result_json}")
            return

        raw_content = result_json['choices'][0]['message']['content'].strip()
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:-3].strip()
        elif raw_content.startswith("```"):
            raw_content = raw_content[3:-3].strip()

        parsed = json.loads(raw_content)
        reasoning = parsed.get("reasoning", "Tidak ada analisa spesifik.")
        updated_config = parsed.get("new_config", current_config)

        # 3b. VALIDASI: clamp parameter agar AI tidak set nilai ekstrem/hallucination
        try:
            import strategy_logic
            updated_config = strategy_logic.validate_config(updated_config)
            print("[NEURO-OPTIMIZER] Config AI tervalidasi (clamp aman).")
        except Exception as ve:
            print(f"[NEURO-OPTIMIZER] Validasi gagal ({ve}) — pakai config lama.")
            updated_config = current_config

        # 4. Terapkan Konfigurasi Baru
        updated_config["last_ai_tuning"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        updated_config["ai_recommendation"] = reasoning

        with open(CONFIG_PATH, "w") as f:
            json.dump(updated_config, f, indent=4)

        # 5. Catat ke Database History (NeonDB)
        db.execute(text("""
            INSERT INTO ai_audit_logs (timestamp, daily_pnl, win_rate, total_trades, ai_reasoning, new_config)
            VALUES (:ts, :pnl, :wr, :count, :reason, :config)
        """), {
            "ts": datetime.utcnow(),
            "pnl": total_pnl,
            "wr": win_rate,
            "count": total_trades,
            "reason": reasoning,
            "config": json.dumps(updated_config)
        })
        db.commit()

        print(f"[{datetime.now()}] [NEURO-OPTIMIZER SUCCESS] AI Rekomendasi: {reasoning}")

    except Exception as e:
        print(f"[NEURO-OPTIMIZER ERROR] {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_neuro_optimizer()
