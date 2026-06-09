"""
User Feedback and Analytics Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, case

from ..core.database import get_db, AsyncSessionLocal
from ..core.security import get_current_user
from ..models.strategy_score import StrategyScore

router = APIRouter(prefix="/analytics", tags=["User Analytics"])


class FeedbackRequest(BaseModel):
    chat_memory_id: Optional[int] = None
    is_helpful: bool
    notes: Optional[str] = None


class CalculationRecord(BaseModel):
    symbol: str
    indicator: str
    period: int
    value: float
    candle_count: int


# ── Reports Pydantic models ────────────────────────────────────────────────

class TodaySummary(BaseModel):
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    pnl: float = 0.0
    best_prompt: str = ""


class DailySummary(BaseModel):
    date: str
    trades: int
    wins: int
    losses: int
    win_rate: float
    pnl: float


class ReportsResponse(BaseModel):
    today: TodaySummary
    daily_history: List[DailySummary]
    prompts: List[dict]
    trades: List[dict]


@router.get("/reports")
async def get_reports(current_user: dict = Depends(get_current_user)):
    """Consolidated reports endpoint: today's summary, daily history, prompt stats, recent trades."""
    user_id = current_user["id"]
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = today_start - timedelta(days=30)

    async with AsyncSessionLocal() as db:
        from app.models.ai_memory import AutopilotTrade

        # ── Today's trades ──
        today_result = await db.execute(
            select(AutopilotTrade).where(
                AutopilotTrade.user_id == user_id,
                AutopilotTrade.executed_at >= today_start,
            ).order_by(AutopilotTrade.executed_at.desc())
        )
        today_trades = today_result.scalars().all()

        wins = sum(1 for t in today_trades if (t.profit or 0) > 0)
        losses = sum(1 for t in today_trades if (t.profit or 0) <= 0)
        pnl = sum(t.profit or 0 for t in today_trades)

        best_prompt = ""
        if today_trades:
            prompt_pnl: dict[int, float] = {}
            for t in today_trades:
                prompt_pnl[t.prompt_number] = prompt_pnl.get(t.prompt_number, 0) + (t.profit or 0)
            best_pn = max(prompt_pnl, key=prompt_pnl.get)
            best_prompt = f"#{best_pn}" if best_pn > 0 else f"Custom-{abs(best_pn)}"

        today_summary = TodaySummary(
            trades=len(today_trades),
            wins=wins,
            losses=losses,
            win_rate=round(wins / len(today_trades) * 100, 1) if today_trades else 0.0,
            pnl=round(pnl, 2),
            best_prompt=best_prompt,
        )

        # ── Daily history (last 30 days) ──
        daily_rows = await db.execute(
            select(
                func.date(AutopilotTrade.executed_at).label("date"),
                func.count(AutopilotTrade.id).label("trades"),
                func.sum(case((AutopilotTrade.profit > 0, 1), else_=0)).label("wins"),
                func.sum(AutopilotTrade.profit).label("pnl"),
            ).where(
                AutopilotTrade.user_id == user_id,
                AutopilotTrade.executed_at >= thirty_days_ago,
            ).group_by(text("date"))
            .order_by(text("date DESC"))
        )
        daily_map = {}
        for r in daily_rows:
            daily_map[str(r[0])] = {
                "trades": r[1],
                "wins": r[2] or 0,
                "pnl": float(r[3] or 0),
            }

        daily_history = []
        for i in range(29, -1, -1):
            day = (today_start - timedelta(days=i)).strftime("%Y-%m-%d")
            if day in daily_map:
                d = daily_map[day]
                w = d["wins"]
                l = d["trades"] - w
                daily_history.append(DailySummary(
                    date=day,
                    trades=d["trades"],
                    wins=w,
                    losses=l,
                    win_rate=round(w / d["trades"] * 100, 1) if d["trades"] > 0 else 0.0,
                    pnl=d["pnl"],
                ))
            else:
                daily_history.append(DailySummary(date=day, trades=0, wins=0, losses=0, win_rate=0.0, pnl=0.0))

        # ── Prompt stats ──
        prompt_result = await db.execute(
            select(AutopilotTrade).where(
                AutopilotTrade.user_id == user_id,
                AutopilotTrade.profit.isnot(None),
            )
        )
        all_closed = prompt_result.scalars().all()

        groups: dict[int, dict] = {}
        for t in all_closed:
            pn = t.prompt_number
            if pn not in groups:
                groups[pn] = {"prompt_number": pn, "prompt_text": t.prompt_text, "total_trades": 0, "wins": 0, "losses": 0, "total_profit": 0.0}
            groups[pn]["total_trades"] += 1
            groups[pn]["total_profit"] += t.profit or 0
            if (t.profit or 0) > 0:
                groups[pn]["wins"] += 1
            else:
                groups[pn]["losses"] += 1

        prompt_stats = []
        for g in groups.values():
            g["win_rate"] = round(g["wins"] / g["total_trades"] * 100, 1) if g["total_trades"] > 0 else 0.0
            g["avg_profit"] = round(g["total_profit"] / g["total_trades"], 2) if g["total_trades"] > 0 else 0.0
            g["total_profit"] = round(g["total_profit"], 2)
            pn = g["prompt_number"]
            g["display_name"] = f"Custom-{abs(pn)}" if pn < 0 else f"#{pn}"
            prompt_stats.append(g)

        prompt_stats.sort(key=lambda x: x["total_profit"], reverse=True)

        # ── Recent trades (last 50) ──
        trades_result = await db.execute(
            select(AutopilotTrade)
            .where(AutopilotTrade.user_id == user_id)
            .order_by(AutopilotTrade.executed_at.desc())
            .limit(50)
        )
        recent_trades = trades_result.scalars().all()

        trades_list = [
            {
                "id": t.id,
                "prompt_number": t.prompt_number,
                "prompt_text": t.prompt_text,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "stop_loss": t.stop_loss,
                "take_profit": t.take_profit,
                "lot_size": t.lot_size,
                "mt5_ticket": t.mt5_ticket,
                "executed_at": t.executed_at.isoformat() if t.executed_at else "",
                "result": t.result,
                "profit": t.profit,
                "closed_at": t.closed_at.isoformat() if t.closed_at else None,
                "reasoning": t.reasoning,
                "confidence": t.confidence,
            }
            for t in recent_trades
        ]

    return ReportsResponse(
        today=today_summary,
        daily_history=daily_history,
        prompts=prompt_stats,
        trades=trades_list,
    )


