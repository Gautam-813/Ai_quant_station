import sqlite3
conn = sqlite3.connect('D:/date-wise/06-04-2026(live current autopilot)/impulse_analyst_v2/backend/finance_engine.db')
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print('Tables:', tables)
print('Has user_feedback:', 'user_feedback' in tables)
print('Has calculation_history:', 'calculation_history' in tables)
print('Has indicator_requests:', 'indicator_requests' in tables)
conn.close()