# RAG & Self-Improving System Architecture

## Current Data Model

```
chat_memories                    trade_records
────────────────────             ────────────────────
id (PK)                          id (PK)
user_id                          user_id
symbol                           symbol
role (user/assistant)            direction (BUY/SELL)
content (full AI text)           entry_price / sl / tp
detected_setup (JSON)            volume
detected_action (JSON)           profit_loss
created_at                       mt5_ticket
                                 ai_message → chat_memories.id (FK)
                                 executed_at / closed_at

autopilot_trades                 user_feedback
────────────────────             ────────────────────
id (PK)                          id (PK)
user_id                          user_id
prompt_number                    chat_memory_id → chat_memories.id
prompt_text                      is_helpful (bool)
symbol                           notes
direction                        created_at
entry_price / sl / tp
profit / result (TP_HIT/SL_HIT)
confidence
```

## Phase 1: Strategy Scoreboard (Foundation)

### New Table

```sql
CREATE TABLE strategy_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_text     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    direction       TEXT,                  -- BUY, SELL, or NULL for both
    source          TEXT NOT NULL,          -- 'autopilot' or 'ai_analyst'

    -- Aggregated metrics
    total_trades    INTEGER DEFAULT 0,
    winning_trades  INTEGER DEFAULT 0,
    total_pnl       REAL DEFAULT 0.0,
    win_rate        REAL DEFAULT 0.0,
    avg_confidence  REAL DEFAULT NULL,     -- AI confidence score
    avg_profit      REAL DEFAULT NULL,
    avg_loss        REAL DEFAULT NULL,
    max_drawdown    REAL DEFAULT NULL,
    profit_factor   REAL DEFAULT NULL,

    -- Timing
    first_used      TIMESTAMP,
    last_used       TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(prompt_text, symbol, direction, source)
);
```

### Python Model

```python
class StrategyScore(Base):
    __tablename__ = "strategy_scores"

    id = Column(Integer, primary_key=True, index=True)
    prompt_text = Column(Text, nullable=False)
    symbol = Column(String, nullable=False)
    direction = Column(String, nullable=True)
    source = Column(String, nullable=False)

    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)
    avg_confidence = Column(Float, nullable=True)
    avg_profit = Column(Float, nullable=True)
    avg_loss = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)

    first_used = Column(DateTime, nullable=True)
    last_used = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("prompt_text", "symbol", "direction", "source",
                         name="uq_strategy_score"),
    )
```

### Update Cron Job (apscheduler)

Runs every hour. Queries all closed trades and recalculates scores.

```
SELECT
    prompt_text,
    symbol,
    direction,
    source,
    COUNT(*) as total_trades,
    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as winning_trades,
    SUM(profit) as total_pnl,
    AVG(confidence) as avg_confidence,
    ...
FROM (
    SELECT prompt_text, symbol, direction, 'autopilot' as source,
           profit, confidence
    FROM autopilot_trades WHERE result IS NOT NULL
    UNION ALL
    SELECT c.content as prompt_text, t.symbol, t.direction, 'ai_analyst' as source,
           t.profit_loss as profit, NULL as confidence
    FROM trade_records t
    JOIN chat_memories c ON c.id = t.ai_message
    WHERE t.profit_loss IS NOT NULL
)
GROUP BY prompt_text, symbol, direction, source;
```

## Phase 2: Vector Embeddings

### Infrastructure

Use `sentence-transformers` for local embedding generation (no external API needed, runs offline).

```python
# embed_service.py
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")  # 384-dim, fast, ~80MB

def embed_text(text: str) -> list[float]:
    return model.encode(text).tolist()

def embed_query(query: str) -> list[float]:
    return model.encode(query).tolist()
```

### New Table

```sql
CREATE TABLE chat_embeddings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_memory_id  INTEGER NOT NULL REFERENCES chat_memories(id) ON DELETE CASCADE,
    embedding       BLOB NOT NULL,           -- numpy float32 array
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chat_embeddings_memory ON chat_embeddings(chat_memory_id);
```

For SQLite, store embeddings as BLOBs (binary numpy arrays). For PostgreSQL, use the `pgvector` extension with proper vector columns.

### Embedding Trigger

On every AI chat response, asynchronously generate and store the embedding.

