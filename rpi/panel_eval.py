"""Deep pseudo-real-time replay of the nowcast rules on the 2014-2025 official Gujarat-urban item panel.

WHY THIS EXISTS.  The live vintage log (rpi/nowcast_eval.py) has at most one scored origin per month and is a year
old, so no head-to-head test at the live horizon is powered (the flagship DM test sits at p~0.2, n=14).  The
2012-base official item panel goes back to 2014-01 and lets every rule be replayed over 76-80 origins per horizon
under ONE fixed protocol - the vintage analogue of a long back-test.  This is a SIMULATION study on official data,
not a substitute for the live record: our own quote data only exist from 2024-10, so the replay cannot know how our
collectors actually behave; it isolates the fill rules.  Results must be read with that in mind.

WHAT IS REPLAYED.  At each origin t (month), for each basket line mapped to the 2012 panel and each horizon h=1..3,
each rule predicts the h-month cumulative log change of the line's official index using only months <= t.  Rules:

  RW      no change (random-walk benchmark)
  T12     engine fallback: h x the item's last-12-month mean log change
  CLIM    h x the item's all-history mean log change (calendar-free drift)
  SEAS    T12 + the EB-shrunk calendar-month deviation to the target months (the seasonal module's SEAS rung)
  SEASC   engine's live seasonal-trend prior: h x long-run mean + shrunk calendar deviation
  MR      mean-reversion: T12 adjusted by the pooled kappa on the deviation from the 12-month mean
  AR1     pooled AR(1) on standardised log changes, iterated h steps (new here)
  KALMAN  local-level state-space filter with the item's own long-run drift and signal/noise ratios estimated by
          method of moments, pooled in the item's volatility group (new here; the state-space rung of the
          mixed-frequency plan - the same filter is what a MIDAS-style monthly aggregation would plug into)
  PANEL   ridge on standardised [h*T12, seasonal, deviation, last change], pooled within the volatility group
  ENS      mean(T12, PANEL)

Two index-level framings, both reported:
  mode=all   every line filled by the rule (measures the rules themselves);
  mode=live  lines whose basket items are `independent` are observed EXACTLY (the optimistic floor used in
             rpi/nowcast_eval.py); only the modelled/linked share of weight is filled by the rule.

STATISTICS.  Index-level errors per origin are tested with rpi/evalstats.py: Diebold-Mariano (HLN-corrected) vs the
live rule SEASC, Mincer-Zarnowitz calibration regressions, Clark-West for nested pairs; the predictive distribution
built from walk-forward error quantiles is scored for coverage / PIT / interval score / CRPS.  The published band in
data/official/nowcast_band_history.json is evaluated against the replay errors directly.

Outputs: data/official/evaluation.json (all of the above), data/official/replay_index_errors.csv (the tidy errors).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import evalstats

PANEL_CSV = "data/official/mospi_cpi2012_gujarat_urban_items.csv"
MAP_CSV = "data/official/basket_to_cpi2012_map.csv"
WEIGHTS_CSV = "data/official/weights_item_detail.csv"
PLAN_CSV = "data/source_plan.csv"
BAND_JSON = "data/official/nowcast_band_history.json"
OUT_JSON = "data/official/evaluation.json"
OUT_ERRORS = "data/official/replay_index_errors.csv"

SELECT_FIRST = pd.Period("2018-01")          # legacy selection window start (scripts/panel_nowcast_rules.py)
SPLIT = pd.Period("2023-01")                 # legacy untouched-test start
RULES = ("RW", "T12", "CLIM", "SEAS", "SEASC", "MR", "AR1", "KALMAN", "PANEL", "ENS")
NESTED_VS_T12 = ("SEAS", "PANEL", "ENS")     # add these to T12 and test the increment (Clark-West)
MIN_TRAIN_ROWS = 150
MIN_TRAIN_ORIGINS = 24


# ---------------------------------------------------------------- panel ----------------------------------------------------------
def load_panel(root: Path) -> dict:
    """Official 2012-base Gujarat-urban item log levels + basket mapping/weights/classes per line."""
    root = Path(root)
    d = pd.read_csv(root / PANEL_CSV)
    P = d.pivot_table(index="period", columns="item", values="index_value").sort_index()
    P.index = pd.PeriodIndex(P.index, freq="M")
    P = P.reindex(pd.period_range(P.index.min(), P.index.max(), freq="M"))
    L = np.log(P.where(P > 0))
    D1 = L.diff()
    mp = pd.read_csv(root / MAP_CSV, dtype=str)
    w = pd.read_csv(root / WEIGHTS_CSV).set_index("item_id")["weight"].astype(float)
    plan = pd.read_csv(root / PLAN_CSV, dtype=str, keep_default_na=False).set_index("item_id")["class"]
    mp = mp[mp.item_id.isin(w.index)]
    line_w = mp.assign(w=mp.item_id.map(w)).groupby("cpi2012_item")["w"].sum()
    line_w = line_w / line_w.sum()
    line_indep = mp.assign(ind=mp.item_id.map(plan).eq("independent")).groupby("cpi2012_item")["ind"].mean()
    lines = sorted(set(mp.cpi2012_item) & set(L.columns))
    return {"L": L, "D1": D1, "lines": lines, "line_w": line_w.reindex(lines),
            "line_indep": line_indep.reindex(lines), "n_items": int(len(w)),
            "independent_weight": float((line_w.reindex(lines) * line_indep.reindex(lines)).sum())}


def _seas_term(D1: pd.DataFrame, col: str, t: pd.Period, targets) -> float:
    """EB-shrunk calendar-month deviation from data up to t only (port of scripts/panel_nowcast_rules.py)."""
    s = D1[col].loc[:t]
    df = pd.DataFrame({"d": s.to_numpy(), "m": [p.month for p in s.index], "y": [p.year for p in s.index]}).dropna()
    g = pd.DataFrame()
    if len(df) >= 36:
        df["dev"] = df.d - df.groupby("y").d.transform("mean")
        g = df.groupby("m").dev.agg(["mean", "count", "var"])
    tau2 = max(float(g["mean"].var(ddof=1)) - float((g["var"] / g["count"]).mean()), 1e-8) if len(g) > 3 else 1e-8
    out = 0.0
    for m in targets:
        if m in g.index and g.loc[m, "count"] >= 3:
            out += tau2 / (tau2 + g.loc[m, "var"] / g.loc[m, "count"]) * g.loc[m, "mean"]
    return float(out)


def build_rows(root: Path, first: pd.Period = SELECT_FIRST, last: pd.Period | None = None,
               horizons=(1, 2, 3)) -> tuple[pd.DataFrame, dict]:
    """Item-level replay rows (one per line x origin x horizon) with every rule's forecast and error."""
    panel = load_panel(root)
    L, D1, lines = panel["L"], panel["D1"], panel["lines"]
    T = list(L.index)
    pos = {p: i for i, p in enumerate(T)}
    last = last or T[-1]
    rows = []
    for t in pd.period_range(first, last, freq="M"):
        i = pos[t]
        for col in lines:
            y = L[col]
            if pd.isna(y.iloc[i]):
                continue
            hist = D1[col].iloc[:i + 1].dropna()
            if len(hist) < 36:
                continue
            sd = float(hist.iloc[-36:].std())
            if not sd > 0:
                continue
            dev = y.iloc[i] - y.iloc[i - 11:i + 1].mean() if not y.iloc[i - 11:i + 1].isna().any() else np.nan
            for h in horizons:
                if i + h >= len(T) or pd.isna(y.iloc[i + h]):
                    continue
                rows.append(dict(line=col, origin=t, op=i, tp=i + h, h=int(h), sd=sd,
                                 t12=float(hist.iloc[-12:].mean()), clim=float(hist.mean()),
                                 dev=dev, lastchg=float(D1[col].iloc[i]),
                                 ret=float(y.iloc[i + h] - y.iloc[i]),
                                 seas=_seas_term(D1, col, t, [(t + k).month for k in range(1, h + 1)])))
    R = pd.DataFrame(rows).dropna(subset=["dev", "lastchg"])
    R["grp"] = np.where(R.sd >= 0.03, "high", "low")
    R["t12_z"] = R.t12 / R.sd
    R["dev_z"] = R.dev / R.sd
    R["seas_z"] = R.seas / R.sd
    R["lastchg_z"] = R.lastchg / R.sd
    R["ret_z"] = R.ret / R.sd
    R = _fit_pooled_rules(R, panel)
    R["f_RW"] = 0.0
    R["f_T12"] = R.h * R.t12
    R["f_CLIM"] = R.h * R.clim
    R["f_SEAS"] = R.f_T12 + R.seas
    R["f_SEASC"] = R.h * R.clim + R.seas
    R["f_ENS"] = 0.5 * (R.f_T12 + R.f_PANEL)
    for rule in RULES:
        R["e_" + rule] = R["f_" + rule] - R.ret
    R["test"] = R.origin >= SPLIT
    meta = {"panel_months": [str(T[0]), str(T[-1])], "lines": len(lines), "items_in_weights": panel["n_items"],
            "independent_weight": round(panel["independent_weight"], 4),
            "origins_per_h": {int(h): int(R[R.h == h].op.nunique()) for h in sorted(R.h.unique())},
            "rows": int(len(R)), "first_origin": str(first), "untouched_test_from": str(SPLIT),
            "T": T, "line_indep": panel["line_indep"], "line_w": panel["line_w"], "_panel": panel}
    return R, meta


