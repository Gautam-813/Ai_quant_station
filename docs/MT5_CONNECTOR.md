# MT5 Connector - Setup Guide

## Overview

The MT5 Connector is a standalone Windows service that connects to MetaTrader 5 and exposes a REST API. This allows the main backend to run on a different server (Linux/Docker) while MT5 runs on a Windows server.

## Architecture

```
┌─────────────────────┐     HTTP API      ┌─────────────────────┐
│  Main Backend       │ ◄─────────────────► │  MT5 Connector      │
│  (Linux/Docker)     │                    │  (Windows Server)   │
│  Port: 8000         │                    │  Port: 5001         │
└─────────────────────┘                    └──────────┬──────────┘
                                                       │
                                                       ▼
                                            ┌─────────────────────┐
                                            │  MetaTrader 5        │
                                            │  (Trading Terminal) │
                                            └─────────────────────┘
```

## Setup Steps

### Step 1: Windows Server (MT5 Connector)

1. **Install Python 3.11+** on Windows server
   - Download from: https://www.python.org/downloads/

2. **Install MetaTrader 5**
   - Download from your broker
   - Login with your trading account
   - Keep MT5 running (can minimize)

3. **Install MT5 Connector dependencies**
   ```cmd
   cd mt5_connector
   pip install -r requirements.txt
   ```

4. **Run the MT5 Connector**
   ```cmd
   python connector.py
   ```
   
   The service will start on `http://localhost:5001`

### Step 2: Main Backend Configuration

Edit `backend/.env`:
```env
# Use external connector
MT5_USE_EXTERNAL_CONNECTOR=True
MT5_CONNECTOR_URL=http://YOUR_WINDOWS_SERVER_IP:5001
```

### Step 3: Start Everything

1. Start MT5 Connector on Windows server
2. Start main backend (on Linux/Docker/Windows)
3. Open browser and login

## Deployment Options

### Option A: Both on Same Windows Server
- Run both MT5 Connector and backend on same Windows machine
- Set `MT5_CONNECTOR_URL=http://localhost:5001`

### Option B: Separate Servers
- MT5 Connector on Windows server (with MT5 terminal)
- Main backend on Linux server/Docker
- Set `MT5_CONNECTOR_URL=http://192.168.1.100:5001` (Windows server IP)

### Option C: Docker (Backend Only)
```bash
docker-compose up --build
```
- MT5 Connector still runs on Windows (not containerized due to MT5)

## Troubleshooting

### "MT5 not initialized" error
1. Check MT5 terminal is running on Windows server
2. Check Windows Firewall allows port 5001
3. Verify connector URL is correct

### "Connection refused" error
1. Check MT5 Connector is running: `http://connector_ip:5001`
2. Check firewall rules on Windows server
3. Verify IP address is accessible

### MT5 Login Issues
1. Ensure MT5 terminal is logged in to broker
2. Check account is not demo/expired
3. Try restarting MT5 terminal

## Security Notes

- Change default port 5001 if needed
- Use firewall to restrict access to MT5 Connector
- Use HTTPS in production (can add nginx in front)
- Keep MT5_API_TOKEN secure

## Port Configuration

The MT5 Connector port is **fully configurable**. Default is `5001`.

### Method 1: Environment Variable (Recommended)
```cmd
set MT5_CONNECTOR_PORT=5002
python connector.py
```

### Method 2: Command Line Argument
```cmd
python connector.py --port 5002
```

### Method 3: Both
```cmd
set MT5_CONNECTOR_PORT=5003
python connector.py --port 5003
```

### Configure Backend to Use Different Port

Edit `backend/.env`:
```env
MT5_CONNECTOR_URL=http://192.168.1.100:5002
```

---

## Quick Test

Test MT5 Connector separately:
```cmd
# On Windows server
curl http://localhost:5001/health
# Should return: {"status": "healthy", "mt5_connected": true}

curl http://localhost:5001/account
# Should return account info
```