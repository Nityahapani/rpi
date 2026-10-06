"""Calibrate a SINGLE-YARD / single-district wholesale feed against the official item change, using every OTHER state; test on Gujarat districts.
The live engine feeds one yard (Gondal / Rajkot APMC) into the item as if wholesale change = retail change (beta=1).  Here:
  WB    b0*dw_t + b1*dw_{t-1}, OLS pooled over (state, district) pairs of the other states; official change = state item change   (errors-in-variables
        are absorbed because the regressor is a single noisy district series, exactly like the live feed)
  SEAS  seasonal-trend prior from the Gujarat 2012-base history (scripts/panel_nowcast_rules.py, h=1)
  FUSE  precision-weighted mean of SEAS and WB; sigma_WB^2 = pooled residual variance, sigma_SEAS^2 = SEAS error variance on Gujarat origins <= 2024-12.
        No weight is fitted on the test months.  Items whose wholesale carries no signal get sigma_WB large, so FUSE falls back to SEAS by itself.
Test set: every Gujarat district series (separately), Jan-Oct 2025, official Gujarat-urban item index.   Run: PYTHONPATH=. python3 scripts/yard_calibration.py"""
import json, numpy as np, pandas as pd
from rpi import pooled_checks as pc
CODE = {"Wheat atta": "01.1.1.2.1.01", "Moong": "01.1.7.6.1.02", "Potato": "01.1.7.5.1.01", "Onion": "01.1.7.4.1.01", "Tomato": "01.1.7.2.1.01", "Brinjal": "01.1.7.2.1.03"}
LINE = {"Wheat atta": "Wheat/ Atta – Other Sources", "Moong": "Moong", "Potato": "Potato", "Onion": "Onion", "Tomato": "Tomato", "Brinjal": "Brinjal"}
off = pd.read_csv("data/official/mospi_states_food_items_2025.csv", dtype={"code": str}); off["state"] = off.state.map(pc.norm_state)
off = off[off.code.isin(CODE.values())].dropna(subset=["index_value"]); inv = {v: k for k, v in CODE.items()}; off["item"] = off.code.map(inv); off = off.rename(columns={"period": "month"})
cd = pd.read_csv("data/ceda/district_monthly_modal.csv"); cd["state"] = cd.state.map(pc.norm_state); cd = cd[cd.modal > 0]
R = pd.read_csv("data/official/panel_nowcast_errors.csv"); R["tgt"] = R.tp.apply(lambda o: str(pd.Period(ordinal=int(o), freq="M")))
def chg(s):
    s = s.sort_index(); per = pd.PeriodIndex(s.index, freq="M"); l = np.log(s.values); out = {}
    for i in range(1, len(s)):
        if (per[i] - per[i - 1]).n == 1: out[str(per[i])] = l[i] - l[i - 1]
    return pd.Series(out, dtype=float)
rows = []
for item in CODE:
    o_by = {st: chg(g.drop_duplicates("month").set_index("month").index_value) for st, g in off[off.item == item].groupby("state")}
    for (st, did), g in cd[cd.item == item].groupby(["state", "district_id"]):
        if st not in o_by: continue
        w = chg(g.set_index("month").modal); w1 = w.copy(); w1.index = [str(pd.Period(i, "M") + 1) for i in w.index]
        for t, v in w.items():
            if t in o_by[st].index: rows.append(dict(item=item, state=st, did=did, t=t, dw=v, dw1=w1.get(t, np.nan), do=o_by[st][t]))
F = pd.DataFrame(rows).dropna(subset=["dw1"])
res = {"pairs": {}, "rmse_pp": {}, "coef": {}}; allg = []
for item in CODE:
    f = F[F.item == item]; tr = f[f.state != "gujarat"]; gj = f[f.state == "gujarat"].copy()
    if len(tr) < 50 or gj.empty: continue
    X = tr[["dw", "dw1"]].values; b = np.linalg.lstsq(X, tr.do.values, rcond=None)[0]; s2w = float(np.var(tr.do.values - X @ b)); s2b0 = float(np.var(tr.do.values))
    sub = R[(R.line == LINE[item]) & (R.h == 1)]; hist = sub[sub.tgt <= "2024-12"]
    s2s = float(np.mean((hist.f_SEAS - hist.ret) ** 2)); m = sub.set_index("tgt")
    gj["WB"] = gj[["dw", "dw1"]].values @ b; gj["W1"] = gj.dw; gj["SEAS"] = gj.t.map(m.f_SEAS); gj["T12"] = gj.t.map(m.f_T12); gj["SEASC"] = gj.t.map(m.f_SEASC)
    ws, ww = 1 / s2s, 1 / s2w; gj["FUSE"] = (ws * gj.SEAS + ww * gj.WB) / (ws + ww)
    # engine-implementable variant: climatological prior (SEASC) and lag-0 wholesale only (usable from the first independent month)
    b0 = float(np.linalg.lstsq(tr[["dw"]].values, tr.do.values, rcond=None)[0][0]); s2w0 = float(np.var(tr.do.values - tr.dw.values * b0))
    hist_c = hist; s2c = float(np.mean((hist_c.f_SEASC - hist_c.ret) ** 2))
    gj["WB0"] = b0 * gj.dw; wc, w0 = 1 / s2c, 1 / s2w0; gj["FUSE0"] = (wc * gj.SEASC + w0 * gj.WB0) / (wc + w0); gj["b0only"] = b0; gj["s_wb0"] = np.sqrt(s2w0); gj["s_seasc"] = np.sqrt(s2c)
    gj = gj.dropna(subset=["SEAS"]); gj["wW"] = ww / (ws + ww); allg.append(gj)
    res["pairs"][item] = dict(n_train=len(tr), n_states=int(tr.state.nunique()), n_test=len(gj), n_test_districts=int(gj.did.nunique()))
    res["coef"][item] = dict(b0=round(float(b[0]), 3), b1=round(float(b[1]), 3), sigma_wb=round(np.sqrt(s2w), 4), sigma_seas=round(np.sqrt(s2s), 4), b0_lag0only=round(float(gj.b0only.iloc[0]), 3), sigma_wb_lag0only=round(float(gj.s_wb0.iloc[0]), 4), sigma_seasc=round(float(gj.s_seasc.iloc[0]), 4), sigma_zero_wholesale=round(np.sqrt(s2b0), 4), weight_on_wholesale=round(float(gj.wW.iloc[0]), 3))
G = pd.concat(allg); G.to_csv("data/official/yard_calibration_test.csv", index=False)
ms = ["T12", "SEAS", "SEASC", "W1", "WB", "FUSE", "WB0", "FUSE0"]
for it, g in list(G.groupby("item")) + [("ALL", G), ("VEG4", G[G["item"].isin(["Potato", "Onion", "Tomato", "Brinjal"])])]:
    res["rmse_pp"][it] = {mm: round(100 * float(np.sqrt(((g[mm] - g.do) ** 2).mean())), 2) for mm in ms}
    # month-clustered: average error across districts per month first (what a multi-yard feed would see) is NOT used; single-yard feed is the live case
json.dump(res, open("data/official/yard_calibration_summary.json", "w"), indent=1); print(json.dumps(res, indent=1))
