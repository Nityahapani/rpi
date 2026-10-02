"""Rajkot asking-rent listings (MagicBricks list pages) - an ACCRUING DIAGNOSTIC, deliberately not an index input.

What it is: every refresh stores the ~30 'RentAction' JSON-LD records on the public Rajkot flats-for-rent list page (listing start date,
BHK, area, asking rent).  robots.txt allows the page for generic user agents.  Records are deduplicated and appended to
data/rent_listings.csv, and robust monthly statistics are published in status.json.

Why it is NOT wired into R001: (1) asking rents of newly advertised flats are a flow measure, while the CPI concept (and the official
index we link) is the whole rented STOCK, which re-prices slowly; (2) ~30 live listings per page, with junk (a 1 BHK at Rs75,000);
(3) no history before the first collection - the only archived copies of the page are 2 Wayback snapshots; (4) the project rule that a
new independent source needs two consecutive qualifying months and a gate against the official item before it carries weight.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

LIST_URLS = tuple(f"https://www.magicbricks.com/{p}-for-rent-in-rajkot-pppfr" for p in (
    "flats", "independent-house", "1-bhk-flats", "2-bhk-flats", "3-bhk-flats"))
COLS = ["first_seen", "listed", "bhk", "sqft", "rent", "title", "source_url"]
MIN_RENT, MAX_RENT = 1500, 100_000


def parse_listings(html: str) -> list[dict]:
    out = []
    for blk in re.findall(r"ld\+json[^>]*>(.*?)</script>", html, re.S):
        try:
            d = json.loads(blk)
        except ValueError:
            continue
        if not (isinstance(d, dict) and d.get("@type") == "RentAction"):
            continue
        try:
            name = d["object"]["name"]
            rent = float(d["priceSpecification"]["price"])
            listed = d["startTime"][:10]
        except (KeyError, TypeError, ValueError):
            continue
        bhk = re.search(r"(\d) BHK", name)
        sq = re.search(r"(\d{3,5}) Sqft", name)
        out.append(dict(listed=listed, bhk=int(bhk.group(1)) if bhk else None, sqft=int(sq.group(1)) if sq else None,
                        rent=rent, title=re.sub(r"\s+", " ", name).strip()))
    return out


def update_file(path: Path, html: str, url: str, today: dt.date | None = None) -> tuple[int, int]:
    """Append unseen listings; return (n_parsed, n_new)."""
    today = today or dt.date.today()
    rows = parse_listings(html)
    old = pd.read_csv(path) if Path(path).exists() else pd.DataFrame(columns=COLS)
    seen = set(zip(old.title, old.rent, old.listed.astype(str)))
    new = [dict(first_seen=today.isoformat(), source_url=url, **r) for r in rows if (r["title"], r["rent"], r["listed"]) not in seen]
    if new:
        pd.concat([x for x in (old, pd.DataFrame(new)[COLS]) if len(x)], ignore_index=True).to_csv(path, index=False)
    return len(rows), len(new)


def clean(g: pd.DataFrame) -> pd.DataFrame:
    """Plausibility band, then a within-BHK junk screen (asking rent > 4x or < 1/4 of the median for that BHK, e.g. a 1 BHK at Rs75,000)."""
    ok = g[(g.rent >= MIN_RENT) & (g.rent <= MAX_RENT)]
    med = ok.groupby("bhk").rent.transform("median")
    return ok[((ok.rent <= 4 * med) & (ok.rent >= med / 4)) | ok.bhk.isna()]


def monthly_stats(path: Path) -> list[dict]:
    """Robust per-month statistics by month of listing: median rent of 2 and 3 BHK, median rent per sq ft, n kept / n dropped as junk."""
    if not Path(path).exists():
        return []
    df = pd.read_csv(path)
    if df.empty:
        return []
    df["month"] = df.listed.astype(str).str[:7]
    out = []
    for m, g in df.groupby("month"):
        ok = clean(g)
        psf = (ok.rent / ok.sqft).dropna()
        row = dict(month=m, n_listings=int(len(g)), n_kept=int(len(ok)), median_rent_psf=round(float(psf.median()), 1) if len(psf) >= 5 else None)
        for b in (2, 3):
            x = ok[ok.bhk == b].rent
            row[f"median_rent_{b}bhk"] = float(x.median()) if len(x) >= 5 else None
            row[f"n_{b}bhk"] = int(len(x))
        out.append(row)
    return out


def qualifying_months(stats: list[dict], min_kept: int = 25) -> int:
    """Months with enough kept listings to be reported as an index candidate (the rule is >= 2 consecutive)."""
    return sum(1 for s in stats if s["n_kept"] >= min_kept)
