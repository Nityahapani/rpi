"""DoCA retail balanced-panel Jevons level per STATE (centres of that state with a quote on every day), monthly mean, Jan-Oct 2025, for the basket's food items.
Same open mirror and the same balanced-panel rule as rpi/collectors/doca.py (panel_level, >= 5 centres).  Feeds the pooled accuracy tests.
Run: PYTHONPATH=. python3 scripts/doca_state_panels.py"""
import json, time, pandas as pd
from rpi.http_compat import session
from rpi.collectors.doca import MIRROR, parse_mapseries, panel_level, SERIES_LIMIT
COM = {4: "Wheat atta", 11: "Tur", 13: "Moong", 10: "Gram split", 22: "Potato", 23: "Onion", 24: "Tomato", 25: "Brinjal", 36: "Eggs", 41: "Banana", 1: "Rice"}
s = session()
meta = json.loads(s.get(f"{MIRROR}/api/meta", timeout=90).text)
by_state = {}
for c in meta["centres"]: by_state.setdefault(c.get("state"), []).append(str(c["id"]))
rows = []
for cid, name in COM.items():
    r = s.get(f"{MIRROR}/api/mapseries?commodity={cid}&start=2025-01-01&end=2025-10-31&limit={SERIES_LIMIT}", timeout=180)
    df = parse_mapseries(r.text)
    for st, ids in by_state.items():
        try: lvl = panel_level(df, ids)
        except ValueError: continue
        m = lvl.groupby(lvl.index.to_period("M")).mean()
        for p, v in m.items(): rows.append(dict(state=st, item=name, month=str(p), level=float(v), n_centres=int(df[[i for i in ids if i in df.columns]].dropna(axis=1).shape[1])))
    print(name, len(rows), flush=True); time.sleep(1)
pd.DataFrame(rows).to_csv("data/doca/state_panel_monthly.csv", index=False); print("done", len(rows))
