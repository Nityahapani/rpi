"""Build data/official/seasonal_tables.csv (per basket item: long-run mean monthly change and EB calendar-month deviation, all official history
2014-01..2025-12) and data/official/wholesale_calibration.csv (pooled b0, sigma_wb, sigma_prior for the mandi-fed items, from scripts/yard_calibration.py).
Run after scripts/mospi_2012_items_gujarat.py, scripts/panel_nowcast_rules.py and scripts/yard_calibration.py.
Run: PYTHONPATH=. python3 scripts/build_seasonal_tables.py"""
import json, numpy as np, pandas as pd
from rpi.seasonal import seasonal_table
d = pd.read_csv("data/official/mospi_cpi2012_gujarat_urban_items.csv")
P = d.pivot_table(index="period", columns="item", values="index_value").sort_index(); P.index = pd.PeriodIndex(P.index, freq="M")
P = P.reindex(pd.period_range(P.index.min(), P.index.max(), freq="M")); L = np.log(P.where(P > 0)); D1 = L.diff()
mp = pd.read_csv("data/official/basket_to_cpi2012_map.csv", dtype=str)
rows = []
for r in mp.itertuples():
    t = seasonal_table(D1[r.cpi2012_item])
    for m, x in t.iterrows(): rows.append(dict(item_id=r.item_id, line=r.cpi2012_item, month=m, clim=round(x.clim, 6), seas=round(x.seas, 6), n_years=int(x.n)))
pd.DataFrame(rows).to_csv("data/official/seasonal_tables.csv", index=False)
s = json.load(open("data/official/yard_calibration_summary.json"))["coef"]
item_id = {"Wheat atta": "F001", "Moong": "F004", "Onion": "F022", "Tomato": "F023", "Brinjal": "F025"}   # potato (F021) is fed by DoCA retail, not a wholesale yard
cal = [dict(item_id=item_id[k], b0=v["b0_lag0only"], sigma_wb=v["sigma_wb_lag0only"], sigma_prior=v["sigma_seasc"], basis=k) for k, v in s.items() if k in item_id]
pd.DataFrame(cal).to_csv("data/official/wholesale_calibration.csv", index=False); print(pd.DataFrame(cal))
