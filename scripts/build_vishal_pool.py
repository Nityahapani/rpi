"""Fix the Vishal Mega Mart diary pool (data/vishal/pool.csv) from the live category pages.
Rules (fixed before any diary price exists): C001 = first 8 products of casual-shirts and first 8 of formal-shirts; C002 = first 12 products of jeans; C003 = first 8 of sandals and first 8 of slippers;
'first' = default listing order of page 1 (12 products per page); price > 0.  Stock status is NOT a criterion: without a pincode every product page reports OutOfStock
(availability is store-specific), while the price is shown.
The pool is never changed silently: replacing a product is a dated, committed edit.  Run: PYTHONPATH=. python3 scripts/build_vishal_pool.py"""
import datetime as dt, time, requests, pandas as pd
from rpi.collectors.vishal_diary import parse_itemlist, parse_product
S = requests.Session(); S.headers["User-Agent"] = "RajkotPriceIndex/0.1 (research; contact: you@example.com)"
B = "https://www.vishalmegamart.com/en-in/mens-fashion/"
SPEC = [("C001", "topwear/casual-shirts", 8), ("C001", "topwear/formal-shirts", 8), ("C002", "bottomwear/jeans", 12), ("C003", "footwear/sandals", 8), ("C003", "footwear/slippers", 8)]
rows = []
for item, cat, n in SPEC:
    urls = parse_itemlist(S.get(B + cat + "/", timeout=40).text); time.sleep(2); k = 0
    for u in urls:
        got = parse_product(S.get(u, timeout=40).text); time.sleep(2)
        if got:
            rows.append(dict(item_id=item, category=cat, url=u, price_at_selection=got[0], selected_on=dt.date.today().isoformat())); k += 1
        if k >= n: break
    print(item, cat, k, "of", len(urls), "listed", flush=True)
pd.DataFrame(rows).to_csv("data/vishal/pool.csv", index=False); print(len(rows), "products")
