# The Finance Engine v2 - Product Requirements Document

## Project Name: The Finance Engine v2 (Impulse Analyst)

**Version:** 1.0
**Date:** May 7, 2026
**Status:** Draft

---

## 1. Executive Summary

### 1.1 Project Overview

The Finance Engine v2 is a professional-grade quantitative trading platform that migrates from Streamlit to a modern React + FastAPI architecture. The platform provides real-time market analysis, AI-powered trade suggestions, automated trading via autopilot, and comprehensive portfolio management.

### 1.2 Problem Statement

The existing Streamlit-based application has reached its limitations:
- Limited UI customization and branding
- State management complexity
- No true single-page application experience
- Performance issues with real-time updates
- Difficult to maintain and extend

### 1.3 Solution

A full-stack web application using:
- **Frontend:** React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui
- **Backend:** FastAPI (Python) with MT5 integration
- **Authentication:** JWT-based system with role management
- **Data:** HuggingFace Hub for cloud storage, MT5 for live trading

---

## 2. Technology Stack

### 2.1 Frontend Technologies

| Category | Technology | Version |
|----------|------------|---------|
| Framework | React | 18.x |
| Build Tool | Vite | 5.x |
| Language | TypeScript | 5.x |
| Styling | Tailwind CSS | 3.x |
| Components | shadcn/ui | latest |
| Charts | Recharts + Plotly.js | latest |
| State Management | Zustand | latest |
| HTTP Client | Axios | latest |
| Routing | React Router | 6.x |
| WebSocket | Socket.io-client | latest |

### 2.2 Backend Technologies

| Category | Technology | Version |
|----------|------------|---------|
| Framework | FastAPI | 0.109.x |
| Server | Uvicorn | 0.27.x |
| MT5 | MetaTrader5 | latest |
| Data | Pandas, NumPy | latest |
| Authentication | Python-Jose | latest |
| Database | SQLite (file-based) | - |
| HuggingFace | huggingface_hub | latest |

### 2.3 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  Auth    │  │Dashboard │  │ Trading  │  │   AI     │        │
│  │  Pages   │  │  Pages   │  │  Pages   │  │  Pages   │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                            │                                    │
│                     ┌─────▼─────┐                              │
│                     │   Store   │                              │
│                     │  (Zustand)│                              │
│                     └─────┬─────┘                              │
└───────────────────────────│────────────────────────────────────┘
                            │ HTTP / WebSocket
┌───────────────────────────│────────────────────────────────────┐
│                        BACKEND (FastAPI)                       │
│                     ┌─────▼─────┐                              │
│                     │   API     │                              │
│                     │  Routes   │                              │
│                     └─────┬─────┘                              │
│        ┌──────────────────┼──────────────────┐                │
│   ┌────▼────┐        ┌────▼────┐        ┌────▼────┐          │
│   │  Auth   │        │   MT5   │        │   AI    │          │
│   │ Service │        │ Service │        │ Service │          │
│   └─────────┘        └─────────┘        └─────────┘          │
│        │                  │                  │                │
│   ┌────▼────────┐   ┌────▼────────┐   ┌────▼────────┐        │
│   │   Users     │   │   MT5       │   │   HF Hub   │        │
│   │   DB        │   │   Terminal  │   │   Storage  │        │
│   └─────────────┘   └─────────────┘   └─────────────┘        │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Feature Requirements

### 3.1 Authentication Module

#### 3.1.1 User Login
- Username/password authentication
- JWT token-based sessions (access + refresh tokens)
- Cookie-based token storage
- Session persistence across browser refresh
- Logout functionality with token invalidation

#### 3.1.2 User Management
- User registration (admin only)
- Role-based access (Admin, Trader, Viewer)
- Password change functionality
- User profile management

#### 3.1.3 Security
- Password hashing (bcrypt)
- Token expiration (15 min access, 7 days refresh)
- Rate limiting on auth endpoints
- Audit logging

### 3.2 Dashboard Module

#### 3.2.1 Overview Dashboard
- Account summary (Balance, Equity, Margin)
- Open positions count and total P&L
- Win rate display
- Quick action buttons
- Recent activity feed

#### 3.2.2 Real-time Price Ticker
- Live price updates via WebSocket
- Multiple symbols display
- Price change indicators (green/red)
- Symbol search functionality

