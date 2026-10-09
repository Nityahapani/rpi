"""Nowcast evaluation: rolling-origin back-test, conformal bands and a real-time vintage log.

Months after the last official release are not fully observed, so the published level for those months is a nowcast: every
item with no independent feed falls back to a fill rule, and the back-test below measures how wrong such fills are and which
rule is least wrong.  Which items those are is read LIVE from data/source_plan.csv (everything whose `class` is not
`independent` - a small and shrinking set, 10.8% of weight today, all flagged official stand-ins); this module hard-codes no
split, so the numbers here cannot drift from the wiring:

* the 20 months of official Gujarat-urban item indices are replayed in a rolling-origin (expanding window) pseudo-real-time
  exercise: at every origin t the fill rule only sees months < t, and its 1- and 2-month-ahead total log change is compared
  with what the official item indices then did;
* the rules compared are: zero change, the item's own 12-month mean drift (the engine's fallback rule - it fills INTERIOR gaps, e.g. the splice month
  where an independent feed starts, and any item without a seasonal table; TRAILING nowcast gaps instead use the seasonal-trend prior where one exists,
  see rpi/seasonal.py and rpi/index/aggregate.py::impute_relatives), the item's own drift while
  our independently observed items are assumed to be seen EXACTLY (an optimistic floor), and the old rule that filled
  unobserved items with the weighted mean relative of observed peers in the same division (shown to be harmful);
* a split-conformal band (distribution-free, finite-sample corrected) is built from the absolute errors of the conservative
  rule, i.e. assuming our independent items add no information. It is published next to every nowcast month.

A vintage log (`data/nowcast_vintages.csv`) stores every nowcast we publish; when the official release arrives the nowcast is
scored against it, so the back-test is continuously replaced by a genuine real-time record.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ALPHA = 0.10
WINDOW = 12
MIN_TRAIN = 8
BAND_FILE = "data/official/nowcast_backtest.json"
VINTAGE_FILE = "data/nowcast_vintages.csv"


def official_panel(root: Path):
    """Official Gujarat-urban item log relatives mapped to basket items.

    Returns (lr: periods x items, w: normalised weights, independent: list, division: Series)."""
    root = Path(root)
    off = pd.read_csv(root / "data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
    off = off[off.level == "item"]
    mp = pd.read_csv(root / "data/basket_official_map.csv", dtype=str, keep_default_na=False)
    w = pd.read_csv(root / "data/weights_cpi2024_gujarat_urban.csv").set_index("item_id").iloc[:, 0].astype(float)
    plan = pd.read_csv(root / "data/source_plan.csv", dtype=str, keep_default_na=False).set_index("item_id")
    basket = pd.read_csv(root / "data/basket.csv", dtype=str).set_index("item_id")
    piv = off.pivot_table(index="period", columns="code", values="index_value").sort_index()
    cols = {i: c for i, c in zip(mp["item_id"], mp["official_item_code"]) if c in piv.columns and i in w.index}
    lr = np.log(piv[list(cols.values())]).diff().iloc[1:]
    lr.columns = list(cols.keys())
    ww = w[lr.columns] / w[lr.columns].sum()
    indep = [i for i in lr.columns if plan.loc[i, "class"] == "independent"]
    div = basket.loc[lr.columns, "division"].astype(str)
    return lr, ww, indep, div


def _old_peer_fill(c: pd.Series, ww: pd.Series, indep: list, div: pd.Series) -> pd.Series:
    """The rule used before the 6th sweep: unobserved item <- weighted mean relative of observed items in its division."""
    v = pd.Series(np.nan, index=c.index)
    obs = c[indep]
    overall = float((ww[indep] * obs).sum() / ww[indep].sum())
    for d in div.unique():
        ii = list(div.index[div == d])
        oi = [i for i in ii if i in indep]
        v[ii] = float((ww[oi] * c[oi]).sum() / ww[oi].sum()) if oi else overall
    v[indep] = c[indep]
    return v


def backtest(lr: pd.DataFrame, ww: pd.Series, indep: list, div: pd.Series, window: int = WINDOW,
             min_train: int = MIN_TRAIN, alpha: float = ALPHA) -> dict:
    T = len(lr)
    act = (lr * ww).sum(axis=1)
    names = ("zero_change", "own_trend", "own_trend_independents_exact", "old_division_peer_fill")
    errs = {n: {1: [], 2: []} for n in names}
    for t in range(min_train, T):
        hist = lr.iloc[:t]
        own = hist.iloc[-window:].mean().fillna(0.0)
        for hz in (1, 2):
            if t + hz > T:
                continue
            a = float(act.iloc[t:t + hz].sum())
            errs["zero_change"][hz].append(0.0 - a)
            errs["own_trend"][hz].append(float((ww * own).sum()) * hz - a)
            pe, po = 0.0, 0.0
            for k in range(hz):
                c = lr.iloc[t + k]
                v = own.copy()
                v[indep] = c[indep]
                pe += float((ww * v).sum())
                po += float((ww * _old_peer_fill(c, ww, indep, div)).sum())
            errs["own_trend_independents_exact"][hz].append(pe - a)
            errs["old_division_peer_fill"][hz].append(po - a)
    methods = {}
    for n in names:
        methods[n] = {}
        for hz in (1, 2):
            e = np.array(errs[n][hz])
            methods[n][f"h{hz}"] = {"n": int(len(e)), "rmse_pp": round(float(np.sqrt((e ** 2).mean())) * 100, 3),
                                    "bias_pp": round(float(e.mean()) * 100, 3)} if len(e) else None
    band = {"alpha": alpha, "rule": "own_trend (conservative: independent items add no information)"}
    for hz in (1, 2):
        e = np.sort(np.abs(np.array(errs["own_trend"][hz])))
        n = len(e)
        k = math.ceil((n + 1) * (1 - alpha))
        valid = k <= n          # with fewer than 1/alpha - 1 points a 1-alpha band is not supportable
        band[f"h{hz}_abs_log"] = round(float(e[min(k, n) - 1]), 5) if n else None
        band[f"h{hz}_n"] = n
        band[f"h{hz}_valid"] = bool(valid)
    return {"methods": methods, "band": band, "n_items": int(lr.shape[1]), "n_months": int(T),
            "origin_range": [str(lr.index[min_train]), str(lr.index[-1])],
            "note": "The 'independents exact' row assumes our independent items equal their official counterparts; real proxies are "
                    "noisier, so it is an optimistic floor. The published band uses the conservative rule."}


def run_backtest(root: Path) -> dict:
    root = Path(root)
    lr, ww, indep, div = official_panel(root)
    res = backtest(lr, ww, indep, div)
    hb = root / "data/official/nowcast_band_history.json"      # sweep 27: band from 11 years of seasonal-trend errors (n=79/78 origins) replaces the 11-origin band
    if hb.exists():
        h = json.loads(hb.read_text())
        res["band_short_sample"] = res["band"]
        res["band"] = {k: h[k] for k in ("alpha", "rule", "h1_abs_log", "h1_n", "h1_valid", "h2_abs_log", "h2_n", "h2_valid")}
    res["generated"] = dt.date.today().isoformat()
    (root / BAND_FILE).write_text(json.dumps(res, indent=2))
    return res


def band_for(root: Path, h: int) -> float | None:
    """Half-width (log points) of the 90% nowcast band for a nowcast h months after the last official month."""
    p = Path(root) / BAND_FILE
    if not p.exists() or h < 1:
        return None
    b = json.loads(p.read_text())["band"]
    q1, q2 = b.get("h1_abs_log"), b.get("h2_abs_log")
    if q1 is None or q2 is None:
        return None
    if h == 1:
        return q1
    if h == 2:
        return q2
    return q2 * math.sqrt(h / 2.0)       # beyond the back-tested horizon: random-walk accumulation (flagged as extrapolated)


# ---- vintage log -------------------------------------------------------------------------------------------------------
def log_vintages(root: Path, total: pd.Series, ref_period: str | None, run_id: str, today: dt.date | None = None) -> int:
    """Append today's nowcasts (months after the reference month) to the vintage log; idempotent per (date, period)."""
    if ref_period is None:
        return 0
    today = today or dt.date.today()
    path = Path(root) / VINTAGE_FILE
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["logged_on", "run_id", "period", "h", "index_value", "ref_period"])
    ref = pd.Period(ref_period, "M")
    rows = []
    for per, val in total.items():
        if per > ref:
            rows.append(dict(logged_on=today.isoformat(), run_id=run_id, period=str(per), h=int((per - ref).n),
                             index_value=round(float(val), 4), ref_period=ref_period))
    if not rows:
        return 0
    new = pd.DataFrame(rows)
    key = ["logged_on", "period"]
    merged = pd.concat([old[~old.set_index(key).index.isin(new.set_index(key).index)], new], ignore_index=True)
    merged.to_csv(path, index=False)
    return len(new)


