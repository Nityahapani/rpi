"""Vegetable DRIVER test (pre-registered before any model was scored; inventory AK).
Question: do rainfall/heat anomalies (NASA POWER, open), an autoregressive term and a festival-timing term improve one-month-ahead forecasts of the official Gujarat-urban
tomato/onion/potato/brinjal monthly change beyond the engine's seasonal prior (SEAS)?  Those four items carry ~80% of nowcast-error variance (inventory AG).
Fixed in advance: target = 100*dlog of the CPI-2012 Gujarat-urban item index, 2014-02..2025-12; training 2014-02..2021-12, rolling one-step test 2022-01..2025-12 (48 months,
parameters re-estimated on all months before the target; ridge alpha chosen ONCE by blocked 4-fold CV on the training window); weather anomalies are z-scores against the
2012-2021 month-of-year climatology; features: local (Rajkot) precip z lags 0,1,2; source-belt (Nashik, Kolar, Deesa) mean precip z lags 0,1,2; mean Tmax z (Rajkot+belt) lags 0,1;
festival = share of the month inside Navratri-start..Diwali+3 days.  Success rule: a model must beat SEAS on the pooled four-item squared loss with a Diebold-Mariano p < 0.05 (one-sided,
Newey-West, h=1); otherwise it is NOT adopted.  Run: PYTHONPATH=. python3 scripts/veg_driver_test.py"""
import json, datetime as dt
import numpy as np, pandas as pd, holidays
from scipy import stats

ITEMS = {"F021": "Potato", "F022": "Onion", "F023": "Tomato", "F025": "Brinjal"}
TRAIN_END, TEST_START = "2021-12", "2022-01"
KAPPA = 3.0

x = pd.read_csv("data/official/mospi_cpi2012_gujarat_urban_items.csv")
w = pd.read_csv("data/reference/weather_nasa_power_monthly.csv")


def target(item):
    s = x[x.item == item].drop_duplicates("period").set_index("period").index_value.sort_index()
    return (np.log(s).diff() * 100).dropna()


def z_anom(col):
    piv = w.pivot(index="month", columns="loc", values=col)
    clim = piv[(piv.index >= "2012-01") & (piv.index <= "2021-12")]
    mo = clim.groupby(clim.index.str[5:]).agg(["mean", "std"])
    out = piv.copy()
    for c in piv.columns:
        m = piv.index.str[5:]
        out[c] = (piv[c].values - mo[(c, "mean")].reindex(m).values) / mo[(c, "std")].reindex(m).values
    return out


P, T = z_anom("precip_mm_day"), z_anom("tmax")
belt = ["nashik", "kolar", "deesa"]
feat = pd.DataFrame(index=P.index)
for L in (0, 1, 2):
    feat[f"p_loc_l{L}"] = P["rajkot"].shift(L)
    feat[f"p_belt_l{L}"] = P[belt].mean(axis=1).shift(L)
for L in (0, 1):
    feat[f"t_l{L}"] = T[["rajkot"] + belt].mean(axis=1).shift(L)
h = holidays.India(years=range(2012, 2027))
dm = lambda name: sorted(k for k, v in h.items() if name in v)
fest = {}
for y in range(2013, 2026):
    diw = [d for d in dm("Diwali") if d.year == y]
    dus = [d for d in dm("Dussehra") if d.year == y]
    if diw and dus:
        a, b = dus[0] - dt.timedelta(days=9), diw[0] + dt.timedelta(days=3)
        for d in pd.date_range(a, b):
            fest[d.strftime("%Y-%m")] = fest.get(d.strftime("%Y-%m"), 0) + 1
feat["fest"] = [fest.get(m, 0) / pd.Period(m, freq="M").days_in_month for m in feat.index]
WX = [c for c in feat.columns if c.startswith(("p_", "t_"))]


def seas_pred(y, t):
    """engine-style SEAS: grand mean + shrunk calendar-month deviation, from months strictly before t."""
    hist = y[y.index < t]
    mu = hist.mean()
    m = hist[hist.index.str[5:] == t[5:]]
    lam = len(m) / (len(m) + KAPPA)
    return mu + lam * (m.mean() - mu) if len(m) else mu


def ridge_fit(X, r, alpha):
    mu, sd = X.mean(0), X.std(0).replace(0, 1)
    Z = (X - mu) / sd
    b = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (r - r.mean()))
    return mu, sd, b, r.mean()


def ridge_pred(model, xrow):
    mu, sd, b, r0 = model
    return float(r0 + ((xrow - mu) / sd).values @ b)


