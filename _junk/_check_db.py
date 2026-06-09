import sqlite3, os
db_path = 'finance_engine.db'
print(f'DB exists: {os.path.exists(db_path)}')
sz = os.path.getsize(db_path)
print(f'DB size: {sz} bytes ({sz/1024:.1f} KB)')
if sz == 0:
    print("CRITICAL: Database file is EMPTY (0 bytes) — schema may be gone!")
    exit(1)
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print(f'\nTotal tables: {len(tables)}')
print('=' * 100)
for tname in tables:
    cur.execute(f'PRAGMA table_info("{tname}")')
    cols = cur.fetchall()
    cur.execute(f'SELECT COUNT(*) FROM "{tname}"')
    cnt = cur.fetchone()[0]
    print(f'\nTable: {tname}  (rows: {cnt})')
    print(f'  {"Column":25} {"Type":15} {"Nullable":10} {"PK":5} {"Default":15}')
    print(f'  {"-"*70}')
    for cid, name, ctype, notnull, default, pk in cols:
        nn = "NOT NULL" if notnull else "NULLABLE"
        print(f'  {name:25} {ctype:15} {nn:10} {pk:5} {str(default):15}')
    cur.execute(f'PRAGMA foreign_key_list("{tname}")')
    fks = cur.fetchall()
    if fks:
        print(f'  Foreign Keys:')
        for fk in fks:
            print(f'    {fk[3]} -> {fk[2]}.{fk[4]}')
    print()
conn.close()
