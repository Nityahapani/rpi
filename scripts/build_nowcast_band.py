"""90% nowcast band from 11 years of pseudo-real-time errors of the seasonal-trend rule (no independent information used: conservative).
Index-level error = basket-weighted mean of the item errors of rule SEASC (data/official/panel_nowcast_errors.csv, origins 2018-01..2025-10, n=79/78).
Split-conformal quantile k=ceil((n+1)(1-alpha)).  Validity check: the quantile built on origins <= 2022-12 is scored on the untouched origins >= 2023-01.
Run: PYTHONPATH=. python3 scripts/build_nowcast_band.py -> data/official/nowcast_band_history.json"""
import json, math, numpy as np, pandas as pd
R = pd.read_csv("data/official/panel_nowcast_errors.csv")
mp = pd.read_csv("data/official/basket_to_cpi2012_map.csv", dtype=str)
w = pd.read_csv("data/official/weights_item_detail.csv").set_index("item_id")["weight"].astype(float); mp["w"] = mp.item_id.map(w)
ALPHA = 0.10; out = {"alpha": ALPHA, "rule": "seasonal_trend (SEASC), 2018-2025 rolling-origin on official Gujarat-urban base-2012 item data; independent items add no information (conservative)"}
def q(e):
    e = np.sort(np.abs(e)); n = len(e); k = math.ceil((n + 1) * (1 - ALPHA)); return float(e[min(k, n) - 1]), n, k <= n
for h in (1, 2):
    rows = []
    for o, g in R[R.h == h].groupby("op"):
        e = g.set_index("line"); m = mp[mp.cpi2012_item.isin(e.index)]; ww = m.w.values / m.w.sum()
        rows.append(dict(op=o, test=bool(g.test.iloc[0]), err=float((ww * e.loc[m.cpi2012_item, "e_SEASC"].values).sum()),
                         old=float((ww * e.loc[m.cpi2012_item, "e_T12"].values).sum())))
    E = pd.DataFrame(rows)
    qa, n, valid = q(E.err.values); qs, ns, vs = q(E[~E.test].err.values); qo, _, _ = q(E.old.values)
    cov_test = float((E[E.test].err.abs() <= qs).mean())
    out[f"h{h}_abs_log"] = round(qa, 5); out[f"h{h}_n"] = n; out[f"h{h}_valid"] = bool(valid)
    out[f"h{h}_check"] = dict(q_select_only=round(qs, 5), n_select=ns, coverage_on_untouched_test=round(cov_test, 3), n_test=int(E.test.sum()), old_rule_q_all=round(qo, 5))
json.dump(out, open("data/official/nowcast_band_history.json", "w"), indent=1); print(json.dumps(out, indent=1))
