from sqlalchemy import Column, Integer, String, DateTime, Float, Text, ForeignKey, JSON, Boolean
from datetime import datetime
from ..core.database import Base


class HistoricalBacktest(Base):
    __tablename__ = "historical_backtests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Status Tracking
    status = Column(String, default="pending")  # pending, running, completed, failed
    error_message = Column(Text, nullable=True)
    
    # Configuration
    symbol = Column(String, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    timeframe = Column(String, default="1T")
    mode = Column(String, nullable=False)  # "backtest" or "analysis"
    prompt = Column(Text, nullable=True)
    
    # Backtest Specifics
    initial_capital = Column(Float, nullable=True)
    leverage = Column(Float, nullable=True)
    include_spread = Column(Boolean, default=False)
    include_commission = Column(Boolean, default=False)
    
    # Results (Stored as JSON)
    metrics = Column(JSON, nullable=True)      # Sharpe, Win Rate, etc.
    equity_curve = Column(JSON, nullable=True)  # Chart data
    analysis_data = Column(JSON, nullable=True) # Volatility, heatmap data
    
    # Conversational Memory
    chat_history = Column(JSON, default=list)   # List of messages: [{"role": "user", "content": "..."}, ...]
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
