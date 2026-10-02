"""Event-driven tracker for administered prices (Tier C): electricity, LPG, petrol, fares, fees...

You (or a scraper + human-confirm step) record each tariff *change* once:
    item_id, effective_from, price, verified_by, source_url
This collector expands the events into one time-weighted average price per month,
so a mid-month change enters each month in proportion to the days it applied.
"""
from __future__ import annotations
import calendar
import datetime as dt
import pandas as pd
from .base import Collector, Observation


def expand_events(events: pd.DataFrame, through: dt.date, source_id: str = "tariff") -> list[Observation]:
    out = []
    if events.empty:
        return out
    ev = events.copy()
    ev["effective_from"] = pd.to_datetime(ev["effective_from"]).dt.date
    # Optional `series` column: several parallel administered series for one item (e.g. two operators' plans). Blank = the
    # item's single series. Each series becomes its own SKU, and the item index is their Jevons mean.
    ev["series"] = (ev["series"] if "series" in ev.columns else pd.Series("", index=ev.index)).fillna("").astype(str).str.strip()
    for (item_id, series), g in ev.groupby(["item_id", "series"]):
        sku = item_id if not series else f"{item_id}:{series}"
        g = g.sort_values("effective_from", kind="stable")
        first = g["effective_from"].iloc[0]
        y, m = first.year, first.month
        while (y, m) <= (through.year, through.month):
            ndays = calendar.monthrange(y, m)[1]
            last_day = min(ndays, through.day) if (y, m) == (through.year, through.month) else ndays
            vals = []
            for d in range(1, last_day + 1):
                day = dt.date(y, m, d)
                prior = g[g["effective_from"] <= day]
                if not prior.empty:
                    vals.append(float(prior["price"].iloc[-1]))
            if vals:
                out.append(Observation(
                    obs_date=dt.date(y, m, 1), source_id=source_id, source_sku=sku,
                    title=f"{sku} administered price (time-weighted monthly avg)",
                    item_id=item_id, pincode="RJT", price=sum(vals) / len(vals)))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


USABLE_STATUSES = {"verified", "corroborated", "derived", "scraped"}      # 'unverified' and 'rejected' NEVER enter the index


def load_usable_events(path) -> pd.DataFrame:
    """Read the events file and keep only rows whose provenance status allows use. Strict: a file without a
    `status` column is refused rather than silently trusted."""
    ev = pd.read_csv(path)
    if ev.empty:
        return ev
    if "status" not in ev.columns:
        raise ValueError(f"{path}: no `status` column - every tariff event must carry a verification status")
    bad = set(ev["status"].str.strip().str.lower()) - USABLE_STATUSES - {"unverified", "rejected"}
    if bad:
        raise ValueError(f"{path}: unknown status values {sorted(bad)}")
    return ev[ev["status"].str.strip().str.lower().isin(USABLE_STATUSES)].copy()


class TariffEventCollector(Collector):
    source_id = "tariff"

    def __init__(self, path):
        self.path = path

    def collect(self, on_date: dt.date):
        yield from expand_events(load_usable_events(self.path), on_date, self.source_id)
