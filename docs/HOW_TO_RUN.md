# How to Run - Step by Step

## Prerequisites

1. **Python 3.11+** installed
2. **PostgreSQL** running
3. **MetaTrader 5** installed and logged in (for Windows)

---

## Step 1: Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

---

## Step 2: Install MT5 Connector Dependencies (Windows)

```cmd
cd mt5_connector
pip install -r requirements.txt
```

---

## Step 3: Start MT5 Connector (Windows with MT5)

```cmd
cd mt5_connector
python connector.py --port 5001
```

**Expected Output:**
```
============================================================
MT5 Connector Service
============================================================
This service connects to MetaTrader 5 and exposes
REST API for the main backend to use.

To configure port:
  - Environment variable: MT5_CONNECTOR_PORT=5002
  - Command line: python connector.py --port 5002

Starting service on http://0.0.0.0:5001...
============================================================
```

---

## Step 4: Start Main Backend

**Option A: Using External MT5 Connector** (recommended)

Edit `backend/.env`:
```env
MT5_USE_EXTERNAL_CONNECTOR=True
MT5_CONNECTOR_URL=http://localhost:5001
```

Then run:
```bash
cd backend
python run.py
```

**Option B: Direct MT5 (Same Windows Server)**

Edit `backend/.env`:
```env
MT5_USE_EXTERNAL_CONNECTOR=False
```

Then run:
```bash
cd backend
python run.py
```

**Expected Output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## Step 5: Test Everything

### Test 1: Health Check

Open browser or use curl:
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{"status": "healthy"}
```

### Test 2: Login

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin@2026"}'
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### Test 3: MT5 Connection (if using connector)

```bash
curl http://localhost:8000/api/mt5/health \
  -H "X-MT5-Token: impulse_secure_2026"
```

**Response:**
```json
{
  "status": "running",
  "mt5_initialized": true,
  "server": "your-broker-server"
}
```

---

## Quick Commands Summary

| Action | Command |
|--------|---------|
| **Start MT5 Connector** | `python connector.py --port 5001` |
| **Start Backend** | `python run.py` |
| **Test Backend Health** | `curl http://localhost:8000/health` |
| **Test Login** | `curl -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"admin@2026\"}"` |
| **Test MT5** | `curl http://localhost:8000/api/mt5/positions -H "X-MT5-Token: impulse_secure_2026"` |

---

## If MT5 Not Available (Testing Without MT5)

The backend and login will still work! Just MT5 endpoints will show errors.

To test login flow:
1. Start backend: `python run.py`
2. Open browser: `http://localhost:8000`
3. Login with: `admin` / `admin@2026`
4. Dashboard will show "MT5 not initialized" - that's normal without MT5

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port 5001 busy | `python connector.py --port 5002` |
| PostgreSQL not running | Start PostgreSQL service |
| MT5 not connected | Open MT5 terminal and login |
| Login fails | Check PostgreSQL has users (run setup_postgres.py) |