"""Gate CEAT's own two-wheeler tyre e-store prices (Wayback captures, data/ceat/sku_prices.csv) against the official 'Tyres and tubes' item index (T006).
Rules fixed before the verdict was seen: SKU-month price = median of that month's captures; price 0 (not listed) excluded; matched-model Jevons chain
(rpi.proxy_check.chain_series); the unchanged gate (rpi.proxy_check.judge); the partial month 2026-09 is dropped because the official index ends in 2026-08.
Output: data/official/ceat_tyre_screen.csv.  Run: PYTHONPATH=. python3 scripts/ceat_screen.py"""
import pandas as pd
from rpi.proxy_check import chain_series, judge

d = pd.read_csv("data/ceat/sku_prices.csv", dtype={"ts": str, "sku": str})
d = d[d.price > 0].copy(); d["m"] = d.ts.str[:4] + "-" + d.ts.str[4:6]
piv = d.groupby(["sku", "m"]).price.median().unstack(0).sort_index()
piv = piv[piv.index <= "2026-08"]
lvl = chain_series(piv)
off = pd.read_csv("data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
o = off[(off.level == "item") & (off.code == "07.2.1.1.1.01")].set_index("period").index_value
j = judge(lvl, o)
out = pd.DataFrame({"ceat_chain": lvl.round(2), "n_skus": piv.notna().sum(axis=1), "official_tyres_rebased": (o.reindex(lvl.index) / o[lvl.index[0]] * 100).round(2)})
out.attrs.update(j)
out.to_csv("data/official/ceat_tyre_screen.csv"); print(out.to_string()); print(j)