def revisions(conn, variant: str = "jevons_chain", min_vintages: int = 2, triangle_periods: int = 8,
              triangle_vintages: int = 12) -> dict:
    """Revision analysis of the published series itself, from `index_results` (every build stores its full series).

    Revisions are expected: a month first published as a nowcast is later carried by real quotes, prices get
    corrected, the seasonal prior moves. The point is to PUBLISH the revision distribution - a standard
    statistical-agency credibility artifact - not to eliminate it.

    Builds are grouped into REGIMES by `index_runs.weights_source` (the recorded methodology label). A change of
    weights_source is a methodology break, and revisions computed across one mix a data update with an engine
    change; so revisions are computed WITHIN a regime and the breaks are reported separately.
    """
    q = pd.read_sql_query(
        "SELECT i.run_id, i.period, i.value, r.built_at, r.weights_source "
        "FROM index_results i JOIN index_runs r USING(run_id) "
        "WHERE i.variant=? AND i.level='total' AND i.key='ALL' ORDER BY i.run_id", conn, params=(variant,))
    if q.empty:
        return {"n_periods": 0, "note": "no index_results rows"}
    order = list(dict.fromkeys(q.sort_values("run_id").weights_source))
    q["regime"] = q.weights_source.map({s: i for i, s in enumerate(order)})
    out = {"variant": variant, "n_runs": int(q.run_id.nunique()),
           "run_span": [str(q.run_id.min()), str(q.run_id.max())], "regimes": [], "breaks": []}
    prev = None
    for i, src in enumerate(order):
        g = q[q.regime == i]
        rows = []
        for per, gp in g.groupby("period"):
            if len(gp) < min_vintages:
                continue
            gp = gp.sort_values("run_id")
            first, last = float(gp.value.iloc[0]), float(gp.value.iloc[-1])
            rows.append({"period": per, "n_vintages": int(len(gp)), "first": round(first, 4), "last": round(last, 4),
                         "revision": round(last - first, 4), "revision_pct": round((last / first - 1) * 100, 4)})
        df = pd.DataFrame(rows).sort_values("period") if rows else pd.DataFrame()
        lab = f"R{i + 1}"
        regime = {"label": lab, "n_runs": int(g.run_id.nunique()), "first_run": str(g.run_id.min()),
                  "last_run": str(g.run_id.max()), "method_label": str(src)[-160:],
                  "n_periods_with_vintages": int(len(df)),
                  "mean_abs_revision": round(float(df.revision.abs().mean()), 4) if len(df) else None,
                  "mean_abs_revision_pct": round(float(df.revision_pct.abs().mean()), 4) if len(df) else None,
                  "max_abs_revision_pct": round(float(df.revision_pct.abs().max()), 4) if len(df) else None}
        out["regimes"].append(regime)
        if prev is not None and len(df):
            a = q[q.regime == prev].groupby("period").value.median()
            b = g.groupby("period").value.median()
            common = a.index.intersection(b.index)
            if len(common):
                jump = ((b[common] / a[common] - 1) * 100).abs()
                out["breaks"].append({"from": f"R{prev + 1}", "to": lab, "n_overlapping_periods": int(len(common)),
                                      "median_abs_jump_pct": round(float(jump.median()), 4),
                                      "max_abs_jump_pct": round(float(jump.max()), 4)})
        prev = i
    last = q[q.regime == order.index(order[-1])]
    if len(last):
        df = pd.DataFrame([{"period": p, "value": v} for p, v in last.groupby("period").value.last().items()])
        tri_v = sorted(last.run_id.unique())[-triangle_vintages:]
        tri = last[last.run_id.isin(tri_v)].pivot_table(index="period", columns="run_id", values="value")
        keep = tri.tail(triangle_periods)
        out["triangle"] = {str(p): {str(c)[:15]: (None if pd.isna(v) else round(float(v), 3)) for c, v in row.items()}
                           for p, row in keep.iterrows()}
    out["note"] = ("revisions within a regime are data updates (new quotes, corrections, official data arriving); "
                   "`breaks` are methodology changes, which are NOT data revisions and dwarf them - compare only "
                   "like-for-like runs when judging the revision record")
    return out


