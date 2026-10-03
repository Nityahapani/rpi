"""Fix the CEAT tyre SKU pool and the minimal page list that covers it.  Rule (fixed before any live quote exists): SKUs with a listed price (> 0) in
>= 6 distinct months of the Wayback history (data/ceat/sku_prices.csv); pages chosen greedily by coverage until every pool SKU is covered.
Output: data/ceat/pool.csv (sku, name, page).  Run: python3 scripts/build_ceat_pool.py"""
import pandas as pd
d = pd.read_csv("data/ceat/sku_prices.csv", dtype={"ts": str, "sku": str})
d = d[d.price > 0].copy(); d["m"] = d.ts.str[:6]
nm = d.groupby("sku").m.nunique()
pool = set(nm[nm >= 6].index)
sub = d[d.sku.isin(pool)]
cov = sub.groupby("url").sku.agg(lambda s: set(s))
left, pages = set(pool), []
while left:
    u = max(cov.index, key=lambda k: (len(cov[k] & left), k))
    pages.append(u); left -= cov[u]
names = sub.groupby("sku").name.first()
first = {s: next(p for p in pages if s in cov[p]) for s in pool}
out = pd.DataFrame([dict(sku=s, name=names[s], page=first[s]) for s in sorted(pool)])
out.to_csv("data/ceat/pool.csv", index=False)
print(len(pool), "SKUs on", len(pages), "pages")
