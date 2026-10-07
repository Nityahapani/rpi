"""Backtest and build the fused best-estimate series (rpi/fusion.py; inventory AK).
Run: PYTHONPATH=. python3 scripts/fusion_backtest.py
Design fixed in advance: origins 2025-07..2026-08 (target month t, only pairs < t used), prior tables built from history <= 2024-12 (no leakage), shrinkage constant 4, floor 0.25 pp.
Methods: PRIOR, RAW (proxy one-for-one = the independent index's rule), CAL (shrunk slope), FUSE (prior + calibrated proxy), FUSE_A5 (FUSE with slope prior from cross-state pooling for the four national-panel items).
Index-level error = sum_i w_i * (estimate_i - official_i) over items with an official change that month (weights re-normalised)."""
import json, sqlite3
import numpy as np, pandas as pd
from scipy import stats
from rpi import fusion as F, pooling as P, proxy_check as pcheck
from rpi.superseded import sql_clause

OFF = "data/official/mospi_cpi2024_gujarat_urban.csv"
conn = sqlite3.connect("data/rpi.sqlite")
plan = pd.read_csv("data/source_plan.csv", dtype=str, keep_default_na=False).set_index("item_id")
mp = pd.read_csv("data/basket_official_map.csv", dtype=str, keep_default_na=False).set_index("item_id")
w = pd.read_csv("data/weights_cpi2024_gujarat_urban.csv").set_index("item_id").weight
d2012 = pd.read_csv("data/official/mospi_cpi2012_gujarat_urban_items.csv").drop_duplicates(["item", "period"])
cmap = pd.read_csv("data/official/basket_to_cpi2012_map.csv")
off = pd.read_csv(OFF, dtype={"code": str})
item_off = off[off.level == "item"].drop_duplicates(["period", "code"]).pivot(index="period", columns="code", values="index_value").sort_index()
MONTHS = pd.period_range("2025-01", "2026-10", freq="M").astype(str)

def dlog(level: pd.Series) -> pd.Series:
    s = level.reindex(MONTHS)
    return np.log(s.where(s > 0)).diff()

# --- inputs: proxy monthly level per item (gated: exactly the gate's series; direct: matched-model chain of tariff / metals / PNG SKUs)
ser = {}
pcheck.validate_proxies(conn, OFF, "data/basket_official_map.csv", "data/source_plan.csv", series_out=ser)
cls, dP, dO, rows = {}, {}, {}, []
for it in plan.index:
    src = plan.loc[it, "primary_source"]
    code = mp.loc[it, "official_item_code"] if it in mp.index else ""
    if code in item_off.columns:
        dO[it] = dlog(item_off[code].dropna())
    if it in ser:
        cls[it] = "gated"; lvl = ser[it][0]
    elif src in F.DIRECT_SOURCES:
        cls[it] = "direct"
        sk = pd.read_sql_query("SELECT o.sku_id sku, substr(o.obs_date,1,7) m, AVG(o.unit_price) v FROM observations o JOIN products p ON p.sku_id=o.sku_id WHERE p.item_id=? AND p.source_id=? AND " + sql_clause("p") + " GROUP BY 1,2", conn, params=[it, src])
        lvl = pcheck.chain_series(sk.pivot(index="m", columns="sku", values="v").sort_index()) if len(sk) else pd.Series(dtype=float)
    else:
        cls[it] = "prior"; lvl = pd.Series(dtype=float)
    if len(lvl):
        dP[it] = dlog(lvl)
        rows += [dict(item_id=it, month=m, level=float(v), cls=cls[it], source=src) for m, v in lvl.items() if v == v]
pd.DataFrame(rows).to_csv("data/official/proxy_monthly_levels.csv", index=False)

tabs = F.build_tables(d2012, cmap, "2024-12")
sp = F.prior_sd(d2012, cmap)

