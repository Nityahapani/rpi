"""Jockey list-price registers: build the QUARANTINE file, print the gate, optionally promote an item into the index.

  python3 scripts/build_mrp_register.py              # (re)build data/mrp/jockey_events.csv from the archive + today's live prices, print the gate
  python3 scripts/build_mrp_register.py --promote C001   # copy that item's series rows into data/tariff_events.csv (only if its gate verdict is 'pass')

Nothing reaches the index until an item is promoted AND passes rpi.collectors.mrp.gate (the same rule as the mandi / DoCA proxies).
Plan edit needed after promotion: data/source_plan.csv primary_source=tariff, and add the item to PROXY_ITEMS (rpi/proxy_check.py).
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rpi.collectors import mrp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QUAR = ROOT / "data/mrp/jockey_events.csv"
P = ROOT / "data/tariff_events.csv"
today = dt.date.today()
arc = pd.read_csv(ROOT / mrp.ARCHIVE, dtype={"sku": str})
pool = pd.read_csv(ROOT / mrp.POOL, dtype={"sku": str})
live = {r.sku: float(r.live_price) for r in pool.itertuples()}
arc = arc[arc.sku.isin(pool.sku)]
rows = pd.DataFrame(mrp.events_from_archive(arc, today, live)).assign(retrieved=today.isoformat())
if "--promote" in sys.argv:
    item = sys.argv[sys.argv.index("--promote") + 1]
    g = {r["item_id"]: r for r in mrp.gate(rows, ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv", ROOT / "data/basket_official_map.csv", today)}
    if g[item]["verdict"] != "pass":
        sys.exit(f"{item}: gate verdict is {g[item]['verdict']} ({g[item]}); refusing to promote")
    ev = pd.read_csv(P); ev["series"] = ev.series.fillna("")
    q = pd.read_csv(QUAR); q["series"] = q.series.fillna("")
    q = q[q.item_id == item]
    have = set(zip(ev.item_id, ev.series, ev.effective_from.astype(str)))
    q = q[[(a, b, str(c)) not in have for a, b, c in zip(q.item_id, q.series, q.effective_from)]]
    pd.concat([ev, q], ignore_index=True).to_csv(P, index=False)
    sys.exit(print(f"promoted {item}: +{len(q)} event(s) into data/tariff_events.csv"))
if QUAR.exists():          # keep exact-dated live changes the daily updater already appended
    old = pd.read_csv(QUAR)
    keep = old[old.note.astype(str).str.startswith("live price changed")]
    rows = pd.concat([rows, keep], ignore_index=True)
rows.to_csv(QUAR, index=False)
for r in mrp.gate(rows, ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv", ROOT / "data/basket_official_map.csv", today):
    print(r)
print(f"quarantine file: {len(rows)} event rows, {rows.series.nunique()} SKU series")
