from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Index, UniqueConstraint
from datetime import datetime, timezone
from ..core.database import Base


class MemoryEdge(Base):
    __tablename__ = "memory_edges"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_node_id = Column(Integer, ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id = Column(Integer, ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False)
    relation = Column(String, nullable=False)

    weight = Column(Float, default=1.0)
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("user_id", "source_node_id", "target_node_id", "relation", name="uq_memory_edge"),
        Index("ix_memory_edges_source", "source_node_id"),
        Index("ix_memory_edges_target", "target_node_id"),
    )
