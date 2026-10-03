"""Index engine: builds all variants, stores results as a new immutable vintage."""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .panel import load_quotes, quotes_to_arrays
from .elementary import rel_from_lp
from .geks import geks_rel
from .aggregate import aggregate, rebase
from .uncertainty import bootstrap_total

VARIANTS = {
    "jevons_chain": dict(field="unit_price", method="chain"),     # headline
    "geks_jevons": dict(field="unit_price", method="geks"),       # chain-drift check
    "regular_price": dict(field="regular_unit_price", method="chain"),  # promo-free check
}


@dataclass
class VariantResult:
    total: pd.Series
    divisions: pd.DataFrame
    items: pd.DataFrame
    coverage: pd.Series
    coverage_by_tier: pd.DataFrame
    imputed: pd.DataFrame
    lo: pd.Series | None = None
    hi: pd.Series | None = None


@dataclass
class IndexRun:
    run_id: str
    is_demo: bool
    weights_source: str
    variants: dict = field(default_factory=dict)


def _load_ref(conn):
    items = pd.read_sql_query("SELECT * FROM items", conn)
    w = pd.read_sql_query("SELECT * FROM weights", conn)
    if items.empty or w.empty:
        raise RuntimeError("basket/weights not loaded - run `rpi init` first")
    return items, w.set_index("item_id")["weight"], w["weight_source"].iloc[0]


# dmart_ahmedabad is a multi-SKU pool but min_matched=1: a SKU that is out of stock for a month must not make the whole item imputed.
SINGLE_SERIES_SOURCES = ("official_link", "gr_metals", "mandi_gondal", "gr_png", "necc_ahmedabad", "mandi_rajkot_apmc", "mandi_rajkot_veg", "yard_rajkot_board", "mandi_rajkot_district", "doca_rajkot", "doca_national", "doca_gujarat", "dmart_ahmedabad", "tariff")


def price_update_weights(weights: pd.Series, wsrc: str, base_period: str, official_csv=None, mapping_csv=None):
    """Lowe-style price update: w_i' = w_i * (official item index at the base month / 100).

    MoSPI weights are 2024 expenditure shares; a Young index from a LATER base (e.g. Jan 2025) with the raw 2024
    weights understates items that rose a lot in between (gold/silver +60-150%). The official item indices tell us how
    far each item moved from 2024 to the base month, so weights are rolled forward. Items without an official item
    keep factor 1. Returns (weights, label)."""
    from ..config import ROOT as _R
    official_csv = official_csv or _R / "data/official/mospi_cpi2024_gujarat_urban.csv"
    mapping_csv = mapping_csv or _R / "data/basket_official_map.csv"
    if not base_period or not (official_csv.exists() and mapping_csv.exists()):
        return weights, wsrc
    off = pd.read_csv(official_csv, dtype={"code": str})
    it = off[(off.level == "item") & (off.period.astype(str) == base_period)].set_index("code")["index_value"]
    if it.empty:
        return weights, wsrc
    mp = pd.read_csv(mapping_csv, dtype=str, keep_default_na=False).set_index("item_id")["official_item_code"]
    f = mp.reindex(weights.index).map(lambda c: float(it.get(c, 100.0)) / 100.0 if c else 1.0).fillna(1.0)
    w2 = weights * f
    w2 = w2 / w2.sum() * weights.sum()
    return w2, f"{wsrc} | price-updated to {base_period} with official item indices"


def _is_demo(conn, weights_source: str) -> bool:
    src = [r[0] for r in conn.execute(
        "SELECT DISTINCT p.source_id FROM observations o JOIN products p USING(sku_id)")]
    return weights_source.upper().startswith("DEMO") or any(s.startswith("synthetic") for s in src)


