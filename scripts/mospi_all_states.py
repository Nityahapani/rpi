"""Official MoSPI CPI (base 2024) item indices for every state/UT, urban sector, calendar 2025, for the basket's food items.
Used only to estimate wholesale->retail pass-through from the pooled panel (scripts/passthrough_pooled.py); Gujarat is held out there.
Run: PYTHONPATH=. python3 scripts/mospi_all_states.py   (about 10-15 minutes; 4 threads, same endpoint and paging as rpi/collectors/mospi_cpi.py)"""
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from rpi.http_compat import session
BASE = "https://api.mospi.gov.in/api/cpi/getCPIData"
CODES = {"01.1.1.2.1.01": "Wheat atta", "01.1.7.6.1.01": "Tur", "01.1.7.6.1.02": "Moong", "01.1.7.6.1.05": "Gram split", "01.1.7.5.1.01": "Potato",
         "01.1.7.4.1.01": "Onion", "01.1.7.2.1.01": "Tomato", "01.1.7.2.1.03": "Brinjal", "01.1.1.1.1.01": "Rice", "01.1.8.1.1.01": "Sugar",
         "01.1.4.8.1.01": "Eggs", "01.1.6.1.1.01": "Banana", "01.1.8.1.1.02": "Jaggery"}


def one(sc):
    s = session(); rows = []; page = 1; tp = 1
    while page <= tp:
        for attempt in range(4):
            try:
                r = s.get(BASE, params=dict(base_year="2024", series="Current", year="2025", state_code=sc, sector_code=2, limit=100, page=page), timeout=90)
                j = r.json(); break
            except Exception:
                time.sleep(3)
        else:
            print("FAIL", sc, page, flush=True); return rows
        if "data" not in j: return rows
        tp = j["meta_data"]["totalPages"]
        rows += [x for x in j["data"] if x.get("code") in CODES and x.get("item")]
        page += 1; time.sleep(0.2)
    print("state", sc, len(rows), flush=True); return rows


if __name__ == "__main__":
    with ThreadPoolExecutor(4) as ex: res = list(ex.map(one, range(1, 38)))
    d = pd.DataFrame([x for r in res for x in r])
    d["period"] = pd.to_datetime(d["year"].astype(str) + "-" + d["month"], format="%Y-%B").dt.to_period("M").astype(str)
    d["index_value"] = pd.to_numeric(d["index"], errors="coerce")
    d[["state", "period", "code", "index_value", "imputation"]].to_csv("data/official/mospi_states_food_items_2025.csv", index=False)
    print(d.state.nunique(), "states", len(d), "rows")