def _fit_pooled_rules(R: pd.DataFrame, panel: dict) -> pd.DataFrame:
    """Pooled fits for MR / AR1 / KALMAN / PANEL, expanding window (training targets <= the origin)."""
    L, D1 = panel["L"], panel["D1"]
    for c in ("f_MR", "f_AR1", "f_KALMAN", "f_PANEL"):
        R[c] = np.nan
    t12_fallback = R.h * R.t12
    for (h, o), g in R.groupby(["h", "op"]):
        tr = R[(R.h == h) & (R.tp <= o)]
        for grp in ("high", "low"):
            a = tr[tr.grp == grp]
            idx = g.index[g.grp == grp]
            if len(idx) == 0:
                continue
            if len(a) < MIN_TRAIN_ROWS:
                for c in ("f_MR", "f_AR1", "f_KALMAN", "f_PANEL"):
                    R.loc[idx, c] = t12_fallback.loc[idx]
                continue
            # MR: regress (ret_z - h*t12_z) on dev_z; forecast = T12 - kappa*dev
            x = a.dev_z.to_numpy()
            yv = (a.ret_z - h * a.t12_z).to_numpy()
            kappa = -float(x @ yv / (x @ x))
            R.loc[idx, "f_MR"] = h * R.loc[idx, "t12"] - kappa * R.loc[idx, "dev_z"] * R.loc[idx, "sd"]
            # PANEL: ridge on standardised [h*T12, seasonal, deviation, last change]
            X = np.column_stack([h * a.t12_z, a.seas_z, a.dev_z, a.lastchg_z])
            Y = a.ret_z.to_numpy()
            beta = np.linalg.solve(X.T @ X + 1.0 * np.eye(4), X.T @ Y)
            G = np.column_stack([h * R.loc[idx, "t12_z"], R.loc[idx, "seas_z"], R.loc[idx, "dev_z"], R.loc[idx, "lastchg_z"]])
            R.loc[idx, "f_PANEL"] = (G @ beta) * R.loc[idx, "sd"].to_numpy()
            # AR1: pooled rho on demeaned standardised changes; each line keeps its own long-run drift
            sd_map = g.groupby("line")["sd"].first()
            rho = _pooled_ar1(D1, a.line.unique(), o, sd_map)
            if rho is not None and abs(rho) < 0.99:
                mu_z = R.loc[idx, "clim"].to_numpy() / R.loc[idx, "sd"].to_numpy()
                z_last = R.loc[idx, "lastchg_z"].to_numpy()
                cum = h * mu_z + rho * (1.0 - rho ** h) / (1.0 - rho) * (z_last - mu_z)
                R.loc[idx, "f_AR1"] = cum * R.loc[idx, "sd"].to_numpy()
            R.loc[idx, "f_AR1"] = R.loc[idx, "f_AR1"].fillna(t12_fallback.loc[idx])
            # KALMAN: local level + drift, group-pooled method-of-moments signal/noise, filter per line
            g0, g1 = _pooled_change_moments(D1, list(g.loc[idx, "line"].unique()), o, sd_map)
            R.loc[idx, "kalman_boundary"] = bool(g1 >= 0)          # no measurement noise identified: no signal extraction
            R.loc[idx, "f_KALMAN"] = _kalman_forecasts(g0, g1, L, R, idx, o, h).fillna(t12_fallback.loc[idx])
    return R


