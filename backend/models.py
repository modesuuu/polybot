from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()

class TradeSignal(Base):
    __tablename__ = 'trade_signals'

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    symbol = Column(String, index=True)
    direction = Column(String) # 'UP' or 'DOWN'
    entry_price = Column(Float) # BTC Price at entry
    exit_price = Column(Float, nullable=True) # BTC Price at exit
    quantity = Column(Float) # Size in USD, typically 5.0
    entry_price_share = Column(Float, nullable=True) # Polymarket token price (e.g. 0.23)
    shares_bought = Column(Float, nullable=True) # quantity / entry_price_share
    token_id = Column(String, nullable=True) # Polymarket clobTokenId for live price tracking
    current_token_price = Column(Float, nullable=True) # Live mark-to-market token price
    unrealized_pnl = Column(Float, nullable=True) # (shares_bought * current_token_price) - quantity
    status = Column(String) # 'OPEN', 'WIN', 'LOSS'
    pnl = Column(Float, nullable=True)
    spread = Column(Float, nullable=True) # Polymarket orderbook spread (best_ask - best_bid)

class AIAuditLog(Base):
    __tablename__ = 'ai_audit_logs'

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    daily_pnl = Column(Float)
    win_rate = Column(Float)
    total_trades = Column(Integer)
    ai_reasoning = Column(String)
    new_config = Column(String)


