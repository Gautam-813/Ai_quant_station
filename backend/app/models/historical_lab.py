from sqlalchemy import Column, Integer, String, DateTime, Float, Text, ForeignKey, JSON, Boolean
from datetime import datetime, timezone
from ..core.database import Base


class HistoricalBacktest(Base):
    __tablename__ = "historical_backtests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    status = Column(String, default="pending")
    error_message = Column(Text, nullable=True)
    
    symbol = Column(String, nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    timeframe = Column(String, default="1m")
    timeframes = Column(JSON, nullable=True)  # List of Pandas offset strings for multi-TF
    mode = Column(String, nullable=False)
    prompt = Column(Text, nullable=True)
    provider = Column(String, default="nvidia")
    model = Column(String, default="qwen/qwen3.5-122b-a10b")
    
    initial_capital = Column(Float, nullable=True)
    lot_size = Column(Float, default=0.01)
    include_spread = Column(Boolean, default=False)
    include_commission = Column(Boolean, default=False)
    
    metrics = Column(JSON, nullable=True)
    equity_curve = Column(JSON, nullable=True)
    analysis_data = Column(JSON, nullable=True)
    generated_code = Column(Text, nullable=True)
    trade_log = Column(JSON, nullable=True)
    
    chat_history = Column(JSON, default=list)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
