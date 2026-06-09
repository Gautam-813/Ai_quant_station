import re
import logging
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from sqlalchemy import select

from ..core.database import AsyncSessionLocal
from ..models.memory_node import MemoryNode
from ..models.memory_edge import MemoryEdge
from ..models.ai_memory import UserPreferences

logger = logging.getLogger(__name__)

# ── Entity extraction patterns ──────────────────────────────────────────

_SYMBOL_PATTERN = re.compile(
    r'\b(XAUUSD|XAGUSD|BTCUSD|ETHUSD|EURUSD|GBPUSD|USDJPY|AUDUSD|'
    r'NZDUSD|USDCAD|USDCHF|US30|SPX500|NAS100|DAX|FTSE|CAC|NI225|'
    r'HK50|AUS200|UK100|COCOA|COFFEE|SUGAR|CORN|WHEAT|Soybean|'
    r'NGAS|OIL|BCOUSD)\b',
    re.I
)

_TIMEFRAME_PATTERN = re.compile(
    r'\b(1m|5m|15m|30m|1h|4h|1d|1w|M1|M5|M15|M30|H1|H4|D1|W1)\b',
    re.I
)

_INDICATOR_PATTERN = re.compile(
    r'\b(RSI|MACD|EMA|SMA|ATR|Bollinger|Stochastic|OBV|Ichimoku|'
    r'Fibonacci|Pivot|Support|Resistance|VWAP|ADX|CCI|Williams)\b',
    re.I
)

_SENTIMENT_PATTERN = re.compile(
    r'\b(bullish|bearish|neutral|overbought|oversold|'
    r'buy|sell|long|short|breakout|breakdown|reversal|pullback)\b',
    re.I
)

_PATTERN_PATTERN = re.compile(
    r'\b(double\s*top|double\s*bottom|head\s*(and|&)\s*shoulders|'
    r'flag|pennant|wedge|triangle|channel|engulfing|doji|hammer|'
    r'shooting\s*star|morning\s*star|evening\s*star)\b',
    re.I
)

_STRATEGY_PATTERN = re.compile(
    r'\b(trend\s*following|mean\s*reversion|breakout|scalping|'
    r'swing\s*trading|momentum|grid|martingale|hedging|'
    r'price\s*action|supply\s*(and|&)\s*demand)\b',
    re.I
)

_TF_NORMALIZE = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d", "W1": "1w",
}


def _normalize_label(label: str, etype: str) -> str:
    if etype == "TIMEFRAME":
        return _TF_NORMALIZE.get(label.upper(), label.lower())
    return label.upper() if etype in ("SYMBOL",) else label.lower()


def extract_entities(text: str) -> List[Tuple[str, str]]:
    entities = []
    for match in _SYMBOL_PATTERN.finditer(text):
        entities.append((match.group(1).upper(), "SYMBOL"))
    for match in _TIMEFRAME_PATTERN.finditer(text):
        entities.append((match.group(1), "TIMEFRAME"))
    for match in _INDICATOR_PATTERN.finditer(text):
        entities.append((match.group(1).upper(), "INDICATOR"))
    for match in _SENTIMENT_PATTERN.finditer(text):
        entities.append((match.group(1).lower(), "SENTIMENT"))
    for match in _PATTERN_PATTERN.finditer(text):
        entities.append((match.group(1).lower(), "PATTERN"))
    for match in _STRATEGY_PATTERN.finditer(text):
        entities.append((match.group(1).lower(), "STRATEGY"))
    return entities


async def _upsert_node(user_id: int, label: str, etype: str) -> Optional[int]:
    norm_label = _normalize_label(label, etype)
    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(MemoryNode).where(
                MemoryNode.user_id == user_id,
                MemoryNode.label == norm_label,
                MemoryNode.type == etype,
            )
        )
        node = existing.scalar_one_or_none()
        if node:
            node.weight = node.weight + 1
            node.last_seen = datetime.now(timezone.utc)
            await db.commit()
            return node.id
        else:
            node = MemoryNode(
                user_id=user_id,
                label=norm_label,
                type=etype,
                weight=1.0,
            )
            db.add(node)
            await db.commit()
            await db.refresh(node)
            return node.id


