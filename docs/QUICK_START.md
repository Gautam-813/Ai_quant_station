# To Run The Finance Engine

## Quick Start

### Step 1: Start Backend
```bash
cd backend
python run.py
```

### Step 2: Open Browser
```
http://localhost:8000
```

### Step 3: Login
- **Username:** admin
- **Password:** admin@2026

---

## For MT5 Trading (Windows with MT5 Terminal)

### Step 1: Install MT5 Connector
```cmd
cd mt5_connector
pip install -r requirements.txt
```

### Step 2: Run MT5 Connector
```cmd
python connector.py --port 5001
```

### Step 3: Update backend .env
```env
MT5_USE_EXTERNAL_CONNECTOR=True
MT5_CONNECTOR_URL=http://localhost:5001
```

### Step 4: Restart Backend
```bash
python run.py
```

---

## If You Get Import Errors

Run these commands to fix:

```bash
pip install --upgrade --force-reinstall pydantic fastapi uvicorn sqlalchemy pydantic-settings
```

Then run backend again:
```bash
python run.py
```

---

## Check Services

| Service | URL | Test Command |
|---------|-----|--------------|
| Backend | http://localhost:8000 | curl http://localhost:8000/health |
| MT5 Connector | http://localhost:5001 | curl http://localhost:5001/health |

---

## Port Already in Use?

If port 5001 is busy:
```cmd
python connector.py --port 5002
```

Then update .env:
```env
MT5_CONNECTOR_URL=http://localhost:5002
```