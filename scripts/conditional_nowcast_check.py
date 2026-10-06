"""Pseudo-real-time test: does CONDITIONING the unobserved items on the observed ones beat the seasonal prior alone?

For every origin month t (2019-01..2025-12) using ONLY data before t: item seasonal prior (rpi/seasonal.py), residual covariance of the
priors' errors (Ledoit-Wolf shrunk, no tuning), then for month t the Gaussian conditional mean of the unobserved items' residuals given the
observed items' residuals.  Observed set = the basket's independent items (optimistic: seen exactly).  Error = weighted log change of the
UNOBSERVED part, aggregated with the production basket weights.  Selection window 2019-2021; untouched test 2022-2025 (rule fixed in advance).
Needs scikit-learn (research script only, not part of the pipeline or CI).
Run: PYTHONPATH=. python3 scripts/conditional_nowcast_check.py
"""
import numpy as np, pandas as pd
from sklearn.covariance import LedoitWolf
from rpi.seasonal import seasonal_table

d = pd.read_csv("data/official/mospi_cpi2012_gujarat_urban_items.csv")
P = d.pivot_table(index="period", columns="item", values="index_value").sort_index(); P.index = pd.PeriodIndex(P.index, freq="M")
P = P.reindex(pd.period_range(P.index.min(), P.index.max(), freq="M")); D = np.log(P.where(P > 0)).diff()
mp = pd.read_csv("data/official/basket_to_cpi2012_map.csv", dtype=str)
plan = pd.read_csv("data/source_plan.csv").set_index("item_id")["class"]
w = pd.read_csv("data/official/weights_item_detail.csv").set_index("item_id")["weight"]
# one column per CPI2012 line; if several basket items share a line their weights add
line_of = dict(zip(mp.item_id, mp.cpi2012_item))
W = w.groupby(line_of).sum() if False else pd.Series({l: w[[i for i in line_of if line_of[i] == l]].sum() for l in set(line_of.values())})
obs_lines = sorted({line_of[i] for i in line_of if plan.get(i) == "independent"})
un_lines = sorted(set(W.index) - set(obs_lines))
lines = obs_lines + un_lines
X = D[lines]
def seas_prior(hist, t):
    out = {}
    for c in hist.columns:
        tb = seasonal_table(hist[c])
        out[c] = tb.loc[t.month, "clim"] + tb.loc[t.month, "seas"]
    return pd.Series(out)
rows = []
for t in pd.period_range("2019-01", "2025-12", freq="M"):
    hist = X.loc[: t - 1].dropna(how="all")
    hist = hist.loc[hist.index >= pd.Period("2014-02", "M")]
    prior = seas_prior(hist, t)
    # in-sample residual panel of the priors (leave nothing out: priors built on the same hist; adequate for covariance structure)
    res = pd.DataFrame({c: hist[c] - np.array([seas_prior_row for seas_prior_row in [0]] * len(hist)) for c in hist.columns}) if False else None
    clim = hist.mean()
    mon = hist.index.month
    seas = pd.DataFrame({c: seasonal_table(hist[c]).seas for c in hist.columns})
    resid = hist - clim - seas.reindex(mon).set_axis(hist.index)
    resid = resid.dropna(thresh=int(0.8 * len(resid.columns)))
    Rf = resid.fillna(0.0)
    S = LedoitWolf().fit(Rf.values).covariance_
    Sd = pd.DataFrame(S, index=lines, columns=lines)
    o, u = obs_lines, un_lines
    e_o = (X.loc[t, o] - prior[o]).fillna(0.0)
    cond = Sd.loc[u, o].values @ np.linalg.solve(Sd.loc[o, o].values, e_o.values)
    pred_prior = prior[u]; pred_cond = prior[u] + cond
    act = X.loc[t, u]
    ok = act.notna()
    wu = W[u][ok] / W[u][ok].sum()
    rows.append(dict(t=str(t), err_prior=float((wu * (pred_prior[ok] - act[ok])).sum()), err_cond=float((wu * (pred_cond[ok] - act[ok])).sum()),
                     err_zero=float((wu * (0 - act[ok])).sum())))
df = pd.DataFrame(rows).set_index("t")
for name, sl in [("selection 2019-2021", slice("2019-01", "2021-12")), ("TEST 2022-2025", slice("2022-01", "2025-12"))]:
    s = df.loc[sl]
    r = {k: float(np.sqrt((s[k] ** 2).mean())) * 100 for k in ["err_zero", "err_prior", "err_cond"]}
    # Diebold-Mariano style paired t on squared errors
    dd = s.err_prior ** 2 - s.err_cond ** 2
    t_stat = dd.mean() / (dd.std(ddof=1) / np.sqrt(len(dd)))
    print(name, "n=%d" % len(s), {k: round(v, 3) for k, v in r.items()}, "paired t(prior^2-cond^2)=%.2f" % t_stat, "cond wins %d/%d" % ((s.err_cond.abs() < s.err_prior.abs()).sum(), len(s)))
df.round(5).to_csv("data/official/conditional_nowcast_test.csv")
print("unobserved lines:", len(un_lines), "observed lines:", len(obs_lines), "unobserved weight share %.1f%%" % (W[un_lines].sum() / W.sum() * 100))
