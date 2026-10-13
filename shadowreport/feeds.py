"""Registry and loaders for the shadow feeds.

Each feed is a shadow source: its quotes are collected and stored, but they do not feed the published index
until a recorded switch passes the gate (see rpi/shadow.py). This module only reads them and compares each one
with its actual reference, where one exists.

Feed kinds
    price    one quote per row with a 'date' column and a unit price; compared with a dated reference price (tariff)
    gate     per-item gate verdicts already computed by rpi/shadow.py (data/official/shadow_sources.json)
    rent     monthly asking-rent listings (data/rent_listings.csv); compared with the official house-rent series
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Feed:
    id: str
    label: str
    kind: str                       # price | gate | rent
    path: str                       # relative to the repo root
    item: str | None                # item id the feed prices, or None when it covers several items
    reference: str | None           # human-readable name of the actual reference, None when there is none
    freshness_days: int = 14        # a feed whose last quote is older than this is 'stale'
    notes: str = ""
    active: bool = True             # False = the source is known to be closed; reported as 'inactive', not an alarm


FEEDS: tuple[Feed, ...] = (
    Feed("onemg_calpol", "1mg Calpol 500 tablet (M001)", "price", "data/onemg_prices.csv", "M001",
         "NPPA ceiling price (data/tariff_events.csv, M001)",
         notes="Per-tablet unit price, in-stock listings only. M001 stays on the tariff."),
    Feed("hathway_k003", "Hathway broadband (K003)", "price", "data/hathway_broadband_prices.csv", "K003", None,
         notes="Plan price, no actual reference series."),
    Feed("apple_k002", "Apple iPhone 16 (K002)", "price", "data/apple_store_prices.csv", "K002", None,
         notes="Single SKU, no actual reference series."),
    Feed("green_mercado", "Green Mercado (store closed)", "price", "data/green_mercado_prices.csv", None, None,
         active=False, notes="Store closed; no quotes expected."),
    Feed("rajkot_shops", "Rajkot web shops", "gate", "data/rajkot_shops_prices.csv", None,
         "official item index (gate in data/official/shadow_sources.json)"),
    Feed("rent_listings", "Rent listings panel (R001)", "rent", "data/rent_listings.csv", "R001",
         "official house-rent series (CPI 04.1.1.0.2.01)",
         notes="Median asking rent by listing month, not the hedonic index."),
)

# Report band for price feeds with a reference. A report threshold, not a gate: it only sorts feeds into
# 'tracking' or 'out_of_band' for reading. Changing it does not change any index or switch.
PRICE_BAND_PCT = 10.0
# Minimum overlap months before a rent comparison is judged (the same 6-month rule rpi/shadow.py uses).
MIN_OVERLAP_MONTHS = 6

# Worst first. The overall status of a run is the first of these that any feed has.
SEVERITY = ("fail", "out_of_band", "stale", "no_quotes", "pending", "tracking", "pass")


def _read(root: Path, rel: str) -> pd.DataFrame:
    p = root / rel
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, dtype=str, keep_default_na=False)


def tariff_price_at(root: Path, item: str, when: str) -> tuple[float | None, str | None]:
    """Latest dated tariff for an item on or before `when` (YYYY-MM-DD). Returns (price, effective_from)."""
    t = _read(root, "data/tariff_events.csv")
    if t.empty:
        return None, None
    t = t[t.item_id == item]
    t = t[t.effective_from <= when]
    if t.empty:
        return None, None
    last = t.sort_values("effective_from").iloc[-1]
    return float(last.price), last.effective_from


def price_rows(root: Path, feed: Feed, as_of: dt.date) -> list[dict]:
    """Per-quote comparison for a price feed: the shadow unit price against the reference on the quote date."""
    df = _read(root, feed.path)
    if df.empty:
        return []
    price_col = "unit_price" if "unit_price" in df.columns else "price"
    rows = []
    for r in df.itertuples():
        date = str(getattr(r, "date", ""))[:10]
        try:
            px = float(getattr(r, price_col))
        except (TypeError, ValueError):
            continue
        ref, eff = (tariff_price_at(root, feed.item, date) if (feed.item and feed.reference) else (None, None))
        gap = None if not ref else round(100 * (px / ref - 1), 2)
        rows.append(dict(date=date, price=px, reference=ref, reference_effective=eff, gap_pct=gap))
    return rows


def gate_rows(root: Path) -> list[dict]:
    """Per-item gate verdicts for the Rajkot web-shop candidates, read from the shadow screen (not recomputed here)."""
    import json
    p = root / "data/official/shadow_sources.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    out = []
    for src, cand in d.get("candidates", {}).items():
        for it in cand.get("items", []):
            g = it.get("gate_vs_official", {})
            out.append(dict(source=src, item_id=it.get("item_id"), name=it.get("name"), verdict=g.get("verdict", "pending"),
                            n_overlap=g.get("n_overlap", 0), status=it.get("status", "")))
    return out


def rent_monthly(root: Path) -> pd.Series:
    """Median asking rent by listing month over the cleaned panel (Rs per month)."""
    from rpi.collectors import rent_listings as rl
    df = _read(root, "data/rent_listings.csv")
    if df.empty:
        return pd.Series(dtype=float)
    df = df.assign(rent=pd.to_numeric(df.rent, errors="coerce"), bhk=pd.to_numeric(df.bhk, errors="coerce"),
                   month=df.listed.str[:7])
    df = df.dropna(subset=["rent", "month"])
    clean = rl.clean(df)
    return clean.groupby("month").rent.median().sort_index()


def official_rent_monthly(root: Path) -> pd.Series:
    from rpi import rentsignal
    return rentsignal.official_rent(root).astype(float).sort_index()


def as_of_date(value: str | None) -> dt.date:
    return dt.date.fromisoformat(value) if value else dt.date.today()
