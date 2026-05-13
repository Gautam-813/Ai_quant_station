from sqlalchemy import Column, Integer, String, DateTime, Float, Text, ForeignKey, JSON, Boolean, BigInteger
from datetime import datetime
from ..core.database import Base


class ChatMemory(Base):
    __tablename__ = "chat_memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=True)
    role = Column(String, nullable=False)  # user or assistant
    content = Column(Text, nullable=False)
    detected_setup = Column(JSON, nullable=True)
    detected_action = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class GlobalInsights(Base):
    __tablename__ = "global_insights"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    
    # Anonymized aggregated data
    total_analyzed = Column(Integer, default=0)
    buy_signals = Column(Integer, default=0)
    sell_signals = Column(Integer, default=0)
    
    # Pattern data (anonymized)
    avg_entry_price = Column(Float, nullable=True)
    avg_stop_loss = Column(Float, nullable=True)
    avg_take_profit = Column(Float, nullable=True)
    
    # Usage stats
    total_conversations = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ModelUsage(Base):
    __tablename__ = "model_usage"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Usage counts
    total_requests = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    total_cost = Column(Float, default=0.0)
    
    last_used = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TradeRecord(Base):
    __tablename__ = "trade_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=False)
    direction = Column(String, nullable=False)  # BUY or SELL
    entry_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    volume = Column(Float, nullable=False)
    order_type = Column(String, default="market")  # market or pending
    status = Column(String, default="open")  # open, closed, cancelled
    
    # Execution info
    executed_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)
    profit_loss = Column(Float, nullable=True)
    
    # MT5 specific fields
    magic_number = Column(Integer, nullable=True, index=True)  # To identify strategy/source
    mt5_ticket = Column(BigInteger, nullable=True, unique=True, index=True)  # MT5 ticket number
    comment = Column(String, nullable=True)
    
    # AI context (for learning)
    ai_message = Column(Text, nullable=True)


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    chat_memory_id = Column(Integer, ForeignKey("chat_memories.id"), nullable=True)
    is_helpful = Column(Boolean, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CalculationHistory(Base):
    __tablename__ = "calculation_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=False)
    indicator = Column(String, nullable=False)  # ATR, SMA, EMA, RSI
    period = Column(Integer, nullable=False)
    value = Column(Float, nullable=False)
    candle_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class IndicatorRequest(Base):
    __tablename__ = "indicator_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=False)
    indicator = Column(String, nullable=False)
    period = Column(Integer, nullable=True)
    request_count = Column(Integer, default=1)
    last_requested = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Favorites
    favorite_symbols = Column(String, nullable=True)  # JSON list: ["XAUUSD", "EURUSD"]
    default_provider = Column(String, default="nvidia")
    default_model = Column(String, default="qwen/qwen3.5-122b-a10b")
    default_data_source = Column(String, default="yahoo")  # yahoo, mt5, none
    default_period = Column(String, default="1mo")
    
    # UI preferences
    theme = Column(String, default="dark")

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AutopilotTrade(Base):
    __tablename__ = "autopilot_trades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Prompt info
    prompt_number = Column(Integer, nullable=False)
    prompt_text = Column(String, nullable=False)

    # Trade setup
    symbol = Column(String, nullable=False)
    direction = Column(String, nullable=False)  # BUY or SELL
    entry_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    lot_size = Column(Float, nullable=False)
    order_type = Column(String, default="market")  # market, limit, stop

    # Execution info
    mt5_ticket = Column(BigInteger, nullable=True)
    executed_at = Column(DateTime, default=datetime.utcnow)
    execution_price = Column(Float, nullable=True)
    execution_status = Column(String, default="pending")  # pending, executed, failed

    # Result tracking
    result = Column(String, nullable=True)  # TP_HIT, SL_HIT, MANUAL_CLOSE, PENDING, ERROR
    profit = Column(Float, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)

    # AI response details
    reasoning = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    ai_response = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class AutopilotSettings(Base):
    __tablename__ = "autopilot_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)

    # Enable/Disable
    enabled = Column(Boolean, default=False)

    # Settings
    interval_seconds = Column(Integer, default=300)  # 5 minutes
    default_lot = Column(Float, default=0.10)
    max_trades_per_day = Column(Integer, default=10)
    cooldown_minutes = Column(Integer, default=5)

    # Account protection
    max_daily_loss = Column(Float, default=-50.0)  # -50 means stop if -50$ reached

    # MT5 Connection - allow user to specify which MT5 terminal
    mt5_terminal_path = Column(String, nullable=True)  # e.g., "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
    mt5_connector_url = Column(String, nullable=True)  # e.g., "http://192.168.1.100:5001"
    mt5_connected = Column(Boolean, default=False)

    # Symbol to trade
    symbol = Column(String, default="XAUUSD")

    # Provider settings
    provider = Column(String, default="nvidia")
    model = Column(String, default="qwen/qwen3.5-122b-a10b")

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)