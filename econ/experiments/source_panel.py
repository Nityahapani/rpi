"""Causal, source-only item panel for honest model validation.

This is deliberately not built from the published item-index levels. Published history can
contain official_link stand-ins and imputed relatives, and the GEKS variant is multilateral
inside its initial window (so early relatives can depend on later observations). Instead we
rebuild the headline chain-Jevons monthly relatives from eligible raw quotes, excluding
MoSPI ``official_link`` observations and leaving unsupported months missing.

The output is an archive-based research panel, not a claim that every archived input was
available in real time. ``max_input_fetched_at`` records the latest fetch timestamp among the
matched quote-months used for each change. Passing ``as_of`` drops observations fetched on or
after that UTC cutoff, allowing a conservative release-date replay when a real arrival date
is available.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from rpi.config import ROOT, load_settings
from rpi.index.elementary import rel_from_lp
from rpi.index.engine import min_matched_series
from rpi.superseded import sql_clause
from rpi.switches import clause as switch_clause

OFFICIAL_SPLICE = ROOT / "data" / "official" / "official_item_spliced.csv"
MAP_CSV = ROOT / "data" / "basket_official_map.csv"
WEIGHTS_CSV = ROOT / "data" / "weights_cpi2024_gujarat_urban.csv"
SOURCE_PLAN = ROOT / "data" / "source_plan.csv"


def _utc_cutoff(as_of: str | pd.Timestamp | None) -> pd.Timestamp | None:
    if as_of is None:
        return None
    t = pd.Timestamp(as_of)
    if t.tzinfo is None:
        # A date-only cutoff is exclusive from midnight UTC; same-day fetches are
        # conservatively excluded because the official release time is not recorded.
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t


def _quote_months(conn: sqlite3.Connection, *, as_of=None) -> pd.DataFrame:
    """Monthly geometric-mean log prices plus a fetch vintage for each active quote."""
    settings = load_settings()
    cfg = settings["index"]
    query = f"""SELECT o.obs_date, o.sku_id, o.pincode, o.unit_price AS price,
                       o.fetched_at, p.item_id, p.source_id
                FROM observations o JOIN products p ON p.sku_id=o.sku_id
                WHERE o.in_stock=1 AND o.unit_price>0 AND p.source_id<>'official_link'
                  AND {sql_clause('p')} AND {switch_clause('p', 'o')}"""
    raw = pd.read_sql_query(query, conn, parse_dates=["obs_date"])
    if raw.empty:
        return pd.DataFrame(columns=["item_id", "quote_id", "period", "lp", "n_days", "source_id", "fetched_at"])

    raw["fetched_at"] = pd.to_datetime(raw["fetched_at"], utc=True, errors="coerce")
    cutoff = _utc_cutoff(as_of)
    if cutoff is not None:
        raw = raw[raw.fetched_at.notna() & (raw.fetched_at < cutoff)].copy()
    if raw.empty:
        return pd.DataFrame(columns=["item_id", "quote_id", "period", "lp", "n_days", "source_id", "fetched_at"])

    raw["period"] = raw.obs_date.dt.to_period("M")
    base = settings.get("project", {}).get("base_period", "2025-01")
    raw = raw[raw.period >= pd.Period(base, freq="M")].copy()
    if raw.empty:
        return pd.DataFrame(columns=["item_id", "quote_id", "period", "lp", "n_days", "source_id", "fetched_at"])
    raw["quote_id"] = raw.sku_id.astype(str) + "|" + raw.pincode.fillna("").astype(str)
    raw["lp"] = np.log(pd.to_numeric(raw.price, errors="coerce"))
    q = raw.groupby(["item_id", "quote_id", "period"], as_index=False).agg(
        lp=("lp", "mean"), n_days=("lp", "size"), source_id=("source_id", "first"),
        fetched_at=("fetched_at", "max"),
    )
    min_days = cfg.get("min_days_by_source", {})
    need = q.source_id.map(lambda s: int(min_days.get(s, cfg.get("min_days_per_month", 1))))
    return q[q.n_days >= need].reset_index(drop=True)


def load_source_panel(*, as_of: str | pd.Timestamp | None = None) -> pd.DataFrame:
    """Build independent-source item changes matched to the spliced official item changes.

    Each row's ``x`` is an observed chain-Jevons relative (not an imputation), made only from
    non-official active source quotes. ``y`` is the official item change for the same month.
    Equal x/y values are retained: source eligibility is determined from provenance, never
    from the target residual. With ``as_of``, source observations fetched at/after the cutoff
    are excluded before monthly aggregation.
    """
    conn = sqlite3.connect(f"file:{ROOT / 'data' / 'rpi.sqlite'}?mode=ro", uri=True)
    try:
        q = _quote_months(conn, as_of=as_of)
        items = pd.read_sql_query("SELECT * FROM items", conn)
    finally:
        conn.close()
    if q.empty:
        return pd.DataFrame(columns=["period", "item_id", "quality", "weight", "x", "y", "n_matched", "source_ids", "max_input_fetched_at", "same_as_official"])

    settings = load_settings()
    cfg = settings["index"]
    min_matched = min_matched_series(items, cfg, is_demo=False, plan_csv=SOURCE_PLAN)
    periods = pd.period_range(q.period.min(), q.period.max(), freq="M")
    official = pd.read_csv(OFFICIAL_SPLICE, dtype={"item_id": str, "period": str})
    official["index_value"] = pd.to_numeric(official.index_value, errors="coerce")
    official = official.sort_values(["item_id", "period"])
    official["y"] = official.groupby("item_id").index_value.transform(lambda s: np.log(s).diff() * 100.0)
    official["period"] = official.period.astype(str)

    mapping = pd.read_csv(MAP_CSV, dtype=str, keep_default_na=False)
    mapping = mapping[mapping.match_quality.isin(["exact", "proxy", "blend"])][["item_id", "match_quality"]]
    weights = pd.read_csv(WEIGHTS_CSV, dtype={"item_id": str}).set_index("item_id").weight.astype(float)
    mapping["weight"] = mapping.item_id.map(weights)

    rows: list[dict] = []
    for item, g in q.groupby("item_id", sort=True):
        if item not in set(mapping.item_id):
            continue
        price = g.pivot(index="period", columns="quote_id", values="lp").reindex(periods)
        latest = g.pivot(index="period", columns="quote_id", values="fetched_at").reindex(index=periods, columns=price.columns)
        source_by_quote = g.drop_duplicates("quote_id").set_index("quote_id").source_id.to_dict()
        mm = int(min_matched.get(item, cfg.get("min_matched", 2)))
        rel, matched_n = rel_from_lp(price.to_numpy(dtype=float), mm, float(cfg["max_abs_log_change"]))
        px = price.to_numpy(dtype=float)
        ft = latest.to_numpy()
        for t in range(1, len(periods)):
            if not np.isfinite(rel[t]) or matched_n[t] < mm:
                continue
            matched = np.isfinite(px[t - 1]) & np.isfinite(px[t])
            if int(matched.sum()) < mm:
                continue
            used_times = [ft[t - 1, matched], ft[t, matched]]
            time_values = []
            complete_vintage = True
            for vals in used_times:
                for v in vals:
                    if pd.isna(v):
                        complete_vintage = False
                    else:
                        time_values.append(pd.Timestamp(v))
            latest_fetch = max(time_values).isoformat() if complete_vintage and time_values else None
            used_sources = sorted({source_by_quote[str(c)] for c, keep in zip(price.columns, matched) if keep})
            rows.append({
                "period": str(periods[t]), "item_id": item, "x": float(100.0 * rel[t]),
                "n_matched": int(matched_n[t]), "source_ids": "+".join(used_sources),
                "max_input_fetched_at": latest_fetch,
            })

    panel = pd.DataFrame(rows)
    if panel.empty:
        return panel
    panel = panel.merge(official[["period", "item_id", "y"]], on=["period", "item_id"], how="inner")
    panel = panel.merge(mapping.rename(columns={"match_quality": "quality"}), on="item_id", how="inner")
    panel["same_as_official"] = (panel.x - panel.y).abs() < 1e-6
    panel = panel.dropna(subset=["x", "y", "weight"]).sort_values(["period", "item_id"]).reset_index(drop=True)
    return panel[["period", "item_id", "quality", "weight", "x", "y", "n_matched", "source_ids", "max_input_fetched_at", "same_as_official"]]


def live_release_targets() -> pd.DataFrame:
    """Non-bootstrap official arrivals: the only release dates suitable for a strict vintage replay."""
    path = ROOT / "data" / "preregistered" / "official_seen.csv"
    if not path.exists():
        return pd.DataFrame(columns=["item_id", "period", "first_seen_on"])
    d = pd.read_csv(path, dtype={"item_id": str, "period": str})
    bootstrap = d.bootstrap.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})
    d = d[~bootstrap].copy()
    if d.empty:
        return pd.DataFrame(columns=["item_id", "period", "first_seen_on"])
    return d[["item_id", "period", "first_seen_on"]].drop_duplicates().sort_values(["period", "item_id"])
