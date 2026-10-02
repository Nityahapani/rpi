"""Keep data/tariff_events.csv current from live pages (event-driven Tier C).

Daily petrol/diesel: every cleaned day whose price differs from the previous day becomes a `scraped` event
(single feed -> never labelled `verified`). Estimated monthly-mean rows (`derived`) that overlap the scraped window are
replaced by the real daily values. LPG: a monthly table; a changed month becomes an event dated the 1st (exact day unknown).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from .collectors.web_sources import clean_outliers, parse_gr_daily_fuel, parse_gr_lpg_monthly

GR = {"T001": "https://www.goodreturns.in/petrol-price-in-rajkot.html",
      "T002": "https://www.goodreturns.in/diesel-price-in-rajkot.html",
      "R003": "https://www.goodreturns.in/lpg-price-in-rajkot.html"}
USABLE = {"verified", "corroborated", "derived", "scraped"}


def _row(item, date, price, note, url, today):
    return {"item_id": item, "effective_from": str(date), "price": round(float(price), 2), "status": "scraped",
            "source_class": "secondary (single feed)", "source_url": url, "retrieved": today.isoformat(), "note": note}


def update_events(ev: pd.DataFrame, pages: dict[str, str], today: dt.date) -> tuple[pd.DataFrame, list[str]]:
    """Return (new events frame, human-readable change log). Pure: no I/O."""
    ev = ev.copy()
    log: list[str] = []
    for item in ("T001", "T002"):
        if item not in pages:
            continue
        series = clean_outliers(parse_gr_daily_fuel(pages[item]))
        if not series:
            continue
        first = series[0][0]
        drop = ev[(ev.item_id == item) & (ev.status == "derived") & (pd.to_datetime(ev.effective_from).dt.date >= first)
                  & ev.note.fillna("").str.startswith("Monthly mean estimated")]
        if len(drop):
            ev = ev.drop(drop.index)
            log.append(f"{item}: replaced {len(drop)} estimated monthly-mean row(s) with real daily data")
        usable = ev[(ev.item_id == item) & ev.status.isin(USABLE)].copy()
        usable["d"] = pd.to_datetime(usable.effective_from).dt.date
        # price in force on the day BEFORE the first scraped day
        prior = usable[usable.d < first].sort_values("d", kind="stable")
        last_p = float(prior.price.iloc[-1]) if len(prior) else None
        have = set(usable[usable.status == "scraped"].d)
        new = []
        for d, p in series:
            if d in have:
                last_p = p
                continue
            if last_p is None or abs(p / last_p - 1) > 0.0005:
                new.append(_row(item, d, p, "daily scrape, outlier-cleaned", GR[item], today))
            last_p = p
        if new:
            ev = pd.concat([ev, pd.DataFrame(new)], ignore_index=True)
            log.append(f"{item}: +{len(new)} daily price-change event(s), latest {series[-1][1]} on {series[-1][0]}")
    if "R003" in pages:
        lp = sorted(parse_gr_lpg_monthly(pages["R003"]))
        if lp:
            u = ev[(ev.item_id == "R003") & ev.status.isin(USABLE)].copy()
            u["d"] = pd.to_datetime(u.effective_from).dt.date
            u = u.sort_values("d", kind="stable")
            for m, p in lp:
                md = dt.date(int(m[:4]), int(m[5:]), 1)
                prior = u[u.d <= md + dt.timedelta(days=27)]
                last_p = float(prior.price.iloc[-1]) if len(prior) else None
                in_month = u[(u.d >= md) & (u.d <= md + dt.timedelta(days=27))]
                if last_p is not None and abs(p / last_p - 1) > 0.0005 and in_month.empty and md > u.d.max():
                    r = _row("R003", md, p, "LPG monthly table; exact effective day unknown (month start used)", GR["R003"], today)
                    ev = pd.concat([ev, pd.DataFrame([r])], ignore_index=True)
                    log.append(f"R003: new LPG price {p} from {m}")
    return ev, log


def update_file(path, pages, today=None):
    today = today or dt.date.today()
    ev = pd.read_csv(path)
    new, log = update_events(ev, pages, today)
    new = new.sort_values(["item_id", "effective_from"], kind="stable")
    new.to_csv(path, index=False)
    return log
