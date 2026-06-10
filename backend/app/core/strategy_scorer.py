import logging
from datetime import datetime, timezone
from sqlalchemy import text as sql_text, select

from ..core.database import AsyncSessionLocal
from ..models.strategy_score import StrategyScore

logger = logging.getLogger(__name__)


def start_strategy_scorer():
    """Register the hourly strategy score update with APScheduler."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(update_strategy_scores, 'interval', hours=1)
        scheduler.start()
        logger.info("Strategy Scorer Scheduler initialized (Hourly).")
    except Exception as e:
        logger.warning(f"Strategy Scorer scheduler not available: {e}")


async def update_strategy_scores():
    """Aggregate trade performance by prompt across autopilot_trades and trade_records."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(sql_text("""
                SELECT prompt_text, symbol, direction, source,
                       COUNT(*) as total_trades,
                       SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as winning_trades,
                       SUM(profit) as total_pnl,
                       AVG(CASE WHEN profit > 0 THEN profit END) as avg_profit,
                       AVG(CASE WHEN profit < 0 THEN profit END) as avg_loss,
                       AVG(confidence) as avg_confidence,
                       MIN(created_at) as first_used,
                       MAX(created_at) as last_used
                FROM (
                    SELECT prompt_text, symbol, direction, 'autopilot' as source,
                           profit, confidence, created_at
                    FROM autopilot_trades
                    WHERE result IS NOT NULL
                    UNION ALL
                    SELECT c.content as prompt_text, t.symbol, t.direction, 'ai_analyst' as source,
                           t.profit_loss as profit, NULL as confidence, t.executed_at as created_at
                    FROM trade_records t
                    JOIN chat_memories c ON cast(c.id as text) = t.ai_message
                    WHERE t.profit_loss IS NOT NULL
                )
                GROUP BY prompt_text, symbol, direction, source
            """))

            rows = result.fetchall()
            updated_count = 0

            for row in rows:
                prompt_text = row.prompt_text
                symbol = row.symbol
                direction = row.direction
                source = row.source
                total = row.total_trades or 0
                wins = row.winning_trades or 0
                pnl = row.total_pnl or 0.0
                avg_profit = row.avg_profit
                avg_loss = row.avg_loss
                avg_conf = row.avg_confidence
                first = row.first_used
                last = row.last_used
                win_rate = (wins / total * 100) if total > 0 else 0.0
                losses = total - wins
                gross_profit = (wins * avg_profit) if avg_profit and wins > 0 else 0
                gross_loss = (losses * avg_loss) if avg_loss and losses > 0 else 0
                if gross_loss < 0:
                    profit_factor = round(abs(gross_profit / gross_loss), 2) if gross_profit > 0 else 0.0
                else:
                    profit_factor = None

                existing = await db.execute(
                    select(StrategyScore).where(
                        StrategyScore.prompt_text == prompt_text,
                        StrategyScore.symbol == symbol,
                        StrategyScore.direction == direction,
                        StrategyScore.source == source,
                    )
                )
                score = existing.scalar_one_or_none()

                if score:
                    score.total_trades = total
                    score.winning_trades = wins
                    score.total_pnl = pnl
                    score.win_rate = win_rate
                    score.avg_confidence = avg_conf
                    score.avg_profit = avg_profit
                    score.avg_loss = avg_loss
                    score.profit_factor = profit_factor
                    score.first_used = first
                    score.last_used = last
                    score.updated_at = datetime.now(timezone.utc)
                else:
                    score = StrategyScore(
                        prompt_text=prompt_text,
                        symbol=symbol,
                        direction=direction,
                        source=source,
                        total_trades=total,
                        winning_trades=wins,
                        total_pnl=pnl,
                        win_rate=win_rate,
                        avg_confidence=avg_conf,
                        avg_profit=avg_profit,
                        avg_loss=avg_loss,
                        profit_factor=profit_factor,
                        first_used=first,
                        last_used=last,
                    )
                    db.add(score)

                updated_count += 1

            await db.commit()
            if updated_count:
                logger.info(f"Updated {updated_count} strategy scores")

        except Exception as e:
            logger.warning(f"Strategy score update failed: {e}")
