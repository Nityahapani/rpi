"""Pseudo-real-time test of PANEL nowcast rules (seasonality + mean reversion, pooled over items) against the engine's own 12-month drift.
Data: official Gujarat-urban base-2012 item indices 2014-2025 (66 basket items mapped via basket_to_cpi2012_map.csv).
Everything is pooled and standardised, nothing is fitted per item, and every fit at origin t uses only pairs whose target month <= t.
Rules (fixed in advance):
  T12      engine: y_t + h*mean(last 12 monthly log changes)
  SEASC    like SEAS but the trend is the item's long-run mean monthly change (all history to t) instead of the last 12 months
  SEAS     T12 + sum of EB-shrunk calendar-month deviations (mean over past years of d_m minus that year's mean change), shrink factor 1/(1+sigma2/(n*tau2))
  MR       T12 - kappa*(y_t - mean(y_{t-11..t}))                 kappa from pooled OLS
  PANEL    ridge (alpha=1) on standardised [h*T12, seasonal term, deviation from 12m mean, last change], pooled within a volatility group
           (group = trailing-36m sd of monthly log change >= 3% -> 'high', else 'low'; the cut is generic, not item names)
  ENS      mean(T12, PANEL)
Selection origins 2018-01..2022-12, untouched test origins 2023-01..2025-10. Run: PYTHONPATH=. python3 scripts/panel_nowcast_rules.py"""
import json, numpy as np, pandas as pd
d = pd.read_csv("data/official/mospi_cpi2012_gujarat_urban_items.csv")
P = d.pivot_table(index="period", columns="item", values="index_value").sort_index()
P.index = pd.PeriodIndex(P.index, freq="M"); P = P.reindex(pd.period_range(P.index.min(), P.index.max(), freq="M"))
L = np.log(P.where(P > 0)); D1 = L.diff()
mp = pd.read_csv("data/official/basket_to_cpi2012_map.csv", dtype=str)
w = pd.read_csv("data/official/weights_item_detail.csv").set_index("item_id")["weight"].astype(float)
plan = pd.read_csv("data/source_plan.csv", dtype=str, keep_default_na=False).set_index("item_id")["class"]
mp = mp[mp.item_id.isin(w.index)]
lines = sorted(mp.cpi2012_item.unique())
H = (1, 2); T = list(L.index); pos = {p: i for i, p in enumerate(T)}
FIRST = pd.Period("2018-01"); LAST = pd.Period("2025-12"); SPLIT = pd.Period("2023-01")

def seas_term(col, t, targets):
    """EB-shrunk calendar-month deviation, from data up to t only."""
    s = D1[col].loc[:t]
    df = pd.DataFrame({"d": s, "m": [p.month for p in s.index], "y": [p.year for p in s.index]}).dropna()
    df = df[df.y >= df.y.min()]
    df["dev"] = df.d - df.groupby("y").d.transform("mean")
    g = df.groupby("m").dev.agg(["mean", "count", "var"])
    tau2 = max(float(g["mean"].var(ddof=1)) - float((g["var"] / g["count"]).mean()), 1e-8) if len(g) > 3 else 1e-8
    out = 0.0
    for m in targets:
        if m in g.index and g.loc[m, "count"] >= 3:
            sh = tau2 / (tau2 + g.loc[m, "var"] / g.loc[m, "count"])
            out += sh * g.loc[m, "mean"]
    return out

rows = []
for t in pd.period_range(FIRST - 0, pd.Period("2025-10"), freq="M"):
    i = pos[t]
    for col in lines:
        y = L[col]
        if pd.isna(y.iloc[i]): continue
        hist = D1[col].iloc[:i + 1].dropna()
        if len(hist) < 36: continue
        t12 = hist.iloc[-12:].mean(); clim = hist.mean(); sd = hist.iloc[-36:].std()
        if not sd > 0: continue
        dev = y.iloc[i] - y.iloc[i - 11:i + 1].mean() if not y.iloc[i - 11:i + 1].isna().any() else np.nan
        last = D1[col].iloc[i]
        for h in H:
            if i + h >= len(T) or pd.isna(y.iloc[i + h]): continue
            tg = [(t + k).month for k in range(1, h + 1)]
            rows.append(dict(line=col, origin=t, h=h, tgt=t + h, sd=sd, t12=t12, clim=clim, seas=seas_term(col, t, tg), dev=dev, last=last, ret=y.iloc[i + h] - y.iloc[i]))