#### 3.2.3 Performance Charts
- Equity curve over time
- Win/Loss pie chart
- Monthly P&L bar chart
- Drawdown visualization

### 3.3 Trading Module

#### 3.3.1 Symbol Selection
- Broker symbol list (from MT5)
- Symbol search
- Symbol favorites
- Recent symbols

#### 3.3.2 Market Data View
- Candlestick chart (multiple timeframes: 1m, 5m, 15m, 1h, 4h, 1D)
- OHLCV data table
- Technical indicators overlay option
- Time range selector

#### 3.3.3 Order Execution
- Market order (BUY/SELL)
- Pending orders (Limit/Stop)
- Lot size input (manual or auto-risk)
- SL/TP input with validation
- One-click execution
- Order confirmation modal

#### 3.3.4 Position Management
- Open positions list
- Position modification (SL/TP)
- Partial/full close
- Trailing stop functionality
- Position history

#### 3.3.5 Trade History
- Closed trades list
- Date range filtering
- Symbol filtering
- Direction filtering
- Export to CSV

### 3.4 AI Analyst Module

#### 3.4.1 AI Chat Interface
- Text input for analysis requests
- Markdown support for AI responses
- Syntax highlighting for code
- Chat history
- Clear conversation button

#### 3.4.2 AI Provider Integration
- NVIDIA NIM
- Groq
- OpenRouter
- Google Gemini
- GitHub Models
- Cerebras

#### 3.4.3 AI Trade Detection
- JSON trade setup parsing
- Trade card generation from AI response
- One-click trade execution from AI suggestion
- Action detection (CLOSE, MODIFY_SL, MODIFY_TP)

#### 3.4.4 Memory System
- Conversation persistence
- Learned insights storage
- User preferences
- Trade statistics
- Feedback system (thumbs up/down, star rating)

### 3.5 Autopilot Module

#### 3.5.1 Autopilot Controls
- Enable/Disable toggle
- Lot size configuration
- Interval setting (minutes)
- Run on startup option

#### 3.5.2 Prompt Management
- Prompt file management
- Random prompt selection
- Custom prompt categories

#### 3.5.3 Autopilot Logging
- Real-time log display
- Success/failure counters
- Error messages
- Trade execution history

### 3.6 Data Sync Module

#### 3.6.1 HuggingFace Integration
- Download historical data
- Upload processed data
- Delta sync (only new candles)
- Repository management

#### 3.6.2 MT5 Data Fetch
- Fetch by date range
- Fetch latest N candles
- Multiple timeframes support
- Symbol resolution

#### 3.6.3 Yahoo Finance Fallback
- Alternative data source
- Limited symbol support
- Offline mode support

### 3.7 Market Intelligence Module

#### 3.7.1 News Feed
- Yahoo Finance news
- Symbol-specific news
- Sentiment analysis

#### 3.7.2 Web Search
- Market news search
- General search
- AI-powered summarization

---

## 4. UI/UX Requirements

### 4.1 Design System

#### 4.1.1 Color Palette
- **Background:** #0d1117 (dark)
- **Card:** #161b22 (dark card)
- **Border:** #30363d (subtle border)
- **Gold Accent:** #f0b429 (primary action)
- **Text Primary:** #f0f6fc
- **Text Secondary:** #8b949e
- **Success:** #22c55e (green)
- **Danger:** #ef4444 (red)
- **Warning:** #f59e0b (amber)

#### 4.1.2 Typography
- **Headings:** Syne (bold, modern)
- **Body:** DM Sans (clean, readable)
- **Monospace:** JetBrains Mono (code blocks)

#### 4.1.3 Layout
- Sidebar navigation (280px)
- Main content area (fluid)
- Header bar (60px)
- Responsive breakpoints: 640px, 768px, 1024px, 1280px

### 4.2 Components

#### 4.2.1 Navigation
- Logo + app name
- Navigation items with icons
- Active state indicator
- User profile section
- Logout button

#### 4.2.2 Cards
- Rounded corners (8px)
- Subtle border
- Header + content sections
- Action buttons

#### 4.2.3 Forms
- Dark input fields
- Floating labels
- Error states (red border)
- Success states (green border)
- Loading states

#### 4.2.4 Tables
- Alternating row colors
- Sortable columns
- Pagination
- Row hover effects

