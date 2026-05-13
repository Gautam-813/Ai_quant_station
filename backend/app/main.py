from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pathlib import Path

from .core.config import settings
from .core.database import init_db
from .api import auth, mt5, trade, ai, yahoo, execute, analytics, autopilot

# Import all models to register them with SQLAlchemy Base before database creation
from . import models  # noqa: F401

app = FastAPI(
    title="The Finance Engine API",
    description="Professional Quantitative Trading Platform API",
    version="2.0.0"
)

@app.on_event("startup")
async def startup_event():
    await init_db()

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
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8002,
        reload=False  # Set to True for development
    )