```python
async def generate_embedding(chat_memory_id: int, text: str):
    loop = asyncio.get_running_loop()
    vector = await loop.run_in_executor(None, embed_text, text)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("INSERT OR REPLACE INTO chat_embeddings (chat_memory_id, embedding) VALUES (:id, :emb)"),
            {"id": chat_memory_id, "emb": np.array(vector, dtype=np.float32).tobytes()}
        )
        await db.commit()
```

### Similarity Search

```python
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

async def find_similar_analyses(query_embedding: np.ndarray, symbol: str, limit: int = 5):
    """Find past analyses similar to the current query, weighted by profitability."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT c.id, c.content, c.detected_setup,
                       t.profit_loss, uf.is_helpful,
                       ce.embedding
                FROM chat_embeddings ce
                JOIN chat_memories c ON c.id = ce.chat_memory_id
                LEFT JOIN trade_records t ON t.ai_message = c.id
                LEFT JOIN user_feedback uf ON uf.chat_memory_id = c.id
                WHERE c.symbol = :symbol
                  AND ce.embedding IS NOT NULL
                ORDER BY c.created_at DESC
                LIMIT 100
            """),
            {"symbol": symbol}
        )
        rows = result.fetchall()

    scored = []
    for row in rows:
        emb = np.frombuffer(row.embedding, dtype=np.float32)
        sim = cosine_similarity(query_embedding, emb)
        profit = row.profit_loss or 0
        helpful = 1 if row.is_helpful else 0
        # Score = similarity + profit bonus + feedback bonus
        score = sim * 0.5 + (min(profit / 100, 1)) * 0.3 + helpful * 0.2
        scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]
```

## Phase 3: RAG-Enhanced AI Queries

### Modified Chat Flow

```
User asks question about XAUUSD
     ↓
1. Generate embedding of user's question
     ↓
2. Vector search: find top-5 similar past analyses with best profit + feedback
     ↓
3. Build RAG context:
   """
   RELEVANT PAST ANALYSES on XAUUSD:

   [Analysis from May 10] — PROFIT: +$150 | Confidence: 75%
     → "Bullish flag pattern on H1, RSI oversold..."
     → TRADE: BUY at 2345, TP at 2360 ✅ HIT

   [Analysis from May 5] — PROFIT: -$80 | Confidence: 60%
     → "Resistance at 2350, expecting reversal..."
     → TRADE: SELL at 2350, SL at 2360 ❌ SL HIT

   [Analysis from Apr 28] — FEEDBACK: Helpful
     → "Strong support at 2330, watch for bounce..."
     → No trade executed

   BEST PERFORMING STRATEGIES on XAUUSD:
   - "Buy RSI < 30 + 200 EMA" : 75% win rate (12 trades, +$890)
   - "Sell on resistance break" : 60% win rate (8 trades, +$340)
   """
     ↓
4. Send to AI with system prompt:
   "You are a quant analyst. You have access to past performance data.
    Consider what worked before. Be honest about your track record."
     ↓
5. AI generates response aware of its own history
```

### System Prompt Enhancement

```python
async def build_rag_context(symbol: str, user_question: str) -> str:
    """Build RAG context block for AI system prompt."""

    # 1. Find similar past analyses
    query_emb = await generate_embedding_async(user_question)
    similar = await find_similar_analyses(query_emb, symbol)

    # 2. Get top strategies for this symbol
    scores = await get_strategy_scores(symbol)

    context_parts = ["RELEVANT PAST ANALYSES:\n"]

    for score, row in similar[:5]:
        profit_tag = ""
        if row.profit_loss:
            profit_tag = f"PROFIT: ${row.profit_loss:+.2f}"
        elif row.is_helpful is not None:
            profit_tag = "FEEDBACK: Helpful" if row.is_helpful else "FEEDBACK: Not Helpful"

        context_parts.append(
            f"[Analysis #{row.id}] {profit_tag}\n"
            f"  {row.content[:200]}..."
        )

    if scores:
        context_parts.append("\nBEST STRATEGIES THIS SYMBOL:\n")
        for s in scores[:3]:
            context_parts.append(
                f"  \"{s.prompt_text[:60]}...\" : {s.win_rate:.0f}% win rate "
                f"({s.total_trades} trades, ${s.total_pnl:+.2f})"
            )

    return "\n".join(context_parts)
```

## Phase 4: Autopilot Self-Improvement

### Smart Prompt Selection

Replace random prompt selection with score-weighted selection.

