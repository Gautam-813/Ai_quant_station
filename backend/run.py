"""
Run the FastAPI server directly without module imports.
"""
import os
import sys

# Add backend folder to path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

# Now import the app
from app.main import app

# Run with uvicorn
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
        log_level="info"
    )