# ── Journal Pydantic models ─────────────────────────────────────────────────

class JournalSummary(BaseModel):
    total_trades: int = 0
    autopilot_trades: int = 0
    manual_trades: int = 0
    mt5_trades: int = 0
    mt5_available: bool = False
    wins: int = 0
    losses: int = 0
    pnl: float = 0.0
    best_trade: Optional[dict] = None
    worst_trade: Optional[dict] = None


class JournalResponse(BaseModel):
    from_date: str
    to_date: str
    summary: JournalSummary
    trades: List[dict]
    page: int
    per_page: int
    has_next: bool
    has_prev: bool
    total_count: int


@router.get("/journal")
async def get_journal(
    from_date: str,
    to_date: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Trade journal with date range. Primary source: MT5 connector [AUTOPILOT] trades.
    Falls back to local DB autopilot_trades if connector unavailable."""
    from app.models.ai_memory import AutopilotTrade

    user_id = current_user["id"]
    per_page = min(per_page, 100)

    # Parse dates with timezone awareness
    try:
        day_start = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid from_date format. Use YYYY-MM-DD")
    if to_date:
        try:
            day_end = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date format. Use YYYY-MM-DD")
    else:
        day_end = day_start + timedelta(days=1)

    # ── 1. Fetch AI context from DB (prompt_number, reasoning, confidence) ──
    db_trades_by_ticket: dict[int, dict] = {}
    db_only_trades: list[dict] = []
    async with AsyncSessionLocal() as db:
        auto_result = await db.execute(
            select(AutopilotTrade).where(
                AutopilotTrade.user_id == user_id,
                AutopilotTrade.executed_at >= day_start,
                AutopilotTrade.executed_at < day_end,
            ).order_by(AutopilotTrade.executed_at.desc())
        )
        for t in auto_result.scalars().all():
            trade_dict = {
                "prompt_number": t.prompt_number,
                "prompt_text": t.prompt_text,
                "confidence": t.confidence,
                "reasoning": t.reasoning,
            }
            if t.mt5_ticket:
                db_trades_by_ticket[t.mt5_ticket] = trade_dict
            else:
                # No MT5 ticket — keep as fallback
                db_only_trades.append({
                    "id": t.id,
                    "source": "autopilot",
                    "symbol": t.symbol,
                    "direction": t.direction,
                    "entry_price": t.entry_price,
                    "exit_price": None,
                    "stop_loss": t.stop_loss,
                    "take_profit": t.take_profit,
                    "lot_size": t.lot_size,
                    "profit": t.profit,
                    "result": t.result,
                    "executed_at": t.executed_at.isoformat() if t.executed_at else "",
                    "closed_at": t.closed_at.isoformat() if t.closed_at else None,
                    "prompt_number": t.prompt_number,
                    "prompt_text": t.prompt_text,
                    "confidence": t.confidence,
                    "reasoning": t.reasoning,
                    "mt5_ticket": None,
                })

    # ── 2. Fetch MT5 connector history, filter [AUTOPILOT] only ──
    mt5_trades: list[dict] = []
    mt5_available = False
    try:
        mt5_url = settings.MT5_CONNECTOR_URL
        if mt5_url:
            mt5_base = mt5_url.rstrip("/")
            hours = int((day_end - day_start).total_seconds() / 3600) + 1
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{mt5_base}/history",
                    params={"hours": max(hours, 24)},
                    timeout=15,
                )
                if resp.status_code == 200:
                    mt5_available = True
                    mt5_data = resp.json()
                    mt5_deals = mt5_data.get("deals", [])

                    # Filter only [AUTOPILOT] trades
                    auto_deals = [d for d in mt5_deals if (d.get("comment") or "").strip().startswith("[AUTOPILOT]")]

                    # Group OPEN/CLOSE pairs by position_id
                    pos_map: dict[int, dict] = {}
                    for deal in auto_deals:
                        pid = deal.get("position_id")
                        if not pid:
                            continue
                        if pid not in pos_map:
                            pos_map[pid] = {"open": None, "close": None}
                        if deal.get("entry") == "OPEN":
                            pos_map[pid]["open"] = deal
                        else:
                            pos_map[pid]["close"] = deal

                    for pid, pair in pos_map.items():
                        open_deal = pair["open"]
                        close_deal = pair["close"]
                        if not open_deal:
                            continue

                        deal_time_str = open_deal.get("time", "")
                        try:
                            deal_dt = datetime.strptime(deal_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        except (ValueError, TypeError):
                            continue
                        if deal_dt < day_start or deal_dt >= day_end:
                            continue

                        direction = open_deal.get("direction", "")
                        profit = close_deal.get("profit", 0) if close_deal else 0
                        comment = open_deal.get("comment", "") or ""
                        prompt_match = __import__("re").search(r"P(\d+)", comment)
                        prompt_number = int(prompt_match.group(1)) if prompt_match else None

                        # Merge MT5 execution data with DB AI context
                        db_ctx = db_trades_by_ticket.get(pid, {})

                        mt5_trades.append({
                            "id": -pid,
                            "source": "mt5_connector",
                            "symbol": open_deal.get("symbol", ""),
                            "direction": direction,
                            "entry_price": open_deal.get("price"),
                            "exit_price": close_deal.get("price") if close_deal else None,
                            "stop_loss": None,
                            "take_profit": None,
                            "lot_size": open_deal.get("volume", 0),
                            "profit": float(profit) if profit else 0.0,
                            "result": "TP_HIT" if (profit or 0) > 0 else "SL_HIT" if (profit or 0) < 0 else "OPEN",
                            "executed_at": open_deal.get("time", ""),
                            "closed_at": close_deal.get("time", "") if close_deal else None,
                            "prompt_number": db_ctx.get("prompt_number") or prompt_number,
                            "prompt_text": db_ctx.get("prompt_text") or (f"Prompt #{prompt_number}" if prompt_number else "Autopilot"),
                            "confidence": db_ctx.get("confidence"),
                            "reasoning": db_ctx.get("reasoning") or comment,
                            "mt5_ticket": pid,
                        })
    except Exception:
        pass  # MT5 connector optional

    # ── 3. Combine ──
    unified = mt5_trades + db_only_trades
    unified.sort(key=lambda x: x.get("executed_at", ""), reverse=True)

    # ── Summary ──
    total = len(unified)
    mt5_count = len(mt5_trades)
    db_only_count = len(db_only_trades)
    wins = sum(1 for t in unified if (t.get("profit") or 0) > 0)
    losses = sum(1 for t in unified if (t.get("profit") or 0) <= 0)
    pnl = sum(t.get("profit") or 0 for t in unified)

    best = max(unified, key=lambda t: t.get("profit") or 0) if unified else None
    worst = min(unified, key=lambda t: t.get("profit") or 0) if unified else None

    summary = JournalSummary(
        total_trades=total,
        autopilot_trades=mt5_count,
        manual_trades=0,
        mt5_trades=mt5_count,
        wins=wins,
        losses=losses,
        pnl=round(pnl, 2),
        best_trade={
            "symbol": best["symbol"],
            "direction": best["direction"],
            "profit": round(best["profit"], 2),
            "source": best["source"],
        } if best else None,
        worst_trade={
            "symbol": worst["symbol"],
            "direction": worst["direction"],
            "profit": round(worst["profit"], 2),
            "source": worst["source"],
        } if worst else None,
        mt5_available=mt5_available,
    )

    # Pagination
    offset = (page - 1) * per_page
    page_trades = unified[offset:offset + per_page]
    has_next = offset + per_page < len(unified)
    has_prev = page > 1

    return JournalResponse(
        from_date=day_start.strftime("%Y-%m-%d"),
        to_date=(day_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        summary=summary,
        trades=page_trades,
        page=page,
        per_page=per_page,
        has_next=has_next,
        has_prev=has_prev,
        total_count=len(unified),
    )


@router.get("/test")
async def test_endpoint(current_user: dict = Depends(get_current_user)):
    """Simple test endpoint"""
    return {"status": "ok", "message": "Analytics is working"}


@router.post("/feedback")
async def submit_feedback(
    feedback: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback on AI response"""
    try:
        from app.models.ai_memory import UserFeedback
        fb = UserFeedback(
            user_id=current_user["id"],
            chat_memory_id=feedback.chat_memory_id,
            is_helpful=feedback.is_helpful,
            notes=feedback.notes
        )
        db.add(fb)
        await db.commit()
        return {"success": True, "message": "Feedback recorded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculation")
async def record_calculation(
    calc: CalculationRecord,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a calculation performed by AI (ATR, RSI, etc.)"""
    try:
        from app.models.ai_memory import CalculationHistory, IndicatorRequest
        from sqlalchemy import select

        calc_record = CalculationHistory(
            user_id=current_user["id"],
            symbol=calc.symbol,
            indicator=calc.indicator,
            period=calc.period,
            value=calc.value,
            candle_count=calc.candle_count
        )
        db.add(calc_record)

        result = await db.execute(
            select(IndicatorRequest).where(
                IndicatorRequest.user_id == current_user["id"],
                IndicatorRequest.symbol == calc.symbol,
                IndicatorRequest.indicator == calc.indicator
            )
        )
        indicator_req = result.scalar_one_or_none()

        if indicator_req:
            indicator_req.request_count += 1
        else:
            new_req = IndicatorRequest(
                user_id=current_user["id"],
                symbol=calc.symbol,
                indicator=calc.indicator,
                period=calc.period
            )
            db.add(new_req)

        await db.commit()
        return {"success": True, "message": "Calculation recorded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calculations")
async def get_calculation_history(
    symbol: Optional[str] = None,
    indicator: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's calculation history"""
    limit = min(limit, 500)
    try:
        from app.models.ai_memory import CalculationHistory
        from sqlalchemy import select, desc

        query = select(CalculationHistory).where(
            CalculationHistory.user_id == current_user["id"]
        )

        if symbol:
            query = query.where(CalculationHistory.symbol == symbol)
        if indicator:
            query = query.where(CalculationHistory.indicator == indicator)

        query = query.order_by(desc(CalculationHistory.created_at)).offset(skip).limit(limit)

        result = await db.execute(query)
        records = result.scalars().all()

        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "indicator": r.indicator,
                "period": r.period,
                "value": float(r.value),
                "candle_count": r.candle_count,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in records
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indicator-stats")
async def get_indicator_stats(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated indicator usage stats"""
    try:
        from app.models.ai_memory import IndicatorRequest
        from sqlalchemy import select, func

        result = await db.execute(
            select(
                IndicatorRequest.indicator,
                func.sum(IndicatorRequest.request_count).label("total_requests"),
                func.avg(IndicatorRequest.period).label("avg_period")
            )
            .where(IndicatorRequest.user_id == current_user["id"])
            .group_by(IndicatorRequest.indicator)
        )

        stats = []
        for row in result:
            symbol_result = await db.execute(
                select(IndicatorRequest.symbol)
                .where(
                    IndicatorRequest.user_id == current_user["id"],
                    IndicatorRequest.indicator == row[0]
                )
                .order_by(IndicatorRequest.request_count.desc())
                .limit(1)
            )
            symbol_row = symbol_result.fetchone()
            most_used = symbol_row[0] if symbol_row else None

            stats.append({
                "indicator": row[0],
                "total_requests": row[1],
                "most_used_symbol": most_used,
                "avg_period": float(row[2]) if row[2] else None
            })

        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback-stats")
async def get_feedback_stats(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's feedback statistics"""
    try:
        from app.models.ai_memory import UserFeedback
        from sqlalchemy import select, func

        total_result = await db.execute(
            select(func.count(UserFeedback.id))
            .where(UserFeedback.user_id == current_user["id"])
        )
        total = total_result.scalar() or 0

        helpful_result = await db.execute(
            select(func.count(UserFeedback.id))
            .where(
                UserFeedback.user_id == current_user["id"],
                UserFeedback.is_helpful == True
            )
        )
        helpful = helpful_result.scalar() or 0

        return {
            "total_feedback": total,
            "helpful_count": helpful,
            "not_helpful_count": total - helpful,
            "helpful_percentage": round((helpful / total * 100), 1) if total > 0 else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategy-scores")
async def get_strategy_scores(
    symbol: Optional[str] = None,
    sort: str = "win_rate",
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get strategy scoreboard with win rate and P&L per prompt."""
    try:
        from sqlalchemy import select, desc

        query = select(StrategyScore)
        if symbol:
            query = query.where(StrategyScore.symbol == symbol)

        sort_col = getattr(StrategyScore, sort, StrategyScore.win_rate)
        query = query.order_by(desc(sort_col)).limit(50)

        result = await db.execute(query)
        scores = result.scalars().all()

        return [
            {
                "prompt_text": s.prompt_text,
                "symbol": s.symbol,
                "direction": s.direction,
                "source": s.source,
                "total_trades": s.total_trades,
                "winning_trades": s.winning_trades,
                "total_pnl": float(s.total_pnl) if s.total_pnl else 0,
                "win_rate": float(s.win_rate) if s.win_rate else 0,
                "avg_confidence": float(s.avg_confidence) if s.avg_confidence else None,
                "avg_profit": float(s.avg_profit) if s.avg_profit else None,
                "avg_loss": float(s.avg_loss) if s.avg_loss else None,
                "profit_factor": float(s.profit_factor) if s.profit_factor else None,
                "last_used": s.last_used.isoformat() if s.last_used else None,
            }
            for s in scores
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
