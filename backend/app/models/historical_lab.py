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
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    timeframe = Column(String, default="1m")
    mode = Column(String, nullable=False)
    prompt = Column(Text, nullable=True)
    
    initial_capital = Column(Float, nullable=True)
    leverage = Column(Float, nullable=True)
    include_spread = Column(Boolean, default=False)
    include_commission = Column(Boolean, default=False)
    
    metrics = Column(JSON, nullable=True)
    equity_curve = Column(JSON, nullable=True)
    analysis_data = Column(JSON, nullable=True)
    generated_code = Column(Text, nullable=True)
    
    chat_history = Column(JSON, default=list)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