def _pooled_change_moments(D1, group_lines, o: int, sd_map: pd.Series) -> tuple[float, float]:
    """Pooled Var and lag-1 autocovariance of standardised changes (demeaned per line), months <= origin."""
    n = 0
    s2 = 0.0
    s1 = 0.0
    pairs = 0
    for line in group_lines:
        if line not in D1.columns or line not in sd_map.index or not float(sd_map[line]) > 0:
            continue
        s = (D1[line].iloc[:o + 1] / float(sd_map[line])).dropna()
        if len(s) < 30:
            continue
        v = s.to_numpy()
        d = v - v.mean()
        s2 += float((d ** 2).sum())
        s1 += float((d[1:] * d[:-1]).sum())
        n += len(d)
        pairs += len(d) - 1
    if n == 0 or pairs == 0:
        return np.nan, np.nan
    return s2 / n, s1 / pairs


def _pooled_ar1(D1, group_lines, o: int, sd_map: pd.Series) -> float | None:
    """Pooled AR(1) coefficient on demeaned standardised changes (no intercept), months <= origin."""
    num = den = 0.0
    pairs = 0
    for line in group_lines:
        if line not in D1.columns or line not in sd_map.index or not float(sd_map[line]) > 0:
            continue
        s = (D1[line].iloc[:o + 1] / float(sd_map[line])).dropna()
        if len(s) < 30:
            continue
        v = s.to_numpy()
        d = v - v.mean()
        num += float((d[1:] * d[:-1]).sum())
        den += float((d[:-1] ** 2).sum())
        pairs += len(d) - 1
    if pairs < 60 or den <= 0:
        return None
    return float(num / den)


