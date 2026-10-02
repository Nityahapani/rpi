"""Fixed-SKU list-price tracker for Jockey India men's apparel (items C001 shirts/T-shirts, C002 trousers/track pants/shorts).

History comes from dated Internet Archive snapshots of each product page (scripts/build_mrp_history.py); from then on the daily refresh
reads the live Shopify product JSON (robots.txt allows /products.json) and records a new dated event whenever a pool SKU's price changed.
Events live in data/tariff_events.csv as one series per SKU ('jockey:<sku>'); the item index is the Jevons mean of the SKU series.

Carry-forward rule: a price holds until the next observation that shows a different price; the step is dated at the first snapshot that shows
the new price (so a change date is never earlier than the evidence).  Sizes: M only (Jockey prices some sizes differently).
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

BASE = dt.date(2025, 1, 1)
ARCHIVE = "data/mrp/jockey_archive_prices.csv"
POOL = "data/mrp/jockey_candidates.csv"
SRC = "https://www.jockey.in/products/"


def _mid(d0: dt.date, d1: dt.date) -> dt.date:
    return d0 + (d1 - d0) / 2


def events_from_archive(archive: pd.DataFrame, today: dt.date | None = None, live: dict | None = None) -> list[dict]:
    """Archive snapshot rows (item_id, handle, sku, ts, price) [+ live {sku: price}] -> register rows.  Pure.

    Interval-censored dating: when two consecutive observations differ, the change happened somewhere between them; it is dated at the
    MIDPOINT of that bracket (status 'derived', bracket stated in the note).  A price change is never dated by the live scrape's own day
    unless the previous observation was that day or the day before."""
    today = today or dt.date.today()
    rows = []
    for (item, sku, handle), g in archive.groupby(["item_id", "sku", "handle"]):
        g = g.assign(d=pd.to_datetime(g.ts.astype(str).str[:8], format="%Y%m%d").dt.date).sort_values("d")
        pre = g[g.d <= dt.date(2025, 1, 31)]
        base = pre.iloc[-1] if len(pre) else g.iloc[0]
        kw = dict(item_id=item, series=f"jockey:{sku}", source_class="retailer list price (Internet Archive snapshots of the product page)", source_url=SRC + handle)
        rows.append(dict(effective_from=BASE.isoformat(), price=float(base.price), status="scraped" if len(pre) else "derived",
                         note=f"Wayback snapshot {base.ts}" + ("" if len(pre) else " is after the base month; price carried back (unverified before it)"), **kw))
        obs = [(r.d, float(r.price), str(r.ts)) for r in g[g.d > base.d].itertuples()]
        if live is not None and str(sku) in live:
            obs.append((today, float(live[str(sku)]), "live"))
        last_d, last_p = base.d, float(base.price)
        for d, p, tag in obs:
            if p != last_p:
                eff = max(_mid(last_d, d), BASE)
                rows.append(dict(effective_from=eff.isoformat(), price=p, status="derived" if (d - last_d).days > 2 else "scraped",
                                 note=f"{last_p:g} on {last_d} -> {p:g} on {d} ({'live feed' if tag == 'live' else 'Wayback ' + tag}); change dated at the midpoint of the "
                                      f"{(d - last_d).days}-day bracket", **kw))
            last_d, last_p = d, p
    return rows


def parse_live(products: list[dict]) -> dict[str, tuple[float, str]]:
    """Shopify /products.json products -> {sku: (price, handle)} for size-M variants."""
    out = {}
    for p in products:
        for v in p.get("variants", []):
            if v.get("option1") == "M" and v.get("sku"):
                out[str(v["sku"])] = (float(v["price"]), p["handle"])
    return out


def live_updates(events: pd.DataFrame, pool: pd.DataFrame, live: dict, today: dt.date) -> tuple[list[dict], list[str]]:
    """New events for pool SKUs whose live price differs from their latest recorded price; warnings for SKUs missing from the feed."""
    new, warn = [], []
    ev = events.assign(d=pd.to_datetime(events.effective_from).dt.date).sort_values("d", kind="stable")
    for c in pool.itertuples():
        ser = f"jockey:{c.sku}"
        g = ev[(ev.item_id == c.item_id) & (ev.series == ser)]
        if g.empty:
            continue
        if str(c.sku) not in live:
            warn.append(f"{c.sku} missing from live feed")
            continue
        price = live[str(c.sku)][0]
        if float(g.price.iloc[-1]) != price:
            new.append(dict(item_id=c.item_id, series=ser, effective_from=today.isoformat(), price=price, status="scraped",
                            source_class="retailer list price (live product JSON)", source_url=SRC + live[str(c.sku)][1],
                            retrieved=today.isoformat(), note=f"live price changed from {g.price.iloc[-1]:g}"))
    return new, warn


def monthly_index(events: pd.DataFrame, item_id: str, through: dt.date) -> pd.Series:
    """Jevons mean over the item's SKU series of price relative to each SKU's own price in the base month, index 'YYYY-MM'.  Pure."""
    from .tariff_events import expand_events
    ev = events[(events.item_id == item_id) & events.series.fillna("").str.startswith("jockey:")]
    obs = expand_events(ev, through)
    df = pd.DataFrame([(o.source_sku, o.obs_date.strftime("%Y-%m"), o.price) for o in obs], columns=["sku", "m", "p"])
    if df.empty:
        return pd.Series(dtype=float)
    base = df[df.m == "2025-01"].set_index("sku").p
    df = df[df.sku.isin(base.index)]
    df["rel"] = df.p / df.sku.map(base)
    import numpy as np
    return (df.groupby("m").rel.apply(lambda x: float(np.exp(np.log(x).mean()))) * 100).sort_index()


def gate(events: pd.DataFrame, official_csv, mapping_csv, through: dt.date) -> list[dict]:
    """Same pass rule as the mandi/DoCA proxies (rpi.proxy_check.judge): corr of monthly changes >= 0.5 and cumulative drift <= 10 points."""
    from ..proxy_check import judge
    off = pd.read_csv(official_csv, dtype={"code": str})
    off = off[off.level == "item"].pivot_table(index="period", columns="code", values="index_value", aggfunc="first")
    mp = pd.read_csv(mapping_csv, dtype=str, keep_default_na=False).set_index("item_id")
    out = []
    for it in ("C001", "C002"):
        s = monthly_index(events, it, through)
        code = mp.loc[it, "official_item_code"]
        v = judge(s, off[code]) if len(s) else {"verdict": "pending", "n_overlap": 0, "corr": None, "drift": None}
        out.append(dict(item_id=it, n_skus=int(events[(events.item_id == it) & events.series.fillna("").str.startswith("jockey:")].series.nunique()),
                        last=round(float(s.iloc[-1]), 2) if len(s) else None, **v))
    return out
