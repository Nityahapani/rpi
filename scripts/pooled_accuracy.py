"""Run the pooled pass-through test, the three-cornered-hat test and the forecast scoring (see rpi/pooled_checks.py for the rules, fixed in advance).
Inputs (all produced by scripts in this folder): data/official/mospi_states_food_items_2025.csv, data/ceda/district_monthly_modal.csv,
data/doca/state_panel_monthly.csv, data/official/replay_backtest.csv.   Run: PYTHONPATH=. python3 scripts/pooled_accuracy.py"""
import json
import numpy as np
import pandas as pd
from rpi import pooled_checks as pc
from rpi.proxy_check import judge

ITEMS = ["Potato", "Onion", "Tomato", "Brinjal", "Banana", "Wheat atta", "Moong", "Tur", "Gram split", "Rice", "Jaggery"]
CODE = {"Wheat atta": "01.1.1.2.1.01", "Tur": "01.1.7.6.1.01", "Moong": "01.1.7.6.1.02", "Gram split": "01.1.7.6.1.05", "Potato": "01.1.7.5.1.01", "Onion": "01.1.7.4.1.01",
        "Tomato": "01.1.7.2.1.01", "Brinjal": "01.1.7.2.1.03", "Rice": "01.1.1.1.1.01", "Banana": "01.1.6.1.1.01", "Jaggery": "01.1.8.1.1.02"}
RAJKOT_DISTRICT_ID = 476

# ---- load ---------------------------------------------------------------------------------------------------------------------------
off = pd.read_csv("data/official/mospi_states_food_items_2025.csv", dtype={"code": str})
off["state"] = off.state.map(pc.norm_state); name_of = {v: k for k, v in CODE.items()}; off["item"] = off.code.map(name_of)
off = off.dropna(subset=["item", "index_value"]).rename(columns={"period": "month"})
doca = pd.read_csv("data/doca/state_panel_monthly.csv"); doca["state"] = doca.state.map(pc.norm_state)
cd = pd.read_csv("data/ceda/district_monthly_modal.csv"); cd["state"] = cd.state.map(pc.norm_state)


def wholesale_changes(sub: pd.DataFrame, min_districts: int = 2) -> pd.Series:
    """matched-district Jevons: mean over districts quoted in BOTH months of the log change of the monthly modal price."""
    piv = sub[sub.modal > 0].pivot_table(index="month", columns="district_id", values="modal")
    lg = np.log(piv).sort_index()
    per = pd.PeriodIndex(lg.index, freq="M")
    d = lg.diff()
    d = d[[(per[i] - per[i - 1]).n == 1 if i else False for i in range(len(per))]]
    n = d.notna().sum(axis=1)
    out = d.mean(axis=1)[n >= min_districts]
    return out


def frame(item: str) -> pd.DataFrame:
    rows = []
    for st, g in cd[cd.item == item].groupby("state"):
        w = wholesale_changes(g)
        o = pc.changes(off[(off.item == item) & (off.state == st)].assign(key=st).rename(columns={"index_value": "v"}), "v")
        d = doca[(doca.item == item) & (doca.state == st)].rename(columns={})
        dd = pc.changes(d.assign(key=st), "level") if len(d) else pd.Series(dtype=float)
        for t, wv in w.items():
            ov = o.get((st, t), np.nan); dv = dd.get((st, t), np.nan) if len(dd) else np.nan
            rows.append(dict(state=st, t=t, dw=float(wv), do=float(ov) if ov == ov else np.nan, dd=float(dv) if dv == dv else np.nan))
    f = pd.DataFrame(rows)
    if f.empty: return f
    f["tp"] = pd.PeriodIndex(f.t, freq="M")
    prev = f[["state", "tp", "dw"]].copy(); prev["tp"] = prev.tp + 1
    f = f.merge(prev.rename(columns={"dw": "dw1"}), on=["state", "tp"], how="left")
    return f


def level_from(changes_: pd.Series, beta) -> pd.Series:
    return 100 * np.exp((np.asarray(changes_) * beta).cumsum())


