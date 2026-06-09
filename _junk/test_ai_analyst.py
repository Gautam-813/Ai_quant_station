"""
End-to-end test suite for AI Analyst page.
Tests all key flows: login, data fetch, candle counts, chat, feedback.
"""
import httpx
import json
import time
import re
import sys

BASE = "http://localhost:8002"

def log(label, ok, detail=""):
    icon = "OK" if ok else "XX"
    print(f"  [{icon}] {label}" + (f" | {detail}" if detail else ""))

def main():
    total = 0
    passed = 0
    client = httpx.Client(base_url=BASE, timeout=30)

    # ── Login ────────────────────────────────────────────────────────────────
    print("\n=== 1. AUTH ===")
    total += 1
    try:
        r = client.post("/api/auth/login", json={"username": "admin", "password": "admin@2026"})
        ok = r.status_code == 200 and "access_token" in r.json()
        token = r.json().get("access_token", "")
        log("Login as admin", ok, f"status={r.status_code}")
        if ok: passed += 1
        if not token:
            print("  !! Cannot proceed without auth token")
            return
    except Exception as e:
        log("Login as admin", False, str(e))
        return

    headers = {"Authorization": f"Bearer {token}"}

    # ── Providers ────────────────────────────────────────────────────────────
    print("\n=== 2. PROVIDERS ===")
    total += 1
    r = client.get("/api/ai/providers", headers=headers)
    providers = r.json().get("providers", [])
    provider_names = [p["id"] for p in providers]
    ok = r.status_code == 200 and len(providers) > 2
    log(f"Providers list ({len(providers)} found)", ok, f"names={provider_names}")
    if ok: passed += 1

    # Find NVIDIA and Mistral
    nvidia = next((p for p in providers if p["id"] == "nvidia"), None)
    mistral = next((p for p in providers if p["id"] == "mistral"), None)
    nvidia_model = nvidia["models"][0] if nvidia and nvidia["models"] else "qwen/qwen3.5-122b-a10b"
    mistral_model = mistral["models"][0] if mistral and mistral["models"] else "mistral-large-latest"

    # ── Candle Count Detection Logic ─────────────────────────────────────────
    print("\n=== 3. CANDLE COUNT DETECTION (frontend logic) ===")
    def detect_required_candles(query):
        lower = query.lower()
        if re.search(r'daily|weekly|d1|w1|1d\b|previous\s*day|yesterday', lower): return 30000
        if re.search(r'4h\b|4[-\s]?hour|four\s*hour|h4\b|4hrs?\b', lower): return 10000
        if re.search(r'1h\b|1[-\s]?hour|one\s*hour|hourly|h1\b|1hrs?\b', lower): return 5000
        if re.search(r'30m\b|30[-\s]?min|m30|thirty\s*min', lower): return 3000
        return 2000

    test_queries = [
        ("scalp setup on 1m", 2000),
        ("30 minute resistance", 3000),
        ("1hour trend analysis", 5000),
        ("4h ATR and RSI", 10000),
        ("four hour breakout setup", 10000),
        ("daily pivot level", 30000),
        ("weekly support and resistance", 30000),
        ("previous day high low", 30000),
        ("yesterday close price", 30000),
        ("1d chart analysis", 30000),
        ("calculate moving average on 1hr", 5000),
    ]
    for query, expected in test_queries:
        total += 1
        result = detect_required_candles(query)
        ok = result == expected
        log(f"'{query}' -> {result}", ok, f"expected={expected}")
        if ok: passed += 1

    # ── MT5 Data Fetch Tests ────────────────────────────────────────────────
    print("\n=== 4. MT5 DATA FETCH ===")
    symbol = "XAUUSD"

    fetch_results = {}
    for label, count in [("Initial 2000", 2000), ("4H 10000", 10000), ("Daily 30000", 30000)]:
        total += 1
        try:
            r = client.post("/api/mt5/data/latest",
                json={"symbol": symbol, "timeframe": "1m", "count": count},
                headers=headers, timeout=15)
            data = r.json()
            got = len(data.get("data", []))
            ok = r.status_code == 200 and data.get("success") and got > 0
            fetch_results[count] = got
            log(f"MT5 {symbol} count={count:5d} -> got={got:5d}", ok)
            if ok: passed += 1
        except Exception as e:
            log(f"MT5 {symbol} count={count:5d}", False, str(e))
            fetch_results[count] = 0

    # Use 2000 candles for chat test
    r = client.post("/api/mt5/data/latest",
        json={"symbol": symbol, "timeframe": "1m", "count": 2000},
        headers=headers, timeout=15)
    candle_data = r.json().get("data", [])[:2000]
    print(f"\n  Using {len(candle_data)} candles for chat test")

    # ── AI Chat Test ─────────────────────────────────────────────────────────
    print("\n=== 5. AI CHAT (with candle data) ===")
    total += 1
    model_to_use = mistral_model
    provider_to_use = "mistral"
    chat_memory_id = None
    try:
        r = client.post("/api/ai/chat",
            json={
                "messages": [{"role": "user", "content": "Calculate ATR(14) on the 1m data and tell me if volatility is high or normal. Show Python code."}],
                "provider": provider_to_use,
                "model": model_to_use,
                "persona": "technical_analyst",
                "symbol": symbol,
                "load_market_data": "mt5",
                "data_period": "1mo",
                "timeframe": "1m",
                "candle_data": candle_data
            },
            headers=headers, timeout=60)
        resp = r.json()
        has_message = bool(resp.get("message"))
        has_chat_id = resp.get("chat_memory_id") is not None
        has_code = "```python" in (resp.get("message") or "")
        ok = r.status_code == 200 and has_message and has_chat_id
        log(f"Chat {provider_to_use}/{model_to_use}", ok,
            f"msg_len={len(resp.get('message',''))} chat_id={resp.get('chat_memory_id')} code={has_code}")
        if ok: passed += 1
        chat_memory_id = resp.get("chat_memory_id")

        exec_output = resp.get("execution_output")
        if exec_output:
            print(f"  Result: {exec_output[:300]}...")
        if resp.get("execution_charts"):
            print(f"  Charts returned: {len(resp['execution_charts'])}")

        # ── Self-Correction test ────────────────────────────────────────────
        print("\n=== 6. SELF-CORRECTION (broken code) ===")
        total += 1
        r2 = client.post("/api/ai/chat",
            json={
                "messages": [{"role": "user",
                    "content": "Write broken Python code that references undefined_var and then fix it."}],
                "provider": provider_to_use,
                "model": model_to_use,
                "persona": "technical_analyst",
                "symbol": symbol,
                "load_market_data": "mt5",
                "data_period": "1mo",
                "timeframe": "1m",
                "candle_data": candle_data[:100]
            },
            headers=headers, timeout=90)
        resp2 = r2.json()
        ok2 = r2.status_code == 200
        log(f"Self-correction chat", ok2, f"chat_id={resp2.get('chat_memory_id')}")
        if ok2: passed += 1

    except Exception as e:
        log(f"Chat test", False, str(e))

    # ── Feedback Test ────────────────────────────────────────────────────────
    print("\n=== 7. FEEDBACK ===")
    total += 1
    try:
        r = client.post("/api/analytics/feedback",
            json={"chat_memory_id": chat_memory_id, "is_helpful": True},
            headers=headers)
        ok = r.status_code == 200
        log(f"Feedback (chat_memory_id={chat_memory_id})", ok)
        if ok: passed += 1
    except Exception as e:
        log(f"Feedback", False, str(e))

    # ── Backend 30000 candle cap test ────────────────────────────────────────
    print("\n=== 8. BACKEND 30000 CANDLE CAP ===")
    total += 1
    try:
        big_data = candle_data * 15
        big_data = big_data[:30000]
        print(f"  Sending {len(big_data)} candles...")
        r = client.post("/api/ai/chat",
            json={
                "messages": [{"role": "user", "content": "How many candles do you have? Print df.shape"}],
                "provider": provider_to_use,
                "model": model_to_use,
                "persona": "quant",
                "symbol": symbol,
                "load_market_data": "mt5",
                "data_period": "1mo",
                "timeframe": "1m",
                "candle_data": big_data
            },
            headers=headers, timeout=120)
        resp3 = r.json()
        output = resp3.get("execution_output", "")
        ok = r.status_code == 200 and bool(output)
        log(f"30000 candles in sandbox", ok, f"output={output[:200] if output else 'none'}")
        if ok: passed += 1
    except Exception as e:
        log(f"30000 candles sandbox", False, str(e))

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"  RESULTS: {passed}/{total} passed")
    print(f"{'='*50}")
    if passed == total:
        print("  ALL TESTS PASSED")
    else:
        print(f"  {total - passed} FAILURES")
    print()

if __name__ == "__main__":
    main()
