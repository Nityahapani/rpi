"""Independent cross-check of F020 (eggs): DoCA all-India retail panel (wired) vs NECC Ahmedabad daily suggested rate (primary publisher
e2necc.com, full history since 2009 via the civic archive eggs.reclaimchennai.city/data/egg_prices_daily.csv).

CORROBORATION ONLY: NECC Ahmedabad is a wholesale, single-zone series and is NOT fed to the index. One-off fetch + CSV; not part of refresh.
Run:  PYTHONPATH=. python3 scripts/crosscheck_eggs_necc.py
"""
import io, sqlite3
import numpy as np, pandas as pd, requests
from rpi.proxy_check import judge

URL = "https://eggs.reclaimchennai.city/data/egg_prices_daily.csv"
raw = pd.read_csv(io.StringIO(requests.get(URL, timeout=120).text), parse_dates=["date"])
a = raw[(raw.zone == "Ahmedabad") & (raw.series == "NECC Suggested")].set_index("date").price_inr
necc = a.resample("MS").mean(); necc.index = necc.index.strftime("%Y-%m")
c = sqlite3.connect("data/rpi.sqlite")
q = pd.read_sql_query("SELECT substr(o.obs_date,1,7) m, AVG(o.unit_price) v FROM observations o JOIN products p ON p.sku_id=o.sku_id "
                      "WHERE p.item_id='F020' AND p.source_id='doca_national' GROUP BY 1", c).set_index("m").v
off = pd.read_csv("data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
off = off[(off.level == "item") & (off.code == "01.1.4.8.1.01")].set_index("period").index_value
rows = []
for name, s in (("DoCA national retail (wired)", q), ("NECC Ahmedabad wholesale (not wired)", necc)):
    j = judge(s, off); rows.append({"series": name, "vs": "official Gujarat-urban eggs index", **j})
both = pd.concat([q.rename("d"), necc.rename("n")], axis=1).dropna()
both = both[both.index <= "2026-08"]
j = judge(both.d, both.n); rows.append({"series": "DoCA national vs NECC Ahmedabad", "vs": "each other", **j})
out = pd.DataFrame(rows); out.to_csv("data/official/egg_crosscheck.csv", index=False)
print(out.to_string()); print("daily NECC Ahmedabad rows", len(a), a.index.min().date(), a.index.max().date())
