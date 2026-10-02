"""Amul (GCMMF) Gujarat pouch-milk price steps -> F009 events (Amul Gold 500 ml, Rs per pouch). Idempotent.

Sources: Indian Express 30 Apr 2025 (Rs2/L hike effective Thu 1 May 2025; Gold 500 ml = Rs34);
The News Mill 14 May 2026 (Rs2/L from 14 May 2026; Gold 500 ml = Rs35; GCMMF press release quoted).
The pre-May-2025 price (Rs33) is DERIVED: new price minus the stated Rs2/L (= Rs1 per 500 ml).
Cross-check: official Gujarat-urban 'Milk: liquid' index steps +1.6% (May 2025), +1.1% (May 2026), +1.4% (Jun 2026).
"""
import datetime as dt
import pandas as pd

P = "data/tariff_events.csv"
ROWS = [
    ("2025-01-01", 33.0, "derived", "press (derived)", "https://indianexpress.com/article/cities/ahmedabad/amul-milk-prices-up-by-rs-2-per-litre-gcmmf-says-lower-than-average-food-inflation-9975619/",
     "Amul Gold 500ml before the May 2025 hike = 34 - 1 (Rs2/L hike stated by GCMMF)"),
    ("2025-05-01", 34.0, "verified", "press (GCMMF release quoted by 2+ outlets)", "https://indianexpress.com/article/cities/ahmedabad/amul-milk-prices-up-by-rs-2-per-litre-gcmmf-says-lower-than-average-food-inflation-9975619/",
     "Amul Gold 500ml Gujarat after Rs2/L hike effective 1 May 2025"),
    ("2026-05-14", 35.0, "verified", "press (GCMMF release quoted)", "https://thenewsmill.com/2026/05/amul-raises-milk-prices-by-%E2%82%B92-per-litre-affecting-vadodara-households/",
     "Amul Gold 500ml Gujarat after Rs2/L hike effective 14 May 2026"),
]
ev = pd.read_csv(P)
have = set(zip(ev.item_id, ev.effective_from.astype(str)))
new = [dict(item_id="F009", effective_from=d, price=p, status=s, source_class=c, source_url=u,
            retrieved=dt.date.today().isoformat(), note=n) for d, p, s, c, u, n in ROWS if ("F009", d) not in have]
if new:
    pd.concat([ev, pd.DataFrame(new)], ignore_index=True).to_csv(P, index=False)
print(f"F009: +{len(new)} event(s)")