#### 4.2.5 Charts
- Dark theme
- Tooltip on hover
- Responsive sizing
- Legend positioning

### 4.3 Pages

#### 4.3.1 Login Page
- Centered card
- Logo + app name
- Username/password inputs
- Remember me option
- Error messages
- Loading state

#### 4.3.2 Dashboard Page
- 4-column metrics grid
- Price ticker section
- Chart area (50% height)
- Quick actions
- Recent activity

#### 4.3.3 Live Terminal Page
- Symbol + timeframe selectors
- Candlestick chart
- Order form (sidebar)
- Positions list
- Account info bar

#### 4.3.4 AI Analyst Page
- Chat interface (70% width)
- History sidebar (30% width)
- Trade setup card
- Action suggestion card
- Feedback buttons

#### 4.3.5 Trade History Page
- Filter controls
- Summary metrics
- Data table
- Export button

#### 4.3.6 Settings Page
- API key management
- AI provider selection
- Autopilot configuration
- Data sync settings

---

## 5. API Endpoints

### 5.1 Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/auth/login | User login |
| POST | /api/auth/logout | User logout |
| POST | /api/auth/refresh | Refresh token |
| GET | /api/auth/me | Current user |
| PUT | /api/auth/password | Change password |

### 5.2 MT5 Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/mt5/health | Server health check |
| POST | /api/mt5/initialize | Initialize MT5 |
| GET | /api/mt5/symbols | All available symbols |
| GET | /api/mt5/symbol/{symbol} | Symbol info |
| POST | /api/mt5/data/fetch | Fetch OHLC data |
| POST | /api/mt5/data/latest | Fetch latest candles |
| GET | /api/mt5/account | Account information |
| GET | /api/mt5/positions | Open positions |
| GET | /api/mt5/history | Trade history |

### 5.3 Trading

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/trade/order | Place order |
| POST | /api/trade/close | Close position |
| POST | /api/trade/modify | Modify position |
| POST | /api/trade/validate | Validate order |

### 5.4 AI Integration

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/ai/chat | Send chat message |
| GET | /api/ai/providers | Available providers |
| POST | /api/ai/test | Test connection |
| GET | /api/memory/history | Conversation history |
| POST | /api/memory/feedback | Save feedback |

### 5.5 Data Sync

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/data/load | Load from HF |
| POST | /api/data/sync | Sync data |
| GET | /api/data/gap | Check data gap |

### 5.6 Autopilot

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/autopilot/start | Start autopilot |
| POST | /api/autopilot/stop | Stop autopilot |
| GET | /api/autopilot/status | Get status |
| GET | /api/autopilot/logs | Get logs |

---

## 6. Data Models

### 6.1 User
```typescript
interface User {
  id: number;
  username: string;
  name: string;
  role: 'admin' | 'trader' | 'viewer';
  created_at: string;
  last_login: string;
}
```

### 6.2 Position
```typescript
interface Position {
  ticket: number;
  symbol: string;
  direction: 'BUY' | 'SELL';
  volume: number;
  entry_price: number;
  current_price: number;
  sl: number | null;
  tp: number | null;
  profit: number;
  open_time: string;
}
```

### 6.3 Trade
```typescript
interface Trade {
  ticket: number;
  symbol: string;
  direction: 'BUY' | 'SELL';
  volume: number;
  price: number;
  profit: number;
  close_time: string;
  comment: string;
}
```

### 6.4 TradeSetup (from AI)
```typescript
interface TradeSetup {
  action: 'TRADE_SETUP';
  symbol: string;
  direction: 'BUY' | 'SELL';
  order_type: 'market' | 'limit' | 'stop';
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  lot_size: number;
  risk_reward: number;
  reasoning: string;
}
```

### 6.5 ChatMessage
```typescript
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  detected_setup?: TradeSetup;
  detected_action?: TradeAction;
}
```

---

## 7. Non-Functional Requirements

### 7.1 Performance
- Page load time < 2 seconds
- API response time < 500ms
- Real-time updates < 100ms latency
- Chart rendering < 1 second

### 7.2 Security
- JWT token validation on every request
- Password hashing with salt
- SQL injection prevention
- CORS configuration
- Rate limiting (100 req/min)

### 7.3 Reliability
- MT5 connection retry (3 attempts)
- Graceful error handling
- Offline mode support
- Auto-reconnect on disconnect

