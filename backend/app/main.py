from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pathlib import Path

from .core.config import settings
from .core.database import AsyncSessionLocal
from .core.security import get_password_hash
from .api import auth, mt5, trade, ai, yahoo, execute, analytics, autopilot, historical_lab, backtest
from .core.mt5_sync import start_sync_scheduler
from .models.user import User

# Import all models to register them with SQLAlchemy Base before database creation
from . import models  # noqa: F401

app = FastAPI(
    title="The Finance Engine API",
    description="Professional Quantitative Trading Platform API",
    version="2.0.0"
)


async def create_default_users():
    """Create default users on first run."""
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(User).where(User.username == "admin"))
            if result.scalar_one_or_none():
                return
            
            default_users = [
                User(username="admin", name="System Administrator", hashed_password=get_password_hash(settings.DEFAULT_ADMIN_PASSWORD or "admin@2026"), role="admin"),
                User(username="keval_viradiya", name="Keval Viradiya", hashed_password=get_password_hash("Usdt@2026"), role="trader"),
                User(username="sagar_barot", name="Sagar Barot", hashed_password=get_password_hash("Usdt@2026"), role="trader"),
                User(username="meet_rao", name="Meet Rao", hashed_password=get_password_hash("Usdt@2026"), role="trader"),
                User(username="guest", name="Guest Viewer", hashed_password=get_password_hash("Usdt@2026"), role="viewer"),
            ]
            for u in default_users:
                session.add(u)
            await session.commit()
            print("Default users created!")
        except Exception as e:
            print(f"Error creating default users: {e}")


def _run_alembic_migrations():
    """Run Alembic migrations synchronously during startup to bring schema to head."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Alembic upgrade failed:\n{result.stderr}")
    else:
        print("Alembic migrations applied successfully.")

@app.on_event("startup")
async def startup_event():
    # Run database migrations via Alembic
    _run_alembic_migrations()
    await create_default_users()
    start_sync_scheduler()

@app.on_event("shutdown")
async def shutdown_event():
    from .core.mt5_connector import shutdown_connector
    from .core.mt5_sync import shutdown_scheduler
    from .api.autopilot import shutdown_http_client
    await shutdown_connector()
    shutdown_scheduler()
    await shutdown_http_client()

# CORS Middleware (still needed for development when frontend runs separately)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth.router, prefix="/api")
app.include_router(mt5.router, prefix="/api")
app.include_router(trade.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(yahoo.router, prefix="/api")
app.include_router(execute.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(autopilot.router, prefix="/api")
app.include_router(historical_lab.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")

# Mount static files (React build) - ONLY if frontend is built
# In development, frontend runs on separate dev server (Vite)
frontend_dist_path = Path(__file__).parent.parent.parent / "frontend" / "dist"

if frontend_dist_path.exists() and frontend_dist_path.is_dir():
    # Production mode: Serve built React frontend
    app.mount("/assets", StaticFiles(directory=frontend_dist_path / "assets"), name="assets")
    
    # Serve React app for all non-API routes (enables client-side routing)
    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        # Don't interfere with API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        
        # Serve index.html for client-side routing (React Router)
        return FileResponse(frontend_dist_path / "index.html")
else:
    # Development mode: Frontend runs on separate Vite dev server
    @app.get("/")
    async def root():
        return {
            "message": "The Finance Engine API is running",
            "docs": "/docs",
            "frontend_dev_server": "http://localhost:5173",
            "note": "To enable single-server deployment: Run 'npm run build' in frontend directory, then restart this server"
        }

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8002"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=(os.getenv("ENV", "production") == "development")
    )