def _kalman_forecasts(g0: float, g1: float, L: pd.DataFrame, R: pd.DataFrame, idx, o: int, h: int) -> pd.Series:
    """Local-level + drift forecast per row: filter the standardised log level with method-of-moments signal/noise.

    For a local level, Var(dz) = 2 s2e + s2eta and Cov(dz_t, dz_{t-1}) = -s2e, so both variances are identified from
    the first two moments of the standardised changes - no optimiser, and the filter is the exact Kalman recursion
    for known variances (diffuse prior on the level).  The variances are pooled over the volatility group; the drift
    is the line's own long-run mean change, so the filter only decides how much of the LAST observation is signal.

    Boundary case, recorded per row as `kalman_boundary`: when the pooled lag-1 autocovariance of standardised
    changes is POSITIVE (typical for monthly prices here), -gamma1 < 0 is not a variance, so no measurement noise is
    identified, the filter trusts the last observation completely and collapses to "current level + h x long-run
    drift" - which is the CLIM rule.  That is the state-space rung honestly reporting that at the monthly horizon in
    this panel there is no mean reversion to extract; a genuinely mixed-frequency version needs the daily feeds.
    """
    if not (g0 == g0 and g1 == g1):
        return pd.Series(np.nan, index=idx)
    s2e = max(-g1, 1e-6)
    s2eta = max(g0 - 2.0 * s2e, 1e-6)
    out = pd.Series(np.nan, index=idx)
    for line, sub in R.loc[idx].groupby("line"):
        if line not in L.columns:
            continue
        sd = float(sub.sd.iloc[0])
        z = (L[line].iloc[:o + 1] / sd).dropna()
        if len(z) < 36:
            continue
        mu_z = float(sub.clim.iloc[0]) / sd
        lvl, P = float(z.iloc[0]), 1e6
        zv = z.to_numpy()
        for t in range(1, len(zv)):
            lvl = lvl + mu_z
            P = P + s2eta
            K = P / (P + s2e)
            lvl = lvl + K * (zv[t] - lvl)
            P = (1.0 - K) * P
        out.loc[sub.index] = ((lvl + h * mu_z) - zv[-1]) * sd
    return out


# ---------------------------------------------------------------- index level ----------------------------------------------------------
def _line_weights(R: pd.DataFrame, meta: dict) -> pd.Series:
    w = meta["line_w"].reindex(sorted(R.line.unique())).astype(float)
    return w / w.sum()


def index_errors(R: pd.DataFrame, meta: dict, mode: str = "all", rules=RULES) -> pd.DataFrame:
    """Index-level error (and actual) per origin x h x rule, weighted by basket line weights.

    mode='all'  : every line's rule error counts.
    mode='live' : lines whose basket items are independent are assumed observed exactly (error 0) - the same
                  optimistic floor used in rpi/nowcast_eval.py.
    """
    w_all = _line_weights(R, meta)
    keep = pd.Series(1.0, index=w_all.index)
    if mode == "live":
        keep = 1.0 - meta["line_indep"].reindex(w_all.index).fillna(0.0)
    denom = None
    actual = None
    frames = {}
    for rule in rules:
        E = R.pivot_table(index=["op", "h"], columns="line", values="e_" + rule)
        W = w_all.reindex(E.columns).fillna(0.0)
        denom = (E.notna() * W).sum(axis=1)
        frames[rule] = (E.fillna(0.0) * W * keep.reindex(E.columns).fillna(1.0)).sum(axis=1) / denom
        if actual is None:
            A = R.pivot_table(index=["op", "h"], columns="line", values="ret")
            actual = (A.fillna(0.0) * W).sum(axis=1) / denom
    out = pd.DataFrame(frames)
    out["actual"] = actual
    out.index = pd.MultiIndex.from_tuples(out.index, names=["op", "h"])
    out = out.reset_index()
    out["origin"] = [pd.Period(meta["T"][i], "M") for i in out.op]
    out["test"] = out.origin >= SPLIT
    return out


