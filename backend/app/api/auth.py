from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from ..core.database import get_db
from ..core.security import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token,
    decode_token, get_current_user
)
from ..models.user import User
from ..models.schemas import UserLogin, Token, UserResponse, PasswordChange

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login/test", response_model=Token)
async def test_login(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Test login - bypass password verification (for testing only)"""
    result = await db.execute(select(User).where(User.username == user_data.username))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    access_token = create_access_token(data={"sub": user.username, "user_id": user.id})
    refresh_token = create_refresh_token(data={"sub": user.username, "user_id": user.id})
    
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    try:
        user.last_login = datetime.utcnow()
        await db.commit()
    except:
        pass

    access_token = create_access_token(data={"sub": user.username, "user_id": user.id})
    refresh_token = create_refresh_token(data={"sub": user.username, "user_id": user.id})

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_data: dict, db: AsyncSession = Depends(get_db)):
    refresh_token = refresh_data.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token is required"
        )

    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    access_token = create_access_token(data={"sub": user.username, "user_id": user.id})
    new_refresh_token = create_refresh_token(data={"sub": user.username, "user_id": user.id})

    return Token(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    # In a production app, you would blacklist the token here
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == current_user["username"]))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user


@router.put("/password")
async def change_password(
    password_data: PasswordChange,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.username == current_user["username"]))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not verify_password(password_data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    user.hashed_password = get_password_hash(password_data.new_password)
    await db.commit()

    return {"message": "Password changed successfully"}


# Helper function to create default admin user
async def create_default_admin(db: AsyncSession):
    result = await db.execute(select(User).where(User.username == "admin"))
    admin = result.scalar_one_or_none()

    if not admin:
        admin = User(
            username="admin",
            name="Administrator",
            hashed_password=get_password_hash("admin123"),
            role="admin"
        )
        db.add(admin)
        await db.commit()
        print("Default admin user created: admin / admin123")