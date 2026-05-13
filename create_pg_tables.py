import psycopg2

conn = psycopg2.connect('host=localhost port=5432 dbname=impulse_analyst user=postgres password=postgres')
cursor = conn.cursor()

# Create tables
cursor.execute('''
CREATE TABLE IF NOT EXISTS user_feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chat_memory_id INTEGER,
    is_helpful BOOLEAN NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS calculation_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    indicator TEXT NOT NULL,
    period INTEGER NOT NULL,
    value REAL NOT NULL,
    candle_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS indicator_requests (
    id SERIAL PRIMARY KEY,
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
cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
tables = [r[0] for r in cursor.fetchall()]
print('Tables:', tables)

conn.close()