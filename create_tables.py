import sqlite3

conn = sqlite3.connect('D:/date-wise/06-04-2026(live current autopilot)/impulse_analyst_v2/backend/finance_engine.db')

# Create missing tables
conn.execute('''
CREATE TABLE IF NOT EXISTS user_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_memory_id INTEGER,
    is_helpful BOOLEAN NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

conn.execute('''
CREATE TABLE IF NOT EXISTS calculation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    indicator TEXT NOT NULL,
    period INTEGER NOT NULL,
    value REAL NOT NULL,
    candle_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

conn.execute('''
CREATE TABLE IF NOT EXISTS indicator_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    indicator TEXT NOT NULL,
    period INTEGER,
    request_count INTEGER DEFAULT 1,
    last_requested TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()

# Verify
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print('Tables now:', tables)

conn.close()