def rmse_table(errs: pd.DataFrame, rules=RULES) -> dict:
    out = {}
    for rule in rules:
        out[rule] = {}
        for h in sorted(errs.h.unique()):
            for nm, sel in (("test", errs.test), ("all", pd.Series(True, index=errs.index))):
                e = errs[(errs.h == h) & sel][rule].to_numpy()
                out[rule][f"h{h}_{nm}"] = {"n": int(len(e)), "rmse_pp": round(100 * float(np.sqrt(np.mean(e ** 2))), 4),
                                           "bias_pp": round(100 * float(np.mean(e)), 4)}
    return out


def _series(errs: pd.DataFrame, rule: str, h: int, test_only: bool = False) -> pd.Series:
    d = errs[(errs.h == h) & errs.test] if test_only else errs[errs.h == h]
    d = d.sort_values("op")
    return pd.Series(d[rule].to_numpy(), index=d.origin)


def statistical_tests(errs: pd.DataFrame, benchmark: str = "SEASC") -> dict:
    """DM (vs `benchmark`) + Mincer-Zarnowitz per rule + Clark-West for the T12-nested rules, on test origins."""
    out = {}
    for h in sorted(errs.h.unique()):
        d = errs[(errs.h == h) & errs.test].sort_values("op")
        if len(d) < 8:
            continue
        act = d["actual"].to_numpy()
        rows = []
        for rule in RULES:
            e = d[rule].to_numpy()
            f = act + e
            mz = evalstats.mincer_zarnowitz(act, f, h=int(h))
            row = {"rule": rule, "n": len(d), "mz_a": round(mz["a"], 6), "mz_b": round(mz["b"], 4),
                   "mz_p_joint": round(mz["p_joint"], 4)}
            if rule != benchmark:
                dm = evalstats.dm_test(e, d[benchmark].to_numpy(), h=int(h))
                row.update(dm_t_hln=round(dm["t_hln"], 3), dm_p=round(dm["p_two_sided"], 4),
                           dm_favours=dm["favours"])
            if rule in NESTED_VS_T12:
                cw = evalstats.clark_west(act, act + d["T12"].to_numpy(), f, h=int(h))
                row.update(cw_p_one_sided=round(cw["p_one_sided"], 4), cw_favours=cw["favours"])
            rows.append(row)
        # Benjamini-Hochberg within this family (rules x one horizon x one framing)
        ps = [r.get("dm_p", np.nan) for r in rows]
        for r, qv in zip(rows, evalstats.bh_fdr(ps)):
            if "dm_p" in r:
                r["dm_q_bh"] = None if qv != qv else round(float(qv), 4)
        out[f"h{h}"] = rows
    return out


def calibration(errs: pd.DataFrame, min_train: int = MIN_TRAIN_ORIGINS, rules=RULES) -> dict:
    """Walk-forward calibration of each rule's error distribution (coverage / PIT / interval score / CRPS)."""
    out = {}
    for rule in rules:
        out[rule] = {}
        for h in sorted(errs.h.unique()):
            e = _series(errs, rule, h).to_numpy()
            if len(e) < min_train + 10:
                continue
            out[rule][f"h{h}"] = evalstats.calibrate(e, min_train=min_train)
    return out


def band_coverage(root: Path, errs: pd.DataFrame) -> dict:
    """Realised coverage of the half-widths published in nowcast_band_history.json against the replay errors."""
    p = Path(root) / BAND_JSON
    if not p.exists():
        return {}
    b = json.loads(p.read_text())
    out = {"source": BAND_JSON, "band": {k: b.get(k) for k in ("alpha", "rule", "h1_abs_log", "h2_abs_log")},
           "coverage_test_origins": {}}
    for h in (1, 2):
        key = f"h{h}_abs_log"
        if b.get(key) is None:
            continue
        for rule in ("SEASC", "T12", "RW"):
            e = _series(errs, rule, h, test_only=True).to_numpy()
            if len(e):
                half = float(b[key])
                out["coverage_test_origins"].setdefault(f"h{h}", {})[rule] = {
                    "nominal": round(1.0 - float(b.get("alpha", 0.10)), 3), "half_width_log": half,
                    "realised": round(float((np.abs(e) <= half).mean()), 4), "n": int(len(e))}
    return out


