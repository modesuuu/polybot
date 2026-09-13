from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import Base
import os
import sqlite3

DATABASE_URL = "sqlite:///./trading.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    # Buat ulang database untuk simulasi bersih (opsional: drop_all jika ingin reset setiap start)
    # Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _migrate_db()

def _migrate_db():
    """Migrasi ringan SQLite: tambahkan kolom baru jika belum ada."""
    try:
        db_path = "./trading.db"
        if not os.path.exists(db_path):
            return
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(trade_signals)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        if 'spread' not in existing_columns:
            try:
                cursor.execute("ALTER TABLE trade_signals ADD COLUMN spread FLOAT")
                conn.commit()
            except Exception:
                pass

        conn.close()
    except Exception as e:
        print(f"[DB MIGRATE ERROR]: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
