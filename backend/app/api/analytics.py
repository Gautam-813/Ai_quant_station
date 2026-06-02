"""
User Feedback and Analytics Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import get_current_user

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
