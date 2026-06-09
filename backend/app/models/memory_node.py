from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Index, UniqueConstraint
from datetime import datetime, timezone
from ..core.database import Base


class MemoryNode(Base):
    __tablename__ = "memory_nodes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String, nullable=False)
    type = Column(String, nullable=False)

    weight = Column(Float, default=1.0)
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("user_id", "label", "type", name="uq_memory_node"),
        Index("ix_memory_nodes_user_type", "user_id", "type"),
    )
