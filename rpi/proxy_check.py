"""Proxy validation gate for non-official price series.

Three gates are reported independently. A series passes if any leg passes. If no leg
passes, the overall verdict remains pending while any applicable leg is still unevaluable;
it fails only when every applicable leg has been evaluated and failed. `leg_status` keeps
the different window limits visible:

  A (monthly tracking): n >= 6, correlation of month-on-month log changes >= 0.5,
     and cumulative log-change drift over the full overlap <= 0.10.
  B (annual tracking): correlation of calendar-aligned 12-month log changes >= 0.5,
     evaluated once at least three paired 12-month changes are available (no separate
     24-level minimum).
  C (level fit): n >= 24, R-squared of log(proxy) ~ log(official) >= 0.5,
     slope in [0.5, 1.5], and absolute cumulative log-change drift over the latest
     24 calendar months <= 0.10. The exact t-24 level is required; otherwise C is pending.

The constant level offset is admissible: published item relatives are chain-rebased,
so a fixed proportional level difference cancels. The slope, fit, and recent drift
checks prevent a loose level association from excusing bad pass-through or current
divergence. Every result includes the diagnostics, `legs` (the passing legs), and
`leg_status` (pass/fail/pending for A, B, and C).

All validation uses `data/official/official_item_spliced.csv`, built from the CPI2012
item history and CPI2024's overlapping/newer months. Falling back silently to the
short CPI2024-only history would defeat the long-window gate, so a missing comparator
is an error.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .superseded import sql_clause

PROXY_SOURCES = (
    "apple_store", "hathway_broadband", "green_mercado", "mandi_gondal", "mandi_rajkot_apmc",
    "mandi_rajkot_veg", "yard_rajkot_board", "mandi_rajkot_district", "necc_ahmedabad",
    "doca_national", "doca_gujarat", "dmart_ahmedabad", "vishal_diary", "frc_rajkot",
    "district_cinema", "fresha_salon",
)
# Multi-SKU pools are chained over matched SKUs. DoCA Rajkot commodity ids 17/18/19/20/21
# jointly represent F008 edible oils; they are not averaged as price levels.
MULTI_SKU_SOURCES = (
    "dmart_ahmedabad", "vishal_diary", "district_cinema", "fresha_salon", "rajkot_shops", "doca_rajkot",
)
# Genuine retail-price series at the Rajkot centre or Rajkot web shops. These are gated
# separately from direct administered/spot prices and from non-local proxy sources.
RETAIL_SOURCES = ("doca_rajkot", "rajkot_shops")
MODELLED_SOURCES = ("rent_signal", "rent_listings")
GATED_SOURCES = PROXY_SOURCES + RETAIL_SOURCES + MODELLED_SOURCES
# Regulated ceilings/rate cards are not observed paid prices; count them as proxies.
PROXY_ITEMS = ("M001", "T004", "D002")

MIN_OVERLAP, MIN_CORR, MAX_DRIFT = 6, 0.5, 0.10
MIN_B_PAIRS = 3
LEVEL_MONTHS, DRIFT_MONTHS = 24, 24
MIN_CORR_12M, MIN_R2, SLOPE_LO, SLOPE_HI = 0.5, 0.5, 0.5, 1.5
SPLICED_CSV = "data/official/official_item_spliced.csv"


def _monthly(series: pd.Series) -> pd.Series:
    """Return a positive numeric series indexed by unique calendar months."""
    s = pd.Series(series).copy()
    if isinstance(s.index, pd.PeriodIndex):
        idx = s.index.asfreq("M")
    else:
        idx = pd.PeriodIndex(pd.to_datetime(s.index, errors="raise"), freq="M")
    vals = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
    out = pd.Series(vals, index=idx, dtype=float)
    return out.groupby(level=0).mean().sort_index()


def judge(proxy: pd.Series, official: pd.Series) -> dict:
    """Pure gate: monthly level series indexed by calendar month -> auditable verdict."""
    p = _monthly(proxy).rename("p")
    o = _monthly(official).rename("o")
    both = pd.concat([p, o], axis=1).sort_index()
    both = both.where((both > 0).all(axis=1))
    valid = both.dropna()
    n = len(valid)
    out = {
        "n_overlap": int(n), "corr": None, "drift": None, "verdict": "pending",
        "corr_12m": None, "r2": None, "slope": None, "drift_recent": None,
        "legs": [], "leg_status": {"A": "pending", "B": "pending", "C": "pending"},
    }
    if n < MIN_OVERLAP:
        return out

    # Reindex to an unbroken monthly calendar before differencing. A missing month must
    # not turn a two-month (or 13-month) move into a one-month (or 12-month) change.
    months = pd.period_range(valid.index.min(), valid.index.max(), freq="M")
    lg = np.log(both.reindex(months))
    changes = lg.diff().dropna()
    corr = float(changes["p"].corr(changes["o"])) if (
        len(changes) >= 2 and changes["p"].std() > 0 and changes["o"].std() > 0
    ) else float("nan")
    drift = float(abs(
        (np.log(valid["p"].iloc[-1]) - np.log(valid["p"].iloc[0]))
        - (np.log(valid["o"].iloc[-1]) - np.log(valid["o"].iloc[0]))
    ))
    out.update(corr=round(corr, 2) if np.isfinite(corr) else None, drift=round(drift, 3))
    leg_a = bool(np.isfinite(corr) and corr >= MIN_CORR and drift <= MAX_DRIFT)
    if len(changes) >= 2:
        out["leg_status"]["A"] = "pass" if leg_a else "fail"

    leg_b = False
    leg_c = False
    # B has no 24-level floor: it needs enough paired calendar-aligned annual changes
    # to estimate a correlation. C's 24-month minimum is separate and remains explicit.
    annual = lg.diff(12).dropna()
    if len(annual) >= MIN_B_PAIRS:
        corr12 = float(annual["p"].corr(annual["o"])) if (
            annual["p"].std() > 0 and annual["o"].std() > 0
        ) else float("nan")
        out["corr_12m"] = round(corr12, 2) if np.isfinite(corr12) else None
        leg_b = bool(np.isfinite(corr12) and corr12 >= MIN_CORR_12M)
        out["leg_status"]["B"] = "pass" if leg_b else "fail"

    if n >= LEVEL_MONTHS:
        x = np.log(valid["o"].to_numpy(dtype=float))
        y = np.log(valid["p"].to_numpy(dtype=float))
        if len(x) >= LEVEL_MONTHS and np.std(x) > 0 and np.std(y) > 0:
            slope = float(np.polyfit(x, y, 1)[0])
            fitted = np.polyval(np.polyfit(x, y, 1), x)
            ss_tot = float(((y - y.mean()) ** 2).sum())
            r2 = float(1 - ((y - fitted) ** 2).sum() / ss_tot) if ss_tot > 0 else float("nan")
            end = valid.index.max()
            start = end - DRIFT_MONTHS
            drift_recent = None
            if start in lg.index and end in lg.index and lg.loc[[start, end]].notna().all(axis=None):
                drift_recent = float(abs(
                    (lg.loc[end, "p"] - lg.loc[start, "p"])
                    - (lg.loc[end, "o"] - lg.loc[start, "o"])
                ))
            out.update(
                r2=round(r2, 3) if np.isfinite(r2) else None,
                slope=round(slope, 3) if np.isfinite(slope) else None,
                drift_recent=round(drift_recent, 3) if drift_recent is not None else None,
            )
            # If the exact month 24 months before the end is absent, the recent-drift
            # leg is not yet testable. Do not turn a calendar-coverage gap into a fail.
            if drift_recent is not None:
                leg_c = bool(
                    np.isfinite(r2) and r2 >= MIN_R2
                    and np.isfinite(slope) and SLOPE_LO <= slope <= SLOPE_HI
                    and drift_recent <= MAX_DRIFT
                )
                out["leg_status"]["C"] = "pass" if leg_c else "fail"
        else:
            out["leg_status"]["C"] = "fail"

    legs = [name for name, passed in (("A", leg_a), ("B", leg_b), ("C", leg_c)) if passed]
    out["legs"] = legs
    # A pass is decisive. With no pass, a still-unevaluable leg keeps the overall
    # result pending; a definitive fail requires every applicable leg to be evaluated.
    statuses = out["leg_status"].values()
    out["verdict"] = "pass" if legs else ("pending" if "pending" in statuses else "fail")
    return out


def judge_monthly(proxy: pd.Series, official: pd.Series) -> dict:
    """Evaluate the legacy monthly-A screen only (used by diagnostics explicitly preregistered on A).

    Production proxy validation uses :func:`judge` and its full A/B/C policy. Some model
    and candidate-source screens were defined in advance as monthly-correlation tests;
    retain that estimand without allowing new B/C legs to silently change their meaning.
    """
    out = judge(proxy, official)
    a = out["leg_status"]["A"]
    out["verdict"] = a
    out["legs"] = ["A"] if a == "pass" else []
    out["leg_status"] = {"A": a, "B": "n/a", "C": "n/a"}
    out["gate_type"] = "A-only monthly screen"
    return out


def chain_series(piv: pd.DataFrame) -> pd.Series:
    """Months x SKUs unit-price table -> matched-model Jevons level series (first month = 100)."""
    lg = np.log(piv.astype(float).where(piv > 0))
    step = lg.diff().mean(axis=1, skipna=True)
    lvl = 100.0 * np.exp(step.fillna(0.0).cumsum())
    lvl[step.isna() & (lvl.index != lvl.index[0])] = np.nan
    return lvl


def official_series(official_csv, spliced_csv: str | None = None) -> pd.DataFrame:
    """Load the required long comparator, indexed by basket item id and month."""
    raw_path = Path(official_csv).resolve()
    splice_path = Path(spliced_csv) if spliced_csv else raw_path.with_name(Path(SPLICED_CSV).name)
    if not splice_path.is_file():
        raise FileNotFoundError(
            f"long official comparator missing: {splice_path}; rebuild it with scripts/build_official_spliced.py"
        )
    d = pd.read_csv(splice_path, dtype={"item_id": str, "period": str})
    required = {"item_id", "period", "index_value"}
    if not required.issubset(d.columns):
        raise ValueError(f"{splice_path} must contain {sorted(required)}")
    return d.pivot_table(index="period", columns="item_id", values="index_value", aggfunc="first").sort_index()


def validate_proxies(
    conn, official_csv, mapping_csv, plan_csv, series_out: dict | None = None, spliced_csv=None,
) -> list[dict]:
    """Validate only each item's active primary source against the long spliced comparator."""
    plan = pd.read_csv(plan_csv, dtype=str, keep_default_na=False).set_index("item_id")
    off = official_series(official_csv, spliced_csv=spliced_csv)
    items = plan.loc[plan.primary_source.isin(GATED_SOURCES)].index.tolist()
    res = []
    for it in items:
        source = plan.loc[it, "primary_source"]
        if source in MULTI_SKU_SOURCES:
            sk = pd.read_sql_query(
                """SELECT o.sku_id AS sku, substr(o.obs_date,1,7) AS m, AVG(o.unit_price) AS v
                   FROM observations o JOIN products p ON p.sku_id=o.sku_id
                   WHERE p.item_id=? AND p.source_id=? AND {} GROUP BY 1,2""".format(sql_clause("p")),
                conn, params=[it, source],
            )
            proxy = chain_series(sk.pivot(index="m", columns="sku", values="v").sort_index()) if len(sk) else pd.Series(dtype=float)
        else:
            q = pd.read_sql_query(
                """SELECT substr(o.obs_date,1,7) AS m, AVG(o.unit_price) AS v
                   FROM observations o JOIN products p ON p.sku_id=o.sku_id
                   WHERE p.item_id=? AND p.source_id=? AND {} GROUP BY 1""".format(sql_clause("p")),
                conn, params=[it, source],
            )
            proxy = q.set_index("m")["v"] if len(q) else pd.Series(dtype=float)

        official = off[it].dropna() if it in off.columns else pd.Series(dtype=float)
        if series_out is not None:
            series_out[it] = (proxy, official, source)
        common = {"proxy_months": int(len(proxy)),
                  "official_months_after_proxy_start": int(sum(1 for m in official.index if len(proxy) and m >= str(proxy.index.min())))}
        if source in MODELLED_SOURCES:
            from .rentsignal import judge_trend
            res.append({"item_id": it, "source_id": source, **judge_trend(proxy, official), **common,
                        "gate_type": "trend", "legs": [],
                        "leg_status": {"A": "n/a", "B": "n/a", "C": "n/a"}})
        else:
            res.append({"item_id": it, "source_id": source, **judge(proxy, official), **common, "gate_type": "A/B/C"})
    return res
