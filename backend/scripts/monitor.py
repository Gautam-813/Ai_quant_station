"""
Monitor script: checks backend + MT5 connector health, sends Telegram alerts on failure.
Run every 5 minutes via cron/systemd timer.
"""
import os
import sys
import json
import subprocess
import urllib.request
from datetime import datetime

BACKEND_URL = os.getenv("MONITOR_BACKEND_URL", "http://127.0.0.1:8002")
CONNECTOR_URL = os.getenv("MONITOR_CONNECTOR_URL", "http://193.38.138.202:5001")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def _send_alert(subject: str, body: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[MONITOR] No Telegram configured. Would send: {subject}")
        return
    text = f"*{subject}*\n\n{body}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15)
        print(f"[MONITOR] Alert sent: {subject}")
    except Exception as e:
        print(f"[MONITOR] Failed to send alert: {e}")

def check_backend():
    try:
        r = urllib.request.urlopen(f"{BACKEND_URL}/health", timeout=10)
        return r.status == 200
    except Exception as e:
        print(f"[MONITOR] Backend check failed: {e}")
        return False

def check_connector():
    try:
        r = urllib.request.urlopen(f"{CONNECTOR_URL}/health", timeout=10)
        data = json.loads(r.read())
        return data.get("mt5_connected", False) or data.get("mt5_initialized", False)
    except Exception as e:
        print(f"[MONITOR] Connector check failed: {e}")
        return False

def check_systemd():
    r = subprocess.run(["systemctl", "is-active", "impulse-analyst"], capture_output=True, text=True)
    return r.stdout.strip() == "active"

def main():
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    failures = []

    systemd_ok = check_systemd()
    if not systemd_ok:
        failures.append("Systemd service impulse-analyst is NOT running")

    backend_ok = check_backend()
    if not backend_ok:
        failures.append(f"Backend at {BACKEND_URL}/health is unreachable")

    connector_ok = check_connector()
    if not connector_ok:
        failures.append(f"MT5 connector at {CONNECTOR_URL}/health is unreachable or not initialized")

    status = "OK" if not failures else "FAIL"
    print(f"[MONITOR] {ts} | Backend={'✓' if backend_ok else '✗'} Connector={'✓' if connector_ok else '✗'} Systemd={'✓' if systemd_ok else '✗'} => {status}")

    if failures:
        _send_alert(
            f"[ALERT] Impulse Analyst - {sum(1 for f in failures)} service(s) down",
            f"Time: {ts}\n\n" + "\n".join(failures)
        )

if __name__ == "__main__":
    main()
