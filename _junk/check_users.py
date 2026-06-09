import sqlite3
conn = sqlite3.connect("backend/finance_engine.db")
users = conn.execute("SELECT id, username, role FROM users").fetchall()
print("Users:", users)
conn.close()
