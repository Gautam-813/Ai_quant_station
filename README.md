# The Finance Engine v2

A professional quantitative trading platform built with React + FastAPI.

## Project Structure

```
impulse_analyst_v2/
├── frontend/                 # React frontend (Vite + TypeScript)
├── backend/                  # FastAPI backend
└── docs/                     # Documentation including PRD
```

## Getting Started

### Prerequisites
- Node.js 18+ 
- Python 3.9+
- MetaTrader 5 (for live trading)
- HuggingFace account (for data storage)

### Backend Setup

1. Navigate to backend directory:
   ```bash
   cd backend
   ```

2. Create virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   source venv/bin/activate  # Linux/Mac
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create `.env` file from `.env.example`:
   ```bash
   copy .env.example .env  # Windows
   cp .env.example .env    # Linux/Mac
   ```

5. Edit `.env` with your configuration:
   - MT5_SERVER_PORT
   - MT5_API_TOKEN
   - HF_REPO_ID and HuggingFace_API_KEY
   - AI provider API keys (NVIDIA, Groq, etc.)

6. Start the server:
   ```bash
   cd app
   python main.py
   ```
   
   The API will be available at http://localhost:8000
   API docs at http://localhost:8000/docs

### Frontend Setup

1. Navigate to frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```
   
   The app will be available at http://localhost:5173

## Features Implemented

✅ Authentication (login/logout with JWT)
✅ MT5 data fetching (symbols, OHLC data, account info)
✅ Trade execution (market/pending orders, SL/TP)
✅ Position management
✅ AI chat integration (multiple providers)
✅ Basic UI components
✅ Dashboard with metrics
✅ Trading terminal
✅ AI analyst
✅ Trade history
✅ Settings page

## Next Steps

1. Implement real-time price updates via WebSocket
2. Add charting with candlesticks
3. Enhance autopilot system
4. Implement proper data persistence
5. Add comprehensive testing
6. Production deployment setup

## License

MIT