# --- A5 slope priors for the four national-panel items (leakage-safe: panel months < min(t, 2026-01))
panel = pd.read_csv("data/official/national_pooling_panel.csv")
NAME = {"F002": "Rice", "F003": "Tur dal", "F005": "Chana dal", "F024": "Banana"}
def a5_b0(t):
    q = panel[panel.t < min(t, "2026-01")]
    out = {}
    for i, n in NAME.items():
        d = q[(q.item == n) & (q.state != "gujarat")]
        if len(d) >= 20:
            out[i] = P.pooled_slope(d)[0]
    return out

ORIGINS = [m for m in MONTHS if "2025-07" <= m <= "2026-08"]
METH = ["PRIOR", "RAW", "CAL", "FUSE", "FUSE_A5"]
res, items_err = [], []
for t in ORIGINS:
    truth_items = [i for i in cls if i in dO and dO[i].get(t, np.nan) == dO[i].get(t, np.nan)]
    ws = w.reindex(truth_items); ws = ws / ws.sum()
    est0 = F.item_estimates(t, cls, dP, dO, tabs, sp)
    est5 = F.item_estimates(t, cls, dP, dO, tabs, sp, b0=a5_b0(t))
    truth = float(sum(ws[i] * dO[i][t] for i in truth_items))
    r = dict(t=t, truth=truth, n_items=len(truth_items))
    for name, est, key in [("PRIOR", est0, "prior"), ("CAL", est0, "cal"), ("FUSE", est0, "fused"), ("FUSE_A5", est5, "fused")]:
        r[name] = float(sum(ws[i] * (est[i].get(key, est[i]["prior"]) if key != "cal" else est[i].get("cal", est[i]["prior"])) for i in truth_items))
    r["RAW"] = float(sum(ws[i] * est0[i].get("raw", est0[i]["prior"]) for i in truth_items))
    r["sd_model"] = float(np.sqrt(sum(ws[i] ** 2 * est0[i]["var_fused"] for i in truth_items)))
    res.append(r)
    for i in truth_items:
        e = est0[i]
        items_err.append(dict(t=t, item_id=i, cls=cls[i], w=float(ws[i]), actual=float(dO[i][t]), PRIOR=e["prior"], RAW=e.get("raw", e["prior"]), CAL=e.get("cal", e["prior"]), FUSE=e["fused"], FUSE_A5=est5[i]["fused"]))
R = pd.DataFrame(res); IE = pd.DataFrame(items_err)
R.to_csv("data/official/fusion_backtest.csv", index=False); IE.to_csv("data/official/fusion_backtest_items.csv", index=False)

def rmse(a): return float(np.sqrt(np.mean(np.square(a)))) * 100
summ = {m: round(rmse(R[m] - R.truth), 3) for m in METH}
dm = {}
for m in METH:
    if m == "PRIOR": continue
    d = (R.PRIOR - R.truth) ** 2 - (R[m] - R.truth) ** 2
    tstat = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
    dm[f"{m}_vs_PRIOR"] = dict(loss_ratio=round(rmse(R[m] - R.truth) / rmse(R.PRIOR - R.truth), 3), t=round(float(tstat), 2), p_two_sided=round(float(2 * stats.t.sf(abs(tstat), len(d) - 1)), 3))
for a, b in [("FUSE", "RAW"), ("FUSE", "CAL"), ("FUSE_A5", "FUSE")]:
    d = (R[b] - R.truth) ** 2 - (R[a] - R.truth) ** 2
    tstat = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
    dm[f"{a}_vs_{b}"] = dict(loss_ratio=round(rmse(R[a] - R.truth) / rmse(R[b] - R.truth), 3), t=round(float(tstat), 2), p_two_sided=round(float(2 * stats.t.sf(abs(tstat), len(d) - 1)), 3))
# item-level, weight-weighted squared-error shares and class RMSE
byc = {}
for c, g in IE.groupby("cls"):
    byc[c] = {m: round(float(np.sqrt(np.average((g[m] - g.actual) ** 2, weights=g.w))) * 100, 3) for m in METH} | {"weight_share": round(float(g.groupby("t").w.sum().mean()), 3)}