def score_vintages(root: Path, realised: pd.Series) -> dict:
    """Compare logged nowcasts with the index level later published for the same month once official data exist.

    `realised` = published total index by period for months that are no longer nowcasts. For each such month the nowcast
    logged EARLIEST (largest h) and LATEST are scored; errors are in index points and percent."""
    path = Path(root) / VINTAGE_FILE
    if not path.exists():
        return {"n_scored": 0}
    v = pd.read_csv(path)
    rows = []
    for per, g in v.groupby("period"):
        p = pd.Period(per, "M")
        if p not in realised.index or pd.isna(realised.loc[p]):
            continue
        if (g["ref_period"].map(lambda r: pd.Period(r, "M")) >= p).all():
            continue                       # never was a nowcast in any logged vintage
        for lab, row in (("first", g.sort_values("logged_on").iloc[0]), ("last", g.sort_values("logged_on").iloc[-1])):
            rows.append(dict(period=per, vintage=lab, logged_on=row["logged_on"], h=int(row["h"]),
                             nowcast=float(row["index_value"]), realised=float(realised.loc[p]),
                             error_pct=round((float(row["index_value"]) / float(realised.loc[p]) - 1) * 100, 3)))
    if not rows:
        return {"n_scored": 0}
    df = pd.DataFrame(rows)
    return {"n_scored": int(df.period.nunique()), "mean_abs_error_pct": round(float(df.error_pct.abs().mean()), 3),
            "rows": df.to_dict("records")}