def run(root: Path, horizons=(1, 2, 3), first: pd.Period = SELECT_FIRST, last: pd.Period | None = None):
    """Run the replay; returns (result dict, item-level rows, index errors for mode=all, for mode=live)."""
    root = Path(root)
    R, meta = build_rows(root, first=first, last=last, horizons=horizons)
    errs_all = index_errors(R, meta, mode="all")
    errs_live = index_errors(R, meta, mode="live")
    res = {"generated": dt.date.today().isoformat(),
           "protocol": {"first_origin": str(first), "untouched_test_from": str(SPLIT),
                        "horizons": [int(h) for h in horizons], "rules": list(RULES),
                        "note": "simulation study on official 2012-base item indices; our own quote data start "
                                "2024-10, so collector behaviour is not part of this replay"},
           "panel": {k: v for k, v in meta.items() if k not in ("T", "line_indep", "line_w", "_panel")},
           "index_rmse_all": rmse_table(errs_all), "index_rmse_live": rmse_table(errs_live),
           "index_bias_live": {rule: {f"h{h}": round(100 * float(_series(errs_live, rule, h).mean()), 4)
                                      for h in sorted(errs_live.h.unique())} for rule in RULES},
           "tests_all": statistical_tests(errs_all), "tests_live": statistical_tests(errs_live),
           "calibration_all": calibration(errs_all),
           "published_band_coverage": band_coverage(root, errs_all),
           "rule_notes": {"KALMAN": "kalman_boundary_share is the fraction of rule fits where the method-of-moments "
                                    "lag-1 autocovariance is >= 0, so no measurement noise is identified and the filter "
                                    "equals CLIM (current level + h x long-run drift); see rpi/panel_eval.py",
                          "kalman_boundary_share": round(float(R["kalman_boundary"].mean()), 4)}}
    return res, R, errs_all, errs_live


def run_and_write(root: Path, horizons=(1, 2, 3), first: pd.Period = SELECT_FIRST, last: pd.Period | None = None,
                  conn=None) -> dict:
    """Run + write evaluation.json and replay_index_errors.csv; attach the live vintage/revision section if a db is given."""
    root = Path(root)
    res, R, errs_all, errs_live = run(root, horizons=horizons, first=first, last=last)
    if conn is not None:
        from .nowcast_eval import revisions
        res["live_revisions"] = revisions(conn)
    errs = pd.concat([errs_all.assign(mode="all"), errs_live.assign(mode="live")], ignore_index=True)
    errs.to_csv(root / OUT_ERRORS, index=False)
    (root / OUT_JSON).write_text(json.dumps(res, indent=1, default=str))
    return res


def summary_lines(res: dict, top: int = 8) -> list[str]:
    """Compact printable summary: live-mode RMSE per rule, DM p vs SEASC, band coverage."""
    lines = []
    horizons = res.get("protocol", {}).get("horizons") or [1, 2, 3]
    for mode, rmk, tst in (("all", "index_rmse_all", "tests_all"), ("live", "index_rmse_live", "tests_live")):
        lines.append(f"--- {('all lines filled by the rule' if mode == 'all' else 'modelled share only (independent lines observed exactly)')} ---")
        for h in horizons:
            key = f"h{h}_test"
            rank = sorted(((r, res[rmk][r].get(key, {}).get("rmse_pp")) for r in RULES),
                          key=lambda x: (x[1] is None, x[1]))
            lines.append(f"h={h}  {mode}-mode index RMSE (pp), untouched test origins:")
            for r, v in rank[:top]:
                if v is None:
                    continue
                t = next((x for x in res[tst].get(f"h{h}", []) if x["rule"] == r), {})
                p = f"  DM p={t['dm_p']:.3f}" if "dm_p" in t else ""
                lines.append(f"    {r:7s} {v:7.4f}{p}")
    bc = res.get("published_band_coverage", {}).get("coverage_test_origins", {})
    for h, d in bc.items():
        s = "  ".join(f"{r}: {v['realised']:.2f} (nominal {v['nominal']:.2f}, n={v['n']})" for r, v in d.items())
        lines.append(f"published band coverage {h}: {s}")
    return lines