R = pd.DataFrame(rows).dropna(subset=["dev", "last"]); R["grp"] = np.where(R.sd >= 0.03, "high", "low")
for c in ("t12", "seas", "dev", "last", "ret"): R[c + "_z"] = R[c] / R.sd
R["t12h_z"] = R.h * R.t12_z
R["f_T12"] = R.h * R.t12; R["f_SEAS"] = R.f_T12 + R.seas; R["f_SEASC"] = R.h * R.clim + R.seas
R["op"] = R.origin.apply(lambda p: p.ordinal); R["tp"] = R.tgt.apply(lambda p: p.ordinal)
pred = {k: [] for k in ("MR", "PANEL")}
R["f_MR"] = np.nan; R["f_PANEL"] = np.nan
for (h, o), g in R.groupby(["h", "op"]):
    tr = R[(R.h == h) & (R.tp <= o)]
    for grp in ("high", "low"):
        a = tr[tr.grp == grp]; idx = g.index[g.grp == grp]
        if len(a) < 150 or len(idx) == 0: R.loc[idx, "f_MR"] = R.loc[idx, "f_T12"]; R.loc[idx, "f_PANEL"] = R.loc[idx, "f_T12"]; continue
        # MR: ret_z - h*t12_z = -kappa*dev_z
        x = a.dev_z.values; yv = (a.ret_z - a.t12h_z).values; kappa = -float(x @ yv / (x @ x))
        R.loc[idx, "f_MR"] = R.loc[idx, "f_T12"] - kappa * R.loc[idx, "dev_z"] * R.loc[idx, "sd"]
        X = a[["t12h_z", "seas_z", "dev_z", "last_z"]].values; Y = a.ret_z.values
        beta = np.linalg.solve(X.T @ X + 1.0 * np.eye(4), X.T @ Y)
        R.loc[idx, "f_PANEL"] = (R.loc[idx, ["t12h_z", "seas_z", "dev_z", "last_z"]].values @ beta) * R.loc[idx, "sd"].values
R["f_ENS"] = 0.5 * (R.f_T12 + R.f_PANEL)
RULES = ["T12", "SEAS", "SEASC", "MR", "PANEL", "ENS"]
for r in RULES: R["e_" + r] = R["f_" + r] - R.ret
R["test"] = R.origin >= SPLIT
R.drop(columns=["origin", "tgt"]).to_csv("data/official/panel_nowcast_errors.csv", index=False)
# --- item-level -> index-level ---------------------------------------------------------------------------------------------------
res = {}
mpw = mp.assign(w=mp.item_id.map(w), cls=mp.item_id.map(plan))
for h in H:
    for nm, sel in (("select", ~R.test), ("test", R.test)):
        S = R[(R.h == h) & sel]
        rows2 = []
        for o, g in S.groupby("op"):
            e = g.set_index("line")
            m = mpw[mpw.cpi2012_item.isin(e.index)]
            ww = m.w.values / m.w.sum()
            r = {"op": o}
            for rule in RULES:
                ev = e.loc[m.cpi2012_item, "e_" + rule].values
                r[rule] = float((ww * ev).sum())
                hi = e.loc[m.cpi2012_item, "grp"].values == "high"
                r[rule + "_high"] = float((ww * ev * hi).sum()); r[rule + "_low"] = float((ww * ev * ~hi).sum())
            rows2.append(r)
        Q = pd.DataFrame(rows2)
        res[f"h{h}_{nm}_n{len(Q)}"] = {k: round(100 * float(np.sqrt((Q[k] ** 2).mean())), 4) for k in Q.columns if k != "op"}
json.dump(res, open("data/official/panel_nowcast_summary.json", "w"), indent=1)
print(json.dumps(res, indent=1))
