"""Vegetable fusion test (Gujarat held out of every estimate).
Four volatile vegetables = ~80% of nowcast-error variance (inventory AG). Three estimators of the month-on-month official change:
  SEAS   panel_nowcast_rules.py SEAS prediction from 2012-base Gujarat history up to the prior month (no wholesale information)
  W1     wholesale matched-district change (what the index implicitly assumes: beta=1)
  WB     pooled pass-through b0*dw_t + b1*dw_{t-1}, estimated on the OTHER states only (rpi/pooled_checks.py rules)
  FUSE   precision-weighted mean of SEAS and WB; weights 1/sigma^2 with sigma_SEAS^2 = item's SEAS error variance on Gujarat origins <= 2024-12
         (2012-base history) and sigma_WB^2 = pooled residual variance from the other states. No weight is fitted on the 2025 test months.
Test months: Gujarat Jan-Oct 2025 (official 2024-base item index vs CEDA wholesale, Dec 2024-Oct 2025). Run: PYTHONPATH=. python3 scripts/veg_fusion_test.py"""
import json, numpy as np, pandas as pd
from rpi import pooled_checks as pc
import importlib.util, sys
spec = importlib.util.spec_from_file_location("pa", "scripts/pooled_accuracy.py")
# reuse frame() from pooled_accuracy without running its __main__ block: it only defines functions at import and runs analyses below; so copy minimal pieces
src = open("scripts/pooled_accuracy.py").read().split("# ---- load")[0]
exec(src)  # imports, constants
off = pd.read_csv("data/official/mospi_states_food_items_2025.csv", dtype={"code": str}); off["state"] = off.state.map(pc.norm_state)
name_of = {v: k for k, v in CODE.items()}; off["item"] = off.code.map(name_of); off = off.dropna(subset=["item", "index_value"]).rename(columns={"period": "month"})
cd = pd.read_csv("data/ceda/district_monthly_modal.csv"); cd["state"] = cd.state.map(pc.norm_state)
exec(open("scripts/pooled_accuracy.py").read().split("def wholesale_changes")[1].split("# ---- ")[0].join(["def wholesale_changes", ""]) if False else "")
def wholesale_changes(sub, min_districts=2):
    piv = sub[sub.modal > 0].pivot_table(index="month", columns="district_id", values="modal"); lg = np.log(piv).sort_index()
    per = pd.PeriodIndex(lg.index, freq="M"); d = lg.diff()
    d = d[[(per[i] - per[i - 1]).n == 1 if i else False for i in range(len(per))]]
    n = d.notna().sum(axis=1); return d.mean(axis=1)[n >= min_districts]
def frame(item):
    rows = []
    for st, g in cd[cd.item == item].groupby("state"):
        w = wholesale_changes(g)
        o = pc.changes(off[(off.item == item) & (off.state == st)].assign(key=st).rename(columns={"index_value": "v"}), "v")
        for t, wv in w.items():
            ov = o.get((st, t), np.nan); rows.append(dict(state=st, t=t, dw=float(wv), do=float(ov) if ov == ov else np.nan))
    f = pd.DataFrame(rows); f["tp"] = pd.PeriodIndex(f.t, freq="M"); prev = f[["state", "tp", "dw"]].copy(); prev["tp"] = prev.tp + 1
    return f.merge(prev.rename(columns={"dw": "dw1"}), on=["state", "tp"], how="left")
LINE = {"Potato": "Potato", "Onion": "Onion", "Tomato": "Tomato", "Brinjal": "Brinjal"}
R = pd.read_csv("data/official/panel_nowcast_errors.csv"); R["tgt"] = R.tp.apply(lambda o: str(pd.Period(ordinal=int(o), freq="M")))
out = []
for item in LINE:
    f = frame(item).dropna(subset=["dw", "do", "dw1"])
    tr = f[f.state != "gujarat"]; gj = f[f.state == "gujarat"].copy()
    X = tr[["dw", "dw1"]].values; b = np.linalg.lstsq(X, tr.do.values, rcond=None)[0]; s2w = float(np.var(tr.do.values - X @ b))
    gj["WB"] = gj[["dw", "dw1"]].values @ b; gj["W1"] = gj.dw
    sub = R[(R.line == LINE[item]) & (R.h == 1)]
    hist = sub[sub.tgt <= "2024-12"]; s2s = float(np.mean((hist.f_SEAS - hist.ret) ** 2)); s2t = float(np.mean((hist.f_T12 - hist.ret) ** 2))
    m = sub.set_index("tgt")
    gj["SEAS"] = gj.t.map(m.f_SEAS); gj["T12"] = gj.t.map(m.f_T12); gj["PANEL"] = gj.t.map(m.f_PANEL)
    wS, wW = 1 / s2s, 1 / s2w
    gj["FUSE"] = (wS * gj.SEAS + wW * gj.WB) / (wS + wW)
    gj["item"] = item; gj["b0"], gj["b1"], gj["s_seas"], gj["s_wb"] = b[0], b[1], np.sqrt(s2s), np.sqrt(s2w)
    out.append(gj)
G = pd.concat(out).dropna(subset=["SEAS", "T12"])
G.to_csv("data/official/veg_fusion_test.csv", index=False)
ms = ["T12", "SEAS", "PANEL", "W1", "WB", "FUSE"]
res = {"n_months": G.groupby("item").size().to_dict(), "rmse_pp": {}}
for it, g in list(G.groupby("item")) + [("ALL4", G)]:
    res["rmse_pp"][it] = {m: round(100 * float(np.sqrt(((g[m] - g.do) ** 2).mean())), 2) for m in ms}
res["weights"] = {it: dict(b0=round(float(g.b0.iloc[0]), 3), b1=round(float(g.b1.iloc[0]), 3), sigma_seas=round(float(g.s_seas.iloc[0]), 3), sigma_wb=round(float(g.s_wb.iloc[0]), 3)) for it, g in G.groupby("item")}
json.dump(res, open("data/official/veg_fusion_summary.json", "w"), indent=1); print(json.dumps(res, indent=1))
