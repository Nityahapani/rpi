"""Back-test of nowcast rules on 11 years (2014-2025) of OFFICIAL Gujarat-urban item indices (CPI base 2012), mapped to the basket.

Question 1 (information coverage): which share of the index's no-information nowcast-error variance sits in items that have an
  independent source, and which share sits in items that do not?  (Baseline rule = the engine's fallback for interior gaps and items without a seasonal
  table: own 12-month mean drift.  Note the engine's live rule for TRAILING nowcast gaps is the seasonal-trend prior, rpi/seasonal.py, so this script's
  own_trend baseline is the conservative one, not the live one.)
Question 2 (method): for the items WITHOUT an independent source (linked + none), does any better nowcast rule beat the engine's
  own-trend rule out of sample?  Rules are fixed in advance; selection data = origins <= 2022-12, untouched test = origins >= 2023-01.
Rules: zero | T12 (engine) | T6 | T24 | LinReg12 (extrapolate OLS line through last 12 log levels) | LLT (local-linear-trend Kalman filter,
  trailing 72 months, level+slope) | EBshrink (own T12 shrunk toward the cross-item median T12 with an empirical-Bayes weight) | Combo (zero+T12)/2.
Run: PYTHONPATH=. python3 scripts/linked_nowcast_methods.py   -> data/official/linked_nowcast_errors.csv, linked_nowcast_summary.json"""
import json, warnings, numpy as np, pandas as pd
from multiprocessing import Pool
warnings.filterwarnings("ignore")
from statsmodels.tsa.statespace.structural import UnobservedComponents

d = pd.read_csv("data/official/mospi_cpi2012_gujarat_urban_items.csv")
P = d.pivot_table(index="period", columns="item", values="index_value").sort_index()
P.index = pd.PeriodIndex(P.index, freq="M")
P = P.reindex(pd.period_range(P.index.min(), P.index.max(), freq="M"))
L = np.log(P)
mp = pd.read_csv("data/official/basket_to_cpi2012_map.csv", dtype=str)
w = pd.read_csv("data/official/weights_item_detail.csv").set_index("item_id")["weight"].astype(float)
plan = pd.read_csv("data/source_plan.csv", dtype=str, keep_default_na=False).set_index("item_id")["class"]
mp = mp[mp.item_id.isin(w.index)].copy()
# several basket items share one official line (LPG, refined oil, medicine): keep them as separate items
H = (1, 2); START = pd.Period("2016-01"); END = pd.Period("2025-12"); SPLIT = pd.Period("2023-01")
METHODS = ["zero", "T12", "T6", "T24", "LinReg12", "LLT", "EBshrink", "Combo"]


def drift(y, k):
    dy = y.diff().dropna()
    return float(dy.iloc[-k:].mean()) if len(dy) >= k else np.nan


def llt(y):
    yy = y.dropna().iloc[-72:]
    try:
        m = UnobservedComponents(yy.values, level="lltrend").fit(disp=False, maxiter=60)
        lv = m.filtered_state[0, -1]; sl = m.filtered_state[1, -1]
        return lv, sl
    except Exception:
        return np.nan, np.nan


def run_item(args):
    iid, name, do_llt = args
    y_full = L[name]
    rows = []
    for t in pd.period_range(START, END - 1, freq="M"):
        y = y_full.loc[:t]
        if pd.isna(y.loc[t]) or y.dropna().shape[0] < 24:
            continue
        hist = y.dropna()
        d12, d6, d24 = drift(hist, 12), drift(hist, 6), drift(hist, 24)
        xs = np.arange(12); yy = hist.iloc[-12:].values
        b, a = np.polyfit(xs, yy, 1); fit_end = a + b * 11
        lv, sl = (llt(y) if do_llt else (np.nan, np.nan))
        # EB shrink needs cross-item median at t -> filled later via G
        sd = float(hist.diff().dropna().iloc[-36:].std())
        for h in H:
            tgt = t + h
            if tgt > END or pd.isna(y_full.get(tgt)):
                continue
            actual = y_full.loc[tgt]
            f = {"zero": y.loc[t], "T12": y.loc[t] + h * d12, "T6": y.loc[t] + h * d6, "T24": y.loc[t] + h * d24,
                 "LinReg12": fit_end + h * b, "LLT": (lv + h * sl) if do_llt else np.nan}
            f["Combo"] = 0.5 * f["zero"] + 0.5 * f["T12"]
            rows.append(dict(item_id=iid, origin=str(t), h=h, actual=actual, d12=d12, sd=sd, ylast=y.loc[t], **{f"f_{k}": v for k, v in f.items()}))
    return rows


def main():
    cls = plan.reindex(mp.item_id).fillna("none")
    jobs = [(r.item_id, r.cpi2012_item, cls[r.item_id] != "independent") for r in mp.itertuples()]
    with Pool(4) as p:
        res = p.map(run_item, jobs, chunksize=1)
    D = pd.DataFrame([x for r in res for x in r])
    # cross-sectional median drift at each origin (all 299 official lines) for the EB-shrink rule
    G = {}
    for t in pd.period_range(START, END - 1, freq="M"):
        G[str(t)] = float(np.nanmedian([drift(L[c].loc[:t].dropna(), 12) for c in L.columns if L[c].loc[:t].dropna().shape[0] > 24]))
    D["G"] = D.origin.map(G)
    # EB weight: tau2 = cross-item variance of d12 at the origin minus average sampling variance (sd^2/12)
    tau2 = D.groupby("origin").apply(lambda g: max(float(np.var(g.d12.dropna(), ddof=1)) - float(np.mean(g.sd ** 2 / 12)), 1e-10))
    D["tau2"] = D.origin.map(tau2)
    D["lam"] = D.tau2 / (D.tau2 + D.sd ** 2 / 12)
    D["f_EBshrink"] = D.ylast + D.h * (D.lam * D.d12 + (1 - D.lam) * D.G)
    for m in METHODS:
        D[f"e_{m}"] = D[f"f_{m}"] - D.actual
    D["class"] = D.item_id.map(cls)
    D["w"] = D.item_id.map(w)
    D["period"] = D.origin.map(pd.Period)
    D["test"] = D.period >= SPLIT
    D.drop(columns="period").to_csv("data/official/linked_nowcast_errors.csv", index=False)
    return D


if __name__ == "__main__":
    D = main(); print(len(D), D.item_id.nunique())