def run_index(conn, settings: dict, store: bool = True) -> IndexRun:
    cfg = settings["index"]
    items, weights, wsrc = _load_ref(conn)
    _bp = settings.get("project", {}).get("base_period", "")
    if _bp and not wsrc.upper().startswith("DEMO"):
        weights, wsrc = price_update_weights(weights, wsrc, _bp)
    run = IndexRun(run_id=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
                   is_demo=_is_demo(conn, wsrc), weights_source=wsrc)
    clip = cfg["max_abs_log_change"]
    by_tier = cfg.get("min_matched_by_tier", {})
    min_m = items.set_index("item_id")["tier"].map(lambda t: by_tier.get(t, cfg["min_matched"])).astype(int)
    # Items fed by ONE series per month by design (official-linked stand-ins, administered tariffs, PNG, daily single-feed
    # sources) legitimately have a single quote: min_matched=1. Synthetic/demo runs keep the strict per-tier rule.
    from ..config import ROOT as _ROOT
    _plan = _ROOT / "data" / "source_plan.csv"
    if _plan.exists() and not run.is_demo:
        import pandas as _pd
        _p = _pd.read_csv(_plan, dtype=str, keep_default_na=False)
        _lk = [i for i in _p.loc[_p["primary_source"].isin(SINGLE_SERIES_SOURCES), "item_id"] if i in min_m.index]
        min_m.loc[_lk] = 1

    for name, v in VARIANTS.items():
        q = load_quotes(conn, v["field"], cfg["min_days_per_month"], cfg.get("min_days_by_source"))
        # Quotes before the configured base month (e.g. register events dated 2024-10) would stretch the panel with leading
        # months that carry one item only; they cannot influence an index rebased to the base month, only break variants.
        if _bp and not run.is_demo and not q.empty:
            q = q[q["period"] >= pd.Period(_bp, "M")]
        if q.empty:
            raise RuntimeError("no observations in database")
        periods = pd.period_range(q["period"].min(), q["period"].max(), freq="M")
        arrays = quotes_to_arrays(q, periods)
        rel = pd.DataFrame(np.nan, index=periods, columns=weights.index)
        n = pd.DataFrame(0, index=periods, columns=weights.index)
        for it, lp in arrays.items():
            if it not in rel.columns:
                continue
            if v["method"] == "chain":
                r, k = rel_from_lp(lp, int(min_m[it]), clip)
            else:
                r, k = geks_rel(lp, cfg["geks_window"], int(min_m[it]))
            rel[it], n[it] = r, k
        agg = aggregate(rel, n, items, weights, min_m, impute=cfg.get("impute", "division"))
        _cfg_base = settings["project"].get("base_period")
        # demo/synthetic data has its own timeline; real runs must hit the configured base month (error if absent)
        base = pd.Period(_cfg_base, "M") if (_cfg_base and not (run.is_demo and pd.Period(_cfg_base, "M") not in periods)) \
            else periods[0]
        res = VariantResult(
            total=rebase(agg["total"], base), divisions=rebase(agg["divisions"], base),
            items=rebase(agg["items"], base), coverage=agg["coverage"],
            coverage_by_tier=agg["coverage_by_tier"], imputed=agg["imputed"])
        if name == "jevons_chain":
            lo, hi = bootstrap_total(arrays, periods, items, weights, cfg["bootstrap_reps"],
                                     min_matched=min_m, clip=clip, impute=cfg.get("impute", "division"))
            lo, hi = lo / agg["total"].loc[base] * 100, hi / agg["total"].loc[base] * 100
            res.lo, res.hi = lo, hi
        run.variants[name] = res
    if store:
        _store(conn, run)
    return run


def _store(conn, run: IndexRun):
    rows = []
    for name, v in run.variants.items():
        for p, val in v.total.items():
            lo = v.lo.get(p) if v.lo is not None else None
            hi = v.hi.get(p) if v.hi is not None else None
            rows.append((run.run_id, name, str(p), "total", "ALL", float(val), lo, hi))
        for d in v.divisions.columns:
            for p, val in v.divisions[d].items():
                rows.append((run.run_id, name, str(p), "division", d, float(val), None, None))
        for it in v.items.columns:
            for p, val in v.items[it].items():
                rows.append((run.run_id, name, str(p), "item", it, float(val), None, None))
    conn.executemany("INSERT INTO index_results VALUES(?,?,?,?,?,?,?,?)", rows)
    diag = []
    for name, v in run.variants.items():
        for p, val in v.coverage.items():
            diag.append((run.run_id, name, str(p), "weight_coverage", "ALL", float(val)))
        for t in v.coverage_by_tier.columns:
            for p, val in v.coverage_by_tier[t].items():
                diag.append((run.run_id, name, str(p), "weight_coverage_tier", t, float(val)))
    conn.executemany("INSERT INTO index_diagnostics VALUES(?,?,?,?,?,?)", diag)
    conn.execute("INSERT INTO index_runs VALUES(?,?,?,?,?)",
                 (run.run_id, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                  int(run.is_demo), run.weights_source, ""))
    conn.commit()


def inflation_table(total: pd.Series) -> pd.DataFrame:
    t = pd.DataFrame({"index": total})
    t["mom_pct"] = total.pct_change() * 100
    t["ann3m_pct"] = ((total / total.shift(3)) ** 4 - 1) * 100
    t["yoy_pct"] = total.pct_change(12) * 100
    return t
