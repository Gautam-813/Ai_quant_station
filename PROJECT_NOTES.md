# Impulse Analyst (The Finance Engine v2) - Project Notes

## Project Overview
This is a professional quantitative trading platform migrating from Streamlit to a modern full-stack architecture. It provides real-time market analysis, AI-powered trade suggestions, automated trading via autopilot, and comprehensive portfolio management.

## Architecture
- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui + Zustand (state management)
- **Backend**: FastAPI (Python) with MT5 integration via external connector
- **Database**: SQLite (file-based) for users, HuggingFace Hub for cloud data storage
- **Trading**: MetaTrader 5 integration for live trading
- **AI**: Multiple providers (NVIDIA NIM, Groq, OpenRouter, Google Gemini, GitHub Models, Cerebras)

## Key Features
- JWT-based authentication with role management (Admin/Trader/Viewer)
- Real-time price ticker and candlestick charts (multiple timeframes)
- Order execution (market/pending orders) with SL/TP
- Position management and trade history
- AI chat interface with trade setup detection and one-click execution
- Autopilot system for automated trading
- Data synchronization with HuggingFace Hub
- Memory system for AI conversations and learned insights

## Project Structure
- `frontend/`: React SPA with component-based architecture
- `backend/`: FastAPI API with modular services (auth, MT5, trading, AI, autopilot)
- `mt5_connector/`: Standalone Windows service for MT5 connection (allows backend to run on Linux/Docker)
- `docs/`: Documentation including PRD, setup guides, and API specs

## Development Status
- Currently in draft phase (as of May 7, 2026)
- Milestones defined for 5-week implementation
- Foundation (auth + basic UI) → Core Trading → AI Integration → Autopilot & Data → Polish

## Current Setup
- Backend runs on port 8000
- MT5 Connector runs on port 5001 (Windows only)
- Default admin login: admin / admin@2026
- Can run without MT5 for development (login/dashboard work, trading endpoints show errors)

## Notes for Development
- Follow TypeScript strict mode and component conventions
- Use shadcn/ui for consistent dark theme components
- Implement proper error handling and loading states
- Focus on real-time updates with WebSocket integration
- Ensure security: JWT validation, password hashing, rate limiting
- Performance targets: <2s page load, <500ms API responses, <100ms real-time updates

## Next Steps
[Add development progress and decisions here as we work]

---

## Development Notes

### Login Flow (After Login → Dashboard)
1. User enters credentials on LoginPage (`/login`)
2. AuthStore.login() sends POST to `/api/auth/login`
3. Backend returns JWT access_token + refresh_token
4. On success: navigate('/') redirects to DashboardPage (`/`)
5. ProtectedRoute checks isAuthenticated - if true, shows DashboardLayout with DashboardPage

### Available Pages (All Protected Routes)
| Route | Page | Purpose |
|-------|------|---------|
| `/` | DashboardPage | Account overview, metrics, price ticker |
| `/terminal` | TerminalPage | Live trading, charts, order execution |
| `/ai-analyst` | AIAnalystPage | AI chat, trade setup detection |
| `/history` | HistoryPage | Trade history, closed positions |
| `/settings` | SettingsPage | API keys, autopilot config |

### Current Implementation Status (as of May 10, 2026)
- ✅ Authentication working (login/logout with JWT)
- ✅ Dashboard with metrics
- ✅ Settings page (API keys, providers)
- ✅ Navigation & layout
- 🔄 Terminal page (partial)
- 🔄 AI Analyst (partial)
- 🔄 Trade history

---

## Recent Changes

### May 10, 2026 - MT5 Connector Settings in UI
- Added MT5 Connection settings in Settings page
- Users can now select between Direct MT5 or External Connector
- When using External Connector, user can enter:
  - Server IP (leave empty for localhost)
  - Port number (required, no default)
- Settings saved to localStorage
- Backend accepts `x-mt5-connector-url` header to dynamically route to external connector
- Axios interceptor automatically sends connector URL for all MT5 API calls

---

*Last Updated: May 10, 2026*