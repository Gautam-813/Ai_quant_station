from sqlalchemy import Column, Integer, DateTime, LargeBinary, ForeignKey, Index
from datetime import datetime, timezone
from ..core.database import Base


class ChatEmbedding(Base):
    __tablename__ = "chat_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    chat_memory_id = Column(Integer, ForeignKey("chat_memories.id", ondelete="CASCADE"), nullable=False)
    embedding = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_chat_embeddings_memory", "chat_memory_id"),
    )