async def _upsert_edge(
    user_id: int, source_id: int, target_id: int, relation: str
):
    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(MemoryEdge).where(
                MemoryEdge.user_id == user_id,
                MemoryEdge.source_node_id == source_id,
                MemoryEdge.target_node_id == target_id,
                MemoryEdge.relation == relation,
            )
        )
        edge = existing.scalar_one_or_none()
        if edge:
            edge.weight = edge.weight + 1
            edge.last_seen = datetime.now(timezone.utc)
        else:
            edge = MemoryEdge(
                user_id=user_id,
                source_node_id=source_id,
                target_node_id=target_id,
                relation=relation,
                weight=1.0,
            )
            db.add(edge)
        await db.commit()


async def update_memory_from_chat(
    user_id: int,
    user_message: str,
    ai_message: str,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
):
    combined = f"{user_message} {ai_message}"
    entities = extract_entities(combined)

    if not entities:
        return

    node_ids = {}
    for label, etype in entities:
        nid = await _upsert_node(user_id, label, etype)
        if nid:
            key = f"{etype}:{_normalize_label(label, etype)}"
            node_ids[key] = nid

    keys = list(node_ids.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            await _upsert_edge(
                user_id,
                node_ids[keys[i]],
                node_ids[keys[j]],
                "CO_OCCURS",
            )

    if symbol and timeframe:
        sym_norm = symbol.upper()
        sym_id = await _upsert_node(user_id, sym_norm, "SYMBOL")
        tf_id = await _upsert_node(user_id, timeframe, "TIMEFRAME")
        if sym_id and tf_id:
            await _upsert_edge(user_id, sym_id, tf_id, "TRADED_ON_TIMEFRAME")

    for entity_type in ("SYMBOL", "SENTIMENT"):
        for key, nid in node_ids.items():
            if key.startswith(f"{entity_type}:"):
                for other_key, other_nid in node_ids.items():
                    if other_key != key and not other_key.startswith(f"{entity_type}:"):
                        await _upsert_edge(user_id, nid, other_nid, "RELATES_TO")


async def _update_user_preferences_from_usage(
    user_id: int,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
):
    async with AsyncSessionLocal() as db:
        prefs = await db.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        pref = prefs.scalar_one_or_none()

        if not pref:
            return

        current_symbols = pref.favorite_symbols or []
        if symbol and symbol not in current_symbols:
            current_symbols = current_symbols[-49:] + [symbol]
            pref.favorite_symbols = current_symbols

        pref.updated_at = datetime.now(timezone.utc)
        await db.commit()


async def get_long_term_context(
    user_id: int, symbol: Optional[str] = None, limit: int = 5
) -> str:
    parts = []

    async with AsyncSessionLocal() as db:
        top_symbols = await db.execute(
            select(MemoryNode)
            .where(
                MemoryNode.user_id == user_id,
                MemoryNode.type == "SYMBOL",
            )
            .order_by(MemoryNode.weight.desc())
            .limit(limit)
        )
        symbols = top_symbols.scalars().all()
        if symbols:
            parts.append(
                "YOUR TRADED SYMBOLS: "
                + ", ".join(f"{s.label} ({int(s.weight)}x)" for s in symbols)
            )

        if symbol:
            sym_node = await db.execute(
                select(MemoryNode).where(
                    MemoryNode.user_id == user_id,
                    MemoryNode.label == symbol.upper(),
                    MemoryNode.type == "SYMBOL",
                )
            )
            sym = sym_node.scalar_one_or_none()
            if sym:
                edges = await db.execute(
                    select(MemoryEdge, MemoryNode)
                    .join(MemoryNode, MemoryEdge.target_node_id == MemoryNode.id)
                    .where(
                        MemoryEdge.user_id == user_id,
                        MemoryEdge.source_node_id == sym.id,
                    )
                    .order_by(MemoryEdge.weight.desc())
                    .limit(limit)
                )
                related = edges.all()
                if related:
                    context_items = []
                    for edge, node in related:
                        context_items.append(
                            f"{node.label} ({node.type.lower()}, {int(edge.weight)}x)"
                        )
                    parts.append(
                        f"YOUR KNOWLEDGE ON {symbol.upper()}: "
                        + ", ".join(context_items)
                    )

    if parts:
        return "[YOUR MEMORY]\n" + "\n".join(parts)
    return ""


async def update_user_preferences_async(user_id: int, **kwargs):
    await _update_user_preferences_from_usage(user_id, **kwargs)