### 7.4 Maintainability
- Component-based architecture
- Clear folder structure
- TypeScript strict mode
- ESLint + Prettier configured

---

## 8. Project Structure

```
impulse_analyst_v2/
├── frontend/                    # React frontend
│   ├── public/                  # Static assets
│   ├── src/
│   │   ├── components/          # Reusable components
│   │   │   ├── ui/              # shadcn components
│   │   │   ├── layout/          # Layout components
│   │   │   ├── trading/         # Trading components
│   │   │   ├── ai/              # AI components
│   │   │   └── charts/         # Chart components
│   │   ├── pages/              # Page components
│   │   ├── hooks/              # Custom hooks
│   │   ├── services/           # API services
│   │   ├── store/              # Zustand store
│   │   ├── types/              # TypeScript types
│   │   ├── utils/              # Utility functions
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── api/                # API routes
│   │   │   ├── auth.py
│   │   │   ├── mt5.py
│   │   │   ├── trade.py
│   │   │   ├── ai.py
│   │   │   ├── data.py
│   │   │   └── autopilot.py
│   │   ├── core/               # Core config
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── database.py
│   │   ├── models/             # Data models
│   │   │   ├── user.py
│   │   │   └── schemas.py
│   │   ├── services/           # Business logic
│   │   │   ├── mt5_service.py
│   │   │   ├── ai_service.py
│   │   │   └── memory_service.py
│   │   └── main.py
│   ├── requirements.txt
│   └── .env.example
│
├── docs/                       # Documentation
│   ├── PRD.md
│   ├── API.md
│   └── ARCHITECTURE.md
│
└── README.md
```

---

## 9. Milestones

### Milestone 1: Foundation (Week 1)
- [ ] Project structure setup
- [ ] FastAPI backend with auth
- [ ] React frontend with routing
- [ ] Login page + authentication
- [ ] Basic layout and navigation

### Milestone 2: Core Trading (Week 2)
- [ ] MT5 connection
- [ ] Symbol list fetching
- [ ] OHLC data display
- [ ] Order execution
- [ ] Position management

### Milestone 3: AI Integration (Week 3)
- [ ] AI chat interface
- [ ] Multiple provider support
- [ ] Trade setup detection
- [ ] Trade execution from AI
- [ ] Memory system

### Milestone 4: Autopilot & Data (Week 4)
- [ ] Autopilot system
- [ ] HuggingFace sync
- [ ] Data visualization
- [ ] Trade history

### Milestone 5: Polish (Week 5)
- [ ] Performance optimization
- [ ] Bug fixes
- [ ] UI/UX refinements
- [ ] Testing
- [ ] Deployment

---

## 10. Acceptance Criteria

### Authentication
- [ ] Users can login with username/password
- [ ] JWT tokens are issued and validated
- [ ] Sessions persist across refresh
- [ ] Logout invalidates tokens

### Trading
- [ ] All broker symbols are listed
- [ ] Candlestick charts render correctly
- [ ] Market orders execute successfully
- [ ] Pending orders work correctly
- [ ] Positions can be modified/closed
- [ ] Trade history displays correctly

### AI
- [ ] Chat messages send and receive
- [ ] Multiple AI providers work
- [ ] Trade setups are detected
- [ ] One-click execution works
- [ ] Memory persists across sessions

### Autopilot
- [ ] Autopilot starts/stops correctly
- [ ] Orders execute automatically
- [ ] Logs display in real-time
- [ ] Error handling works

### Performance
- [ ] Page loads under 2 seconds
- [ ] Charts render smoothly
- [ ] No memory leaks
- [ ] WebSocket updates are fast

---

## 11. Out of Scope (v1)

- Mobile app
- Multi-account management
- Backtesting engine
- Strategy builder
- Portfolio optimization
- Social trading features

---

## 12. Risks and Mitigation

| Risk | Impact | Mitigation |
|------|--------|-------------|
| MT5 connection issues | High | Retry logic, clear error messages |
| API rate limits | Medium | Queue system, caching |
| AI provider downtime | Medium | Fallback providers |
| Data sync failures | Low | Offline mode, manual retry |

---

**Document Version:** 1.0
**Last Updated:** May 7, 2026
**Next Review:** After Milestone 1 completion