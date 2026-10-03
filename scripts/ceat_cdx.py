"""List Wayback captures of CEAT's own two-wheeler tyre pages (JSON-LD Product prices) -> data/ceat/captures.csv.
Selection rule (fixed before any price was parsed): model pages (.../<brand>/<model>-tyres.html) under /bike-tyres/ and /scooter-tyres/ with a 200 capture between 2025-07 and 2026-09;
one capture (the latest) per page per month. (An earlier draft required >= 8 months per page; no page has more than 7, so the rule is per SKU, not per page.)"""
import requests, pandas as pd, collections
S = requests.Session(); S.headers["User-Agent"] = "RajkotPriceIndex/0.1 (research; archive reader)"
rows = []
for pre in ("ceat.com/bike-tyres/*", "ceat.com/scooter-tyres/*"):
    r = S.get("http://web.archive.org/cdx/search/cdx", params=dict(url=pre, output="txt", fl="timestamp,original", filter="statuscode:200", **{"from": "202507", "to": "202610"}), timeout=180)
    rows += [l.split() for l in r.text.splitlines() if l.strip()]
d = pd.DataFrame(rows, columns=["ts", "url"])
d["url"] = d.url.str.split("?").str[0].str.replace("http://", "https://").str.replace("://ceat.com", "://www.ceat.com")
d = d[d.url.str.endswith("-tyres.html") & (d.url.str.count("/") >= 5)]       # model pages: .../bike-tyres/<brand>/<model>-tyres.html
d["month"] = d.ts.str[:6]
print(len(d)); nm = d.groupby("url").month.nunique()
keep = nm.index
d = d.sort_values("ts").groupby(["url", "month"]).tail(1)
d.to_csv("data/ceat/captures.csv", index=False)
print(nm.describe().to_dict()); print(len(keep), "pages", len(d), "captures"); print(d.groupby("month").size().to_dict())
