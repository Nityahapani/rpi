"""CEDA (Agmarknet) monthly modal wholesale price for every DISTRICT of every state, Dec 2024 - Oct 2025, for the basket's food items
(feeds scripts/pooled_accuracy.py, which forms state wholesale changes as matched-district Jevons means).
One request per commodity in the same map mode the site's own choropleth uses (all districts in one response); 2 s spacing.
Run: python3 scripts/ceda_all_states.py"""
import time, requests, pandas as pd
B = "https://agmarknet.ceda.ashoka.edu.in/api/prices"
COM = {1: "Wheat atta", 49: "Tur", 9: "Moong", 6: "Gram split", 24: "Potato", 23: "Onion", 78: "Tomato", 35: "Brinjal", 3: "Rice", 48: "Sugar", 367: "Eggs", 19: "Banana", 74: "Jaggery"}
S = requests.Session(); S.headers["User-Agent"] = "RajkotPriceIndex/0.1 (research; contact: you@example.com)"
rows = []
for cid, name in COM.items():
    for attempt in range(3):
        try:
            r = S.post(B, json=dict(state_id=None, commodity_id=cid, district_id=None, start_date="2024-12-01", end_date="2025-10-31", calculation_type="m", chart_type="map"), timeout=170)
            if r.status_code == 429: time.sleep(60); continue
            if not r.json().get("data"): print("empty response, retry", name, flush=True); time.sleep(10); continue   # the API sometimes answers 200 with no data
            for x in r.json().get("data", []):
                rows.append(dict(item=name, state=x["state"], district_id=x["district_id"], district=x["district"], month=x["t"], modal=x["p_modal"]))
            break
        except Exception as e:
            print("retry", name, str(e)[:50], flush=True); time.sleep(5)
    print(name, len(rows), flush=True); time.sleep(2)
pd.DataFrame(rows).to_csv("data/ceda/district_monthly_modal.csv", index=False); print("done", len(rows))
