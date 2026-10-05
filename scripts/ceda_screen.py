"""CEDA (Ashoka University) cleaned Agmarknet price history as a back-test of the wholesale-mandi proxy type for F021-F026 and the pulse/wheat items F001, F003-F005.
Source: agmarknet.ceda.ashoka.edu.in public JSON API (the same endpoint the site's own charts use; monthly mode, no bulk-download endpoint, one request per
commodity x geography, 1 s spacing).  The API's data END in 2025-10 (checked 2026-10-04), so this is a historical validation, not a live feed.
Rule fixed before any result was seen: monthly modal price (mean of daily district/state means, as served), geography hierarchy Rajkot district -> Gujarat state ->
all India, the most local geography that passes the unchanged gate (rpi.proxy_check.judge: >= 6 overlapping months, corr >= 0.5, drift <= 0.10) is reported.
Run: PYTHONPATH=. python3 scripts/ceda_screen.py"""
import time, requests, pandas as pd
from rpi.proxy_check import judge
B = "https://agmarknet.ceda.ashoka.edu.in/api/prices"
ITEMS = {"F021": (24, "01.1.7.5.1.01", "Potato"), "F022": (23, "01.1.7.4.1.01", "Onion"), "F023": (78, "01.1.7.2.1.01", "Tomato"),
         "F025": (35, "01.1.7.2.1.03", "Brinjal"), "F024": (19, "01.1.6.1.1.01", "Banana"), "F026": (74, "01.1.8.1.1.02", "Jaggery"),
         "F001": (1, "01.1.1.2.1.01", "Wheat (atta)"), "F004": (9, "01.1.7.6.1.02", "Moong"), "F003": (49, "01.1.7.6.1.01", "Tur"), "F005": (6, "01.1.7.6.1.05", "Gram")}
GEO = {"rajkot_district": (24, 476), "gujarat": (24, None), "india": (None, None)}
S = requests.Session(); S.headers["User-Agent"] = "RajkotPriceIndex/0.1 (research; contact: you@example.com)"
off = pd.read_csv("data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
rows, out = [], []
for item, (cid, code, name) in ITEMS.items():
    o = off[(off.level == "item") & (off.code == code)].set_index("period").index_value
    res = {}
    for g, (sid, did) in GEO.items():
        r = S.post(B, json=dict(state_id=sid, commodity_id=cid, district_id=did, start_date="2024-12-01", end_date="2026-10-03", calculation_type="m"), timeout=120)
        time.sleep(1)
        d = pd.DataFrame(r.json().get("data", []))
        if d.empty: res[g] = dict(n_overlap=0, verdict="no data"); continue
        s = d.set_index("t").p_modal.astype(float).sort_index(); s = s[s > 0]
        for t, v in s.items(): rows.append(dict(item_id=item, geo=g, month=t, modal_per_quintal=round(v, 2)))
        res[g] = judge(s, o); res[g]["months"] = f"{s.index.min()}..{s.index.max()}"
    pick = next((g for g in GEO if res[g]["verdict"] == "pass"), "none")
    out.append(dict(item_id=item, item=name, wire_to=pick, **{f"{g}_{k}": res[g].get(k) for g in GEO for k in ("n_overlap", "corr", "drift", "verdict")}))
    print(out[-1], flush=True)
pd.DataFrame(rows).to_csv("data/ceda/monthly_modal.csv", index=False)
pd.DataFrame(out).to_csv("data/official/ceda_screen.csv", index=False)
