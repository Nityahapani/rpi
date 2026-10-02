"""Geography screen for the DoCA retail feed: for every basket commodity, gate THREE panels against the official Gujarat-urban item index with
the unchanged gate (rpi.proxy_check.judge): Rajkot centre, Gujarat centres (balanced panel), all-India centres (balanced panel).
Wiring rule (fixed beforehand): the most local panel that passes wins.  Output: data/official/doca_panel_screen.csv.
(An earlier draft of this screen used the API's default 400-day window and wrongly reported 2 of 20 passes for the Gujarat panel.)"""
import numpy as np, pandas as pd, requests
from rpi.collectors.doca import WIRED, CANDIDATES, NATIONAL_WIRED, NATIONAL_CANDIDATES, MIRROR, CENTRE_ID, SERIES_LIMIT, parse_mapseries, panel_level, parse_history
from rpi.proxy_check import judge

meta = requests.get(MIRROR + "/api/meta", timeout=30).json()
gujarat = [str(c["id"]) for c in meta["centres"] if c["state"] == "Gujarat"]
mp = pd.read_csv("data/basket_official_map.csv", dtype=str, keep_default_na=False).set_index("item_id")
off = pd.read_csv("data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
off = off[off.level == "item"].pivot_table(index="period", columns="code", values="index_value", aggfunc="first")
items = {**{k: v[0] for k, v in WIRED.items()}, **{k: v[0] for k, v in NATIONAL_WIRED.items()}, **CANDIDATES, **NATIONAL_CANDIDATES}


def monthly(s):
    m = s.groupby(s.index.to_period("M")).mean()
    m.index = m.index.astype(str)
    return m


rows = []
for cid, item in items.items():
    df = parse_mapseries(requests.get(f"{MIRROR}/api/mapseries?commodity={cid}&start=2025-01-01&end=2026-10-02&limit={SERIES_LIMIT}", timeout=120).text)
    o = off[mp.loc[item, "official_item_code"]].dropna()
    r = {"item_id": item, "doca_commodity": cid, "last_day": str(df.index.max().date())}
    rk = requests.get(f"{MIRROR}/api/centre/{CENTRE_ID}/history?commodity={cid}&start=2025-01-01&end=2026-10-02", timeout=60).text
    rajkot = pd.Series({pd.Timestamp(d): p for d, p in parse_history(rk)})      # exactly what the wired Rajkot feed ingests
    for name, lvl in (("rajkot", rajkot), ("gujarat", panel_level(df, gujarat)), ("india", panel_level(df))):
        j = judge(monthly(lvl), o)
        r.update({f"{name}_corr": j["corr"], f"{name}_drift": j["drift"], f"{name}_verdict": j["verdict"]})
    r["wire_to"] = next((n for n in ("rajkot", "gujarat", "india") if r[f"{n}_verdict"] == "pass"), "none")
    rows.append(r)
out = pd.DataFrame(rows)
out.to_csv("data/official/doca_panel_screen.csv", index=False)
print(out.to_string())
