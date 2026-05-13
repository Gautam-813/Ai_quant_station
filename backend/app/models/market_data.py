from sqlalchemy import Column, Integer, String, DateTime, Float, Index
from ..core.database import Base

class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    timeframe = Column(String, nullable=False, index=True)  # 1m, 5m, 1h, etc.
    time = Column(DateTime, nullable=False, index=True)
    
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    tick_volume = Column(Integer, nullable=True)
    
    # To handle multiple brokers/sources if ever needed
    source = Column(String, default="mt5", index=True)

    # Unique constraint to prevent duplicates for the same symbol, timeframe, and time
    __table_args__ = (
        Index("ix_market_data_symbol_tf_time", "symbol", "timeframe", "time", unique=True),
    )
