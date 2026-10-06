"""Official MoSPI CPI base-2012 item indices, Gujarat urban, 2013-2025 (Back + Current series).
Purpose: a ~11-year history of the same kinds of items (rent, clothing, fees, fares...) so that nowcast methods
for items WITHOUT an independent source can be back-tested on far more than 19 months.
Output: data/official/mospi_cpi2012_gujarat_urban_items.csv (period,item,index_value,status). Run: PYTHONPATH=. python3 scripts/mospi_2012_items_gujarat.py"""
import time, pandas as pd
from concurrent.futures import ThreadPoolExecutor
from rpi.http_compat import session
B = "https://api.mospi.gov.in/api/cpi/getCPIData"

def one(args):
    ser, yr = args
    s = session(); rows = []; page = 1; tp = 1
    while page <= tp:
        for _ in range(5):
            try:
                r = s.get(B, params=dict(base_year="2012", series=ser, year=yr, state_code=10, sector_code=2, limit=100, page=page, level="Item"), timeout=90)
                j = r.json(); break
            except Exception: time.sleep(3)
        else: print("FAIL", ser, yr, page, flush=True); return rows
        if not j.get("data"): break
        tp = j.get("meta_data", {}).get("totalPages", 1)
        rows += j["data"]; page += 1; time.sleep(0.2)
    print(ser, yr, len(rows), flush=True); return rows

if __name__ == "__main__":
    jobs = [("Back", y) for y in range(2013, 2021)] + [("Current", y) for y in range(2017, 2026)]
    with ThreadPoolExecutor(4) as ex: res = list(ex.map(one, jobs))
    d = pd.DataFrame([dict(x, series=j[0]) for r, j in zip(res, jobs) for x in r])
    d["period"] = pd.to_datetime(d["year"].astype(str) + "-" + d["month"], format="%Y-%B").dt.to_period("M").astype(str)
    d["index_value"] = pd.to_numeric(d["index"], errors="coerce")
    d = d.sort_values(["series", "item", "period"])
    d[["series", "period", "item", "index_value", "inflation", "status"]].to_csv("data/official/mospi_cpi2012_gujarat_urban_items.csv", index=False)
    print(len(d), d.period.min(), d.period.max(), d.item.nunique())
