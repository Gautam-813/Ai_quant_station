from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional, Annotated

from ..core.config import settings
from ..core.security import decode_token
from ..models.schemas import OrderRequest, OrderResponse, CloseRequest, ModifyRequest
from ..services.trade_service import place_order as svc_place_order
from ..services.trade_service import close_position as svc_close_position
from ..services.trade_service import modify_position as svc_modify_position
from ..services.trade_service import TradeError

_security = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/trade", tags=["Trading"])


async def verify_mt5_token(
    x_mt5_token: Annotated[Optional[str], Header()] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
):
    if x_mt5_token:
        if x_mt5_token == settings.MT5_API_TOKEN:
            return {"auth_method": "mt5_token", "user_id": None}
        raise HTTPException(status_code=401, detail="Invalid MT5 token")
    if credentials:
        payload = await decode_token(credentials.credentials)
        if payload and payload.get("type") == "access":
            return {"auth_method": "jwt", "user": payload.get("sub"), "user_id": payload.get("user_id")}
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Missing authentication: provide x-mt5-token header or Authorization Bearer token"
    )


def _resolve_user_id(token: dict) -> Optional[int]:
    return token.get("user_id") if isinstance(token, dict) else None


@router.post("/order", response_model=OrderResponse)
async def place_order(order: OrderRequest, token: dict = Depends(verify_mt5_token)):
    """Place a market or pending order."""
    try:
        result = await svc_place_order(order, _resolve_user_id(token))
        return OrderResponse(**result)
    except TradeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/close")
async def close_position(close_req: CloseRequest, token: dict = Depends(verify_mt5_token)):
    """Close an open position."""
    try:
        return await svc_close_position(close_req.ticket, close_req.volume, _resolve_user_id(token))
    except TradeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/modify")
async def modify_position(mod_req: ModifyRequest, token: dict = Depends(verify_mt5_token)):
    """Modify SL and/or TP of a position."""
    try:
        return await svc_modify_position(mod_req.ticket, mod_req.sl, mod_req.tp, _resolve_user_id(token))
    except TradeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)