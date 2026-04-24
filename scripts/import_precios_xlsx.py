"""Import cost_price from inventario.xlsx into Product table for company 2."""
import sqlite3
import unicodedata
import re
import pandas as pd

COMPANY_ID = 2
XLSX = 'inventario.xlsx'
DB = 'instance/sat_app.db'


def norm(s):
    if not s:
        return ''
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(s.split())


df = pd.read_excel(XLSX)
df.columns = [c.strip().lower() for c in df.columns]

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, cost_price FROM product WHERE company_id=? AND active=1", (COMPANY_ID,))
by_norm = {}
for pid, name, cp in cur.fetchall():
    by_norm.setdefault(norm(name), []).append((pid, name, cp))

updates = []
skipped = []
for _, row in df.iterrows():
    xlsx_name = row['nombre']
    price = row['precio']
    if pd.isna(price):
        skipped.append((xlsx_name, 'precio vacío'))
        continue
    hits = by_norm.get(norm(xlsx_name), [])
    if len(hits) != 1:
        skipped.append((xlsx_name, f'{len(hits)} matches'))
        continue
    pid, name, old_cp = hits[0]
    updates.append((pid, name, old_cp, float(price)))

print(f'Will update {len(updates)} rows; skipped {len(skipped)}.')
for xn, reason in skipped:
    print(f'  SKIP [{reason}] {xn!r}')

cur.executemany("UPDATE product SET cost_price=? WHERE id=?",
                [(new, pid) for pid, _, _, new in updates])
conn.commit()
print(f'Committed {cur.rowcount if cur.rowcount != -1 else len(updates)} updates.')
conn.close()
