"""Information coverage: share of the index's NO-INFORMATION nowcast-error variance that sits in items with an independent source.
Weight coverage (56.4%) counts how much of the basket has an independent price; it ignores that items differ hugely in how much they MOVE.
Baseline rule = engine's own-trend (T12). Errors from `linked_nowcast_errors.csv` (official Gujarat-urban base-2012 item series, 2016-2025).
Item share_i = w_i * Cov(e_i, E) / Var(E)   (additive, sums to 1).  Reduction if item i's independent source had skill q_i:  share_i * q_i.
Scenarios (stated, not tuned): upper = q=1 for all covered items (sources equal the official item);
  gate-based = q = gate corr^2 for items with a passing gate (docs/data/status.json), q=1 for administered/tariff items (exact by construction),
               q=0 for pending items (no evidence yet);
  pending-at-0.5 = as gate-based but pending items assumed q=0.5.
Run: PYTHONPATH=. python3 scripts/information_coverage.py -> data/official/information_coverage.json"""
import json, numpy as np, pandas as pd
D = pd.read_csv("data/official/linked_nowcast_errors.csv"); D = D[D.e_T12.notna()]
plan = pd.read_csv("data/source_plan.csv", dtype=str, keep_default_na=False).set_index("item_id")
pv = {r["item_id"]: r for r in json.load(open("docs/data/status.json"))["proxy_validation"]}
def q_item(i, pend):
    src = plan.loc[i, "primary_source"]
    if i in pv:
        r = pv[i]
        return (r["corr"] ** 2 if r["verdict"] == "pass" else (0.0 if r["verdict"] == "pending" else 0.0)) if r["verdict"] != "pending" else pend
    return 1.0                                   # tariff / administered / benchmark price: equals the official item by construction
out = {}
for h in (1, 2):
    piv = D[D.h == h].pivot_table(index="origin", columns="item_id", values="e_T12")
    w = D[D.h == h].groupby("item_id").w.first().reindex(piv.columns)
    X = piv.copy()
    # items present in every origin only (all but a few) - renormalise weights
    ok = X.columns[X.notna().mean() > 0.95]; X = X[ok].dropna(); ww = w[ok] / w[ok].sum()
    E = (X * ww).sum(axis=1); v = np.var(E, ddof=1)
    share = pd.Series({i: ww[i] * np.cov(X[i], E)[0, 1] / v for i in ok})
    cls = plan.loc[ok, "class"]
    indep = cls == "independent"
    r = dict(n_origins=len(X), n_items=len(ok), weight_independent=float(ww[indep].sum()), share_independent=float(share[indep].sum()), share_unobserved=float(share[~indep].sum()))
    for nm, pend in (("gate_based_pending0", 0.0), ("gate_based_pending0.5", 0.5)):
        q = pd.Series({i: (q_item(i, pend) if indep[i] else 0.0) for i in ok})
        r[nm] = float((share * q).sum())
    r["top_unobserved"] = {k: round(float(v), 4) for k, v in share[~indep].sort_values(ascending=False).head(5).items()}
    r["top_independent"] = {k: round(float(v), 4) for k, v in share[indep].sort_values(ascending=False).head(8).items()}
    r["items_excluded"] = [i for i in w.index if i not in ok]
    out[f"h{h}"] = r
json.dump(out, open("data/official/information_coverage.json", "w"), indent=1)
print(json.dumps(out, indent=1))