# ---- 1. pooled pass-through -----------------------------------------------------------------------------------------------------------
res1, res2 = [], []
gj_off = {it: off[(off.item == it) & (off.state == "gujarat")].set_index("month").index_value for it in ITEMS}
for it in ITEMS:
    f = frame(it)
    if f.empty: continue
    base = f.dropna(subset=["do", "dw"])
    pool = base[(base.state != "gujarat")]
    if pool.state.nunique() < 8: res1.append(dict(item=it, note=f"only {pool.state.nunique()} states with both series")); continue
    p_lag = base.dropna(subset=["dw1"])
    spec = {}
    for lag in (False, True):
        d = p_lag if lag else base
        spec[lag] = pc.loso(d, lag)
    lag = bool(spec[True].get("rmse_pool", 9) < spec[False].get("rmse_pool", 9))
    d = p_lag if lag else base
    b, lo, hi = pc.boot_beta(d, lag)
    ls = spec[lag]
    row = dict(item=it, n_states=int(d[d.state != "gujarat"].state.nunique()), n_obs=int(len(d[d.state != "gujarat"])), spec="lag0+lag1" if lag else "lag0",
               beta=round(float(b.sum()), 2), beta_lo=round(float(lo.sum()), 2), beta_hi=round(float(hi.sum()), 2),
               loso_rmse_pool=round(ls["rmse_pool"], 4), loso_rmse_beta1=round(ls["rmse_b1"], 4), loso_rmse_beta0=round(ls["rmse_b0"], 4),
               loso_wins_vs_beta1=f"{ls['wins_vs_b1']}/{ls['n_states']}", loso_wins_vs_beta0=f"{ls['wins_vs_b0']}/{ls['n_states']}",
               loso_drift_pool=round(ls["drift_pool"], 3), loso_drift_beta1=round(ls["drift_b1"], 3))
    # apply to Gujarat (held out), two wholesale geographies: Gujarat state districts, and Rajkot district alone
    for geo, sub in (("gujarat_state", cd[(cd.item == it) & (cd.state == "gujarat")]), ("rajkot_district", cd[(cd.item == it) & (cd.district_id == RAJKOT_DISTRICT_ID)])):
        w = wholesale_changes(sub, 1) if len(sub) else pd.Series(dtype=float)
        o = gj_off[it]
        if len(w) < 7 or o.empty: row[f"{geo}_note"] = "no wholesale data"; continue
        w = w[w.index >= "2025-02"]
        betas = (b if lag else b)
        if lag:
            wl = pd.concat([w, w.shift(1).fillna(0.0)], axis=1).values
            pred = wl @ b
        else:
            pred = w.values * b[0]
        lv_pool = pd.Series(100 * np.exp(np.cumsum(pred)), index=w.index); lv_b1 = pd.Series(level_from(w.values, 1.0), index=w.index)
        jp, j1 = judge(lv_pool, o), judge(lv_b1, o)
        row.update({f"{geo}_pooled_corr": jp["corr"], f"{geo}_pooled_drift": jp["drift"], f"{geo}_pooled_verdict": jp["verdict"],
                    f"{geo}_beta1_drift": j1["drift"], f"{geo}_beta1_verdict": j1["verdict"], f"{geo}_n": jp["n_overlap"]})
    res1.append(row)
r1 = pd.DataFrame(res1); r1.to_csv("data/official/pooled_passthrough.csv", index=False)

# ---- 2. three-cornered hat ---------------------------------------------------------------------------------------------------------------
for it in ITEMS:
    f = frame(it).dropna(subset=["do", "dd", "dw"])
    if f.state.nunique() < 8: res2.append(dict(item=it, note=f"only {f.state.nunique()} states with all three series")); continue
    t = pc.triad_boot(f.rename(columns={"do": "o", "dd": "d", "dw": "w"}))
    e = t["est"]
    fmt = lambda x: None if x is None else round(x, 2)
    ci = lambda c: None if t["rel_ci"][c][0] is None else f"{t['rel_ci'][c][0]:.2f}-{t['rel_ci'][c][1]:.2f}"
    res2.append(dict(item=it, n_states=int(f.state.nunique()), n_obs=int(len(f)),
                     reliab_official=fmt(e["a"]["reliability"]), ci_official=ci("a"), reliab_doca=fmt(e["b"]["reliability"]), ci_doca=ci("b"),
                     reliab_wholesale=fmt(e["c"]["reliability"]), ci_wholesale=ci("c"),
                     passthrough_corrected=fmt(t["ratio"]), passthrough_ci="" if t["ratio_ci"][0] is None else f"{t['ratio_ci'][0]:.2f}-{t['ratio_ci'][1]:.2f}",
                     note="; ".join(f"{k}:{v.get('note')}" for k, v in e.items() if v.get("note"))))
r2 = pd.DataFrame(res2); r2.to_csv("data/official/pooled_triad.csv", index=False)

# ---- 3. forecast scoring ------------------------------------------------------------------------------------------------------------------
rb = pd.read_csv("data/official/replay_backtest.csv")
sc = {}
for h in (1, 2):
    x = rb[rb.h == h]
    e, e_own, e_zero = x.err_pct.values, x.err_own_trend_only_pct.values, x.err_zero_change_pct.values
    sc[f"h{h}"] = dict(n=len(x), rmse_engine=round(float(np.sqrt((e ** 2).mean())), 3), rmse_own_trend=round(float(np.sqrt((e_own ** 2).mean())), 3), rmse_zero=round(float(np.sqrt((e_zero ** 2).mean())), 3),
                       dm_engine_vs_own_trend=pc.dm_test(e, e_own), dm_engine_vs_zero=pc.dm_test(e, e_zero), loo_conformal_90=pc.loo_conformal_coverage(e))
json.dump(sc, open("data/official/forecast_scoring.json", "w"), indent=1)

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
print(r1.to_string(index=False)); print(); print(r2.to_string(index=False)); print(); print(json.dumps(sc, indent=1))