```python
async def pick_best_prompt(prompt_pool: list, symbol: str) -> dict:
    """Pick prompt weighted by historical performance."""
    scores = await get_strategy_scores(symbol)

    weighted = []
    for p in prompt_pool:
        score_data = next(
            (s for s in scores if s.prompt_text == p["text"] and s.direction is None),
            None
        )
        if score_data and score_data.total_trades >= 5:
            # Weight by win rate, prefer 60%+ strategies
            weight = max(score_data.win_rate - 30, 5)  # 5% to 70%
        else:
            weight = 10  # Default weight for new prompts

        weighted.extend([p] * int(weight))

    return random.choice(weighted)
```

### Automatic Model Routing

Track which AI provider/model performs best per symbol.

```python
async def get_best_model_for_symbol(symbol: str) -> tuple[str, str]:
    """Return (provider, model) with highest trade success rate for this symbol."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT m.provider, m.model,
                       COUNT(t.id) as trades,
                       AVG(CASE WHEN t.profit_loss > 0 THEN 1.0 ELSE 0.0 END) as win_rate
                FROM model_usage m
                JOIN chat_memories c ON c.user_id = m.user_id
                JOIN trade_records t ON t.ai_message = c.id
                WHERE c.symbol = :symbol AND t.profit_loss IS NOT NULL
                GROUP BY m.provider, m.model
                HAVING trades >= 3
                ORDER BY win_rate DESC
                LIMIT 1
            """),
            {"symbol": symbol}
        )
        row = result.fetchone()
        if row:
            return (row.provider, row.model)
    return ("nvidia", "qwen/qwen3.5-122b-a10b")  # fallback
```

## Phase 5: Feedback Dashboard

### New API Endpoint

```
GET /api/analytics/strategy-scores?symbol=XAUUSD&sort=win_rate

Response:
{
  "strategies": [
    {
      "prompt": "Buy RSI < 30 + 200 EMA",
      "symbol": "XAUUSD",
      "win_rate": 75.0,
      "trades": 12,
      "total_pnl": 890.50,
      "last_used": "2026-05-18T10:30:00Z"
    },
    ...
  ]
}
```

### Frontend Page Enhancements

Add a "Strategy Analytics" tab to the Settings or History page showing:
- Win rate by strategy prompt
- P&L by symbol
- Model performance comparison
- Best/worst performing prompts
- AI accuracy over time (rolling 30-day window)

## File Structure

```
backend/app/
├── core/
│   ├── embed_service.py         # NEW — sentence-transformers wrapper
│   ├── rag_service.py           # NEW — RAG context builder
│   └── strategy_scorer.py       # NEW — Scoreboard updater
├── models/
│   ├── ai_memory.py             # + StrategyScore model
│   └── chat_embeddings.py       # NEW — Embedding model
└── api/
    ├── ai.py                    # + RAG context injection
    ├── autopilot.py             # + Smart prompt selection
    └── analytics.py             # + Strategy scores endpoint
```

## Dependency Additions

```txt
# requirements.txt additions
sentence-transformers>=3.0.0
numpy>=1.26.0                   # already installed
```

For PostgreSQL with pgvector:
```sql
CREATE EXTENSION vector;
CREATE TABLE chat_embeddings (
    id SERIAL PRIMARY KEY,
    chat_memory_id INT REFERENCES chat_memories(id) ON DELETE CASCADE,
    embedding VECTOR(384),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_chat_embeddings_vector ON chat_embeddings USING ivfflat (embedding vector_cosine_ops);
```

## Timeline

| Phase | What | When |
|---|---|---|
| 1 | Strategy Scoreboard table + cron updater | Day 1 |
| 2 | Vector embeddings on new chats | Day 2-3 |
| 3 | RAG context in AI prompts | Day 3-4 |
| 4 | Autopilot smart selection + model routing | Day 4-5 |
| 5 | Feedback dashboard UI | Day 5-7 |

## Success Metrics

| Metric | Target | How to measure |
|---|---|---|
| AI trade suggestion win rate | >55% | Compare detected_setup direction vs trade_records.profit_loss |
| Autopilot P&L improvement | +20% vs random | Compare before/after RAG smart selection |
| User feedback positive rate | >70% | user_feedback.is_helpful ratio |
| Strategy diversity | <30% on top strategy | StrategyScore distribution |
