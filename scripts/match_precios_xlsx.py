"""Dry-run: match names in inventario.xlsx against Product.name for company 2."""
import sqlite3
import unicodedata
import re
from difflib import SequenceMatcher
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
cur.execute("SELECT id, name, cost_price, selling_price FROM product WHERE company_id=? AND active=1", (COMPANY_ID,))
rows = cur.fetchall()
products = [(pid, name, cp, sp, norm(name)) for pid, name, cp, sp, in [(r[0], r[1], r[2], r[3]) for r in rows]]

exact = 0
fuzzy = 0
missing = []
collisions = []

for _, row in df.iterrows():
    xlsx_name = row['nombre']
    price = row['precio']
    target = norm(xlsx_name)

    exact_hits = [p for p in products if p[4] == target]
    if len(exact_hits) == 1:
        exact += 1
        continue
    if len(exact_hits) > 1:
        collisions.append((xlsx_name, [(p[0], p[1]) for p in exact_hits]))
        continue

    best = None
    best_ratio = 0
    for p in products:
        r = SequenceMatcher(None, target, p[4]).ratio()
        if r > best_ratio:
            best_ratio = r
            best = p
    if best_ratio >= 0.85:
        fuzzy += 1
    else:
        missing.append((xlsx_name, best[1] if best else None, round(best_ratio, 2)))

print(f'Total xlsx rows: {len(df)}')
print(f'Exact matches:   {exact}')
print(f'Fuzzy >=0.85:    {fuzzy}')
print(f'Collisions:      {len(collisions)}')
print(f'No good match:   {len(missing)}')
print()
print('--- Collisions (same normalized name, multiple products) ---')
for name, hits in collisions[:10]:
    print(f'  {name!r} -> {hits}')
print()
print('--- First 15 unmatched (xlsx name / closest product / ratio) ---')
for x, best, r in missing[:15]:
    print(f'  [{r}] {x!r}')
    print(f'        -> {best!r}')