def resid_series(y):
    return pd.Series({t: y[t] - seas_pred(y, t) for t in y.index if (y.index < t).sum() >= 36})


def cv_alpha(r, cols, F):
    tr = r[r.index <= TRAIN_END].dropna()
    X = F.loc[tr.index, cols]
    ok = X.notna().all(axis=1)
    tr, X = tr[ok], X[ok]
    folds = np.array_split(np.arange(len(tr)), 4)
    best = None
    for a in (1, 3, 10, 30, 100, 300, 1000):
        e = 0
        for f in folds:
            m = np.ones(len(tr), bool); m[f] = False
            mod = ridge_fit(X[m], tr[m], a)
            e += sum((tr.iloc[i] - ridge_pred(mod, X.iloc[i])) ** 2 for i in f)
        if best is None or e < best[0]:
            best = (e, a)
    return best[1]


SPECS = {"SEAS": [], "AR": ["ar"], "WX": WX, "FEST": ["fest"], "WX+AR+FEST": WX + ["ar", "fest"]}
res, losses = {}, {}
for code, item in ITEMS.items():
    y = target(item)
    r = resid_series(y)
    F = feat.copy()
    F["ar"] = [r.get(str(pd.Period(m, freq="M") - 1), np.nan) for m in F.index]
    alphas = {name: cv_alpha(r, cols, F) for name, cols in SPECS.items() if cols}
    test = [t for t in r.index if t >= TEST_START]
    for name, cols in SPECS.items():
        e = []
        for t in test:
            if not cols:
                e.append(r[t]); continue
            past = r[r.index < t]
            X = F.loc[past.index, cols]; ok = X.notna().all(axis=1)
            mod = ridge_fit(X[ok], past[ok], alphas[name])
            xr = F.loc[t, cols]
            e.append(r[t] - ridge_pred(mod, xr) if xr.notna().all() else r[t])
        losses[(code, name)] = pd.Series(e, index=test)
    res[code] = {n: float(np.sqrt((losses[(code, n)] ** 2).mean())) for n in SPECS}
    res[code]["alphas"] = alphas


def dm_test(e0, e1):
    d = e0 ** 2 - e1 ** 2
    n = len(d); lag = 1
    g0 = d.var(ddof=0); g1 = ((d - d.mean()).values[1:] * (d - d.mean()).values[:-1]).mean()
    v = (g0 + 2 * (1 - 1 / (lag + 1)) * g1) / n
    s = d.mean() / np.sqrt(v)
    return float(s), float(1 - stats.norm.cdf(s))


out = {"rmse_pp": res, "n_test": len(test), "dm_vs_SEAS_pooled": {}, "adopted": []}
base = pd.concat([losses[(c, "SEAS")] for c in ITEMS])
allres = {}
for name in SPECS:
    if name == "SEAS":
        continue
    alt = pd.concat([losses[(c, name)] for c in ITEMS])
    s, p = dm_test(base.reset_index(drop=True), alt.reset_index(drop=True))
    allres[name] = dict(rmse_pooled=float(np.sqrt((alt ** 2).mean())), rmse_seas=float(np.sqrt((base ** 2).mean())), dm_stat=s, p_one_sided=p)
    if p < 0.05:
        out["adopted"].append(name)
out["dm_vs_SEAS_pooled"] = allres
# exploratory only (NOT the pre-registered rule): item-level DM p-values, 16 comparisons, so the Bonferroni level is 0.05/16
ex = {}
for c in ITEMS:
    for name in SPECS:
        if name != "SEAS":
            sdm, pv = dm_test(losses[(c, "SEAS")].reset_index(drop=True), losses[(c, name)].reset_index(drop=True))
            ex[f"{c}|{name}"] = dict(rmse_ratio_vs_seas=round(float(np.sqrt((losses[(c, name)] ** 2).mean() / (losses[(c, "SEAS")] ** 2).mean())), 3), p_one_sided=round(pv, 4))
out["exploratory_item_level"] = dict(bonferroni_level=0.05 / 16, results=ex, survivors=[k for k, v in ex.items() if v["p_one_sided"] < 0.05 / 16])
json.dump(out, open("data/official/veg_driver_test.json", "w"), indent=1)
pd.concat({f"{c}|{n}": losses[(c, n)] for c in ITEMS for n in SPECS}, axis=1).to_csv("data/official/veg_driver_errors.csv")
print(json.dumps(out, indent=1))