contrib = IE.assign(**{m + "_se": IE.w ** 2 * (IE[m] - IE.actual) ** 2 for m in ("RAW", "FUSE")}).groupby("item_id")[["RAW_se", "FUSE_se"]].sum()
contrib = (contrib / contrib.sum()).round(3).sort_values("RAW_se", ascending=False).head(8)
ratio = float(np.sqrt(np.mean((R.FUSE - R.truth) ** 2)) / np.sqrt(np.mean(R.sd_model ** 2)))
cover = float((np.abs(R.FUSE - R.truth) <= 1.2816 * ratio * R.sd_model).mean())
summ_out = dict(coverage_80_in_sample_scaled=round(cover, 3), coverage_80_unscaled=round(float((np.abs(R.FUSE - R.truth) <= 1.2816 * R.sd_model).mean()), 3), n_origins=len(R), origins=[ORIGINS[0], ORIGINS[-1]], rmse_index_pp=summ, dm=dm, by_class_rmse_pp=byc, top_error_share=contrib.to_dict(),
                band_scale=round(ratio, 3), mean_sd_model_pp=round(float(R.sd_model.mean()) * 100, 3), mean_abs_truth_pp=round(float(R.truth.abs().mean()) * 100, 3),
                corr_truth_vs_official_general=None)
gen = off[off.level == "general"].drop_duplicates("period").set_index("period").index_value.sort_index()
gm = np.log(gen).diff().reindex(R.t)
summ_out["corr_truth_vs_official_general"] = round(float(np.corrcoef(R.truth, gm.values)[0, 1]), 3)

# --- production: official-basis series rebased 2025-01 = 100, nowcast for months not yet published
last = gen.index.max()
base = gen["2025-01"]
out = [dict(period=p, index=round(float(v / base * 100), 3), kind="official", band80_lo="", band80_hi="") for p, v in gen.items()]
lvl = float(gen[last] / base * 100); h = 0
tabs = F.build_tables(d2012, cmap, "2025-12")          # production uses all history through the last full year (backtest used 2024-12)
sp = F.prior_sd(d2012, cmap, 2019, 2025)
latest = conn.execute("SELECT MAX(obs_date) FROM observations").fetchone()[0]          # a partly observed month is not comparable with a full month: nowcast complete months only
complete = latest[:7] if int(latest[8:10]) >= 28 else str(pd.Period(latest[:7], "M") - 1)
for t in [m for m in MONTHS if last < m <= complete]:
    h += 1
    est = F.item_estimates(t, cls, dP, dO, tabs | {}, sp, b0=a5_b0("2026-12"))
    items = [i for i in cls]; ws = w.reindex(items); ws = ws / ws.sum()
    step = float(sum(ws[i] * est[i]["fused"] for i in items)); sd = float(np.sqrt(sum(ws[i] ** 2 * est[i]["var_fused"] for i in items))) * ratio * np.sqrt(h)
    lvl *= float(np.exp(step))
    out.append(dict(period=t, index=round(lvl, 3), kind="nowcast", band80_lo=round(lvl * np.exp(-1.2816 * sd), 3), band80_hi=round(lvl * np.exp(1.2816 * sd), 3)))
summ_out["complete_through"] = complete
S = pd.DataFrame(out).sort_values("period"); S["mom_pct"] = (S["index"].pct_change() * 100).round(3); S["yoy_pct"] = np.nan
ix = S.set_index("period")["index"]
S["yoy_pct"] = [round((ix[p] / ix[str(pd.Period(p, 'M') - 12)] - 1) * 100, 2) if str(pd.Period(p, 'M') - 12) in ix.index else "" for p in S.period]
S.to_csv("docs/data/rpi_fused.csv", index=False)
summ_out["nowcast_months"] = S[S.kind == "nowcast"].to_dict("records")
json.dump(summ_out, open("data/official/fusion_summary.json", "w"), indent=1, default=str)
print(json.dumps(summ_out, indent=1, default=str))
