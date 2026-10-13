"""Comparison and status rules. Pure functions: no file or network access, so they are easy to test."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .feeds import MIN_OVERLAP_MONTHS, PRICE_BAND_PCT, SEVERITY, Feed


def days_since(last: str | None, as_of: dt.date) -> int | None:
    if not last:
        return None
    return (as_of - dt.date.fromisoformat(last[:10])).days


def price_summary(rows: list[dict], feed: Feed, as_of: dt.date) -> dict:
    """Summary of a price feed. `rows` are per-quote dicts from feeds.price_rows()."""
    n = len(rows)
    dates = sorted(r["date"] for r in rows if r["date"])
    last = dates[-1] if dates else None
    gaps = [r["gap_pct"] for r in rows if r["gap_pct"] is not None]
    out = dict(n_quotes=n, first_quote=dates[0] if dates else None, last_quote=last,
               days_since_last=days_since(last, as_of), n_with_reference=len(gaps),
               latest_price=rows[-1]["price"] if rows else None,
               latest_gap_pct=gaps[-1] if gaps else None,
               mean_gap_pct=round(float(np.mean(gaps)), 2) if gaps else None)
    return out


def rent_comparison(shadow: pd.Series, official: pd.Series, min_months: int = MIN_OVERLAP_MONTHS) -> dict:
    """Shadow (median asking rent by month) against the official house-rent index, over the months both have.

    The overlap is judged with the trend gate in rpi.rentsignal, the same test R001 uses. Below `min_months` the
    comparison is reported but not judged."""
    from rpi.rentsignal import trend_gate
    both = pd.concat([shadow.rename("p"), official.rename("o")], axis=1).dropna().sort_index()
    n = len(both)
    out = dict(n_overlap_months=n, overlap=[both.index[0], both.index[-1]] if n else None,
               judged=False, verdict="pending", gap_cum_pp=None, gap_12m_pp=None, tol_cum_pp=None, tol_12m_pp=None)
    if n < 2:
        return out
    gap = (np.log(both.p.iloc[-1]) - np.log(both.p.iloc[0]) - (np.log(both.o.iloc[-1]) - np.log(both.o.iloc[0]))) * 100
    out["gap_cum_pp"] = round(float(gap), 2)
    if n < min_months:
        return out
    g = trend_gate(shadow, official)
    out.update(judged=True, verdict=g["verdict"], gap_cum_pp=g["gap_cum_pp"], gap_12m_pp=g["gap_12m_pp"],
               tol_cum_pp=g["tol_cum_pp"], tol_12m_pp=g["tol_12m_pp"])
    return out


def feed_status(feed: Feed, summary: dict) -> str:
    """One status per feed. Priority: a judged failure beats everything; a feed with no quotes is 'no_quotes'."""
    if not feed.active:
        return "inactive"
    if summary.get("n_quotes", 0) == 0 and feed.kind != "gate":
        return "no_quotes"
    if summary.get("judged_verdict") == "fail":
        return "fail"
    if summary.get("judged_verdict") == "pass":
        return "pass"
    days = summary.get("days_since_last")
    if days is not None and days > feed.freshness_days:
        return "stale"
    if feed.kind == "price":
        if summary.get("n_with_reference", 0) == 0:
            return "pending"
        gap = summary.get("latest_gap_pct")
        if gap is not None and abs(gap) > PRICE_BAND_PCT:
            return "out_of_band"
        return "tracking"
    return "pending"


def overall(statuses: list[str]) -> str:
    present = set(statuses) - {"inactive"}          # a known-closed source is not a problem
    for s in SEVERITY:
        if s in present:
            return s
    return "inactive" if statuses else "pending"
