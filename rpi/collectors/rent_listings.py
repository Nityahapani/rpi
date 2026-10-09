"""Rajkot asking-rent listings - an ACCRUING PANEL from two portals, and the input of the listings-based rent index (rpi/rentlistings.py).

What it is.  Every refresh visits a rotating set of Rajkot RESIDENTIAL rent list pages and stores each listing's structured record:
  * MagicBricks list pages ('RentAction' JSON-LD: listing date, expiry, BHK, type, society/locality, area, asking rent).  A list URL is
    server-rendered two pages deep (~55 listings), so depth comes from breadth: the set of list URLs (localities, BHK, price bands,
    property types) is discovered from the pages themselves and kept in data/rent_list_urls.csv (capped).
  * SquareYards list pages ('RentAction' JSON-LD with a stable listing id, area and furnishing in the description); ~9 per page.
  robots.txt allows both for generic user agents (checked 2026-10-10); 99acres, Housing.com/Makaan and OLX refuse honest clients
  (HTTP 403/406) and are not used; NoBroker does not serve Rajkot.
Each run fetches at most `budget` list URLs (least recently fetched first, page 2 only when page 1 is full), so a full sweep takes a few
days while listings stay up for ~75 days - nothing is missed and no site sees a burst.

Panel (data/rent_listings.csv; the first 7 columns are the original diagnostic's and keep their meaning):
    first_seen, listed, bhk, sqft, rent, title, source_url, portal, key, last_seen, ptype, locality, expires, n_seen
One row per (listing, asking rent): a listing seen again with the same rent only updates last_seen / n_seen; a CHANGED asking rent adds a
row with the same key (a revision).  key = portal id where one exists (SquareYards), else a hash of portal | title | area | listing date.
Landlord / agent names are never stored.  Commercial listings (offices, shops, godowns, land, PG) are dropped at parse time.

Why it is not wired into R001 directly: asking rents of newly advertised dwellings are a FLOW (new-lease) measure, while the CPI concept
is the rent of the whole rented STOCK, which re-prices slowly (11-month leave-and-licence cycles).  rpi/rentlistings.py turns the panel
into a new-lease index and then into a stock-rent candidate; it stays a SHADOW candidate until it qualifies and passes the R001 trend gate.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

LIST_URLS = tuple(f"https://www.magicbricks.com/{p}-for-rent-in-rajkot-pppfr" for p in (
    "flats", "independent-house", "1-bhk-flats", "2-bhk-flats", "3-bhk-flats"))
SQ_SEEDS = tuple(f"https://www.squareyards.com/rent/{p}-in-rajkot" for p in (
    "property-for-rent", "1-bhk-for-rent", "independent-houses-for-rent", "furnished-properties-for-rent"))
COLS = ["first_seen", "listed", "bhk", "sqft", "rent", "title", "source_url"]
PANEL_COLS = COLS + ["portal", "key", "last_seen", "ptype", "locality", "expires", "n_seen"]
URLS_CSV = "data/rent_list_urls.csv"          # top-level data/*.csv: the only data files the daily workflow commits besides the DB
URL_COLS = ["portal", "url", "discovered_on", "last_fetched", "last_n"]
MAX_URLS, DEFAULT_BUDGET = 150, 18
MIN_RENT, MAX_RENT = 1500, 100_000
COMMERCIAL = re.compile(r"office|showroom|\bshop\b|warehouse|godown|industrial|\bland\b|\bplot\b|commercial|hostel|\bpg\b|paying guest|"
                        r"co-?working|hotel|restaurant|factory|\bshed\b|agricultur|farm ?house|retail", re.I)
_MB_LIST = re.compile(r"https://www\.magicbricks\.com/[a-z0-9\-]+-for-rent-in-[a-z0-9\-]*rajkot[a-z0-9\-]*-pppfr")
_SQ_LIST = re.compile(r"https://www\.squareyards\.com/rent/[a-z0-9\-]+-in-[a-z0-9\-]*rajkot")
_NONRES_URL = re.compile(r"office|shop|showroom|warehouse|godown|plot|land|commercial|industrial|\bpg\b|hostel|co-?working|retail", re.I)


class RentBlocked(RuntimeError):
    pass


# ----------------------------------------------------------------------------------------------------------------- parsing (pure)
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def ptype_of(title: str) -> str:
    t = title.lower()
    if re.search(r"\b1\s*rk\b|studio", t):
        return "studio"
    for pat, lab in ((r"villa", "villa"), (r"builder floor", "builder_floor"), (r"penthouse", "penthouse"),
                     (r"house|bungalow|row ?house|independent", "house"), (r"room", "room"), (r"flat|apartment", "flat")):
        if re.search(pat, t):
            return lab
    return "other"


def locality_of(title: str) -> str:
    """'3 BHK Flat for Rent in Gokul Mathura, 150 Feet Ring Road, Rajkot 1500 Sqft' -> '150 feet ring road' (the part before 'Rajkot')."""
    m = re.search(r"for rent in (.*?),?\s*rajkot", title, re.I)
    if not m:
        return ""
    parts = [p.strip() for p in m.group(1).split(",") if p.strip()]
    return re.sub(r"[^a-z0-9 ]+", "", parts[-1].lower()).strip() if parts else ""


def _key(portal: str, title: str, sqft, listed: str) -> str:
    sq = "" if sqft is None or (isinstance(sqft, float) and np.isnan(sqft)) else str(int(float(sqft)))
    return hashlib.sha1(f"{portal}|{_norm(title)}|{sq}|{listed}".encode()).hexdigest()[:16]


def _ld_blocks(html: str):
    for blk in re.findall(r"ld\+json[^>]*>(.*?)</script>", html, re.S):
        try:
            d = json.loads(blk)
        except ValueError:
            continue
        yield from (d if isinstance(d, list) else [d])


def parse_listings(html: str) -> list[dict]:
    """MagicBricks list page -> residential listings (commercial records dropped)."""
    out = []
    for d in _ld_blocks(html):
        if not (isinstance(d, dict) and d.get("@type") == "RentAction"):
            continue
        try:
            name = d["object"]["name"]
            rent = float(d["priceSpecification"]["price"])
            listed = d["startTime"][:10]
        except (KeyError, TypeError, ValueError):
            continue
        title = _norm(name)
        if COMMERCIAL.search(title):
            continue
        bhk = re.search(r"(\d)\s*BHK", name) or re.search(r"(\d)\s*RK", name)
        sq = re.search(r"(\d{3,5}) Sqft", name)
        sqft = int(sq.group(1)) if sq else None
        out.append(dict(listed=listed, bhk=int(bhk.group(1)) if bhk else None, sqft=sqft, rent=rent, title=title,
                        portal="magicbricks", key=_key("magicbricks", title, sqft, listed), ptype=ptype_of(title),
                        locality=locality_of(title), expires=str(d.get("endTime", ""))[:10]))
    return out


def parse_squareyards(html: str) -> list[dict]:
    """SquareYards list page -> residential listings keyed by the portal's listing id."""
    out = []
    for d in _ld_blocks(html):
        if not (isinstance(d, dict) and d.get("@type") == "RentAction"):
            continue
        name, url = _norm((d.get("object") or {}).get("name", "")), d.get("url", "")
        m = re.search(r"/(\d{5,})$", url)
        if not name or not m or COMMERCIAL.search(name) or COMMERCIAL.search(url):
            continue
        try:
            rent = float(str(d.get("price", "")).replace(",", ""))
        except ValueError:
            continue
        desc = d.get("description", "") or ""
        sq = re.search(r"(\d{3,5})\s*(?:Square Feet|sq\.? ?ft|sqft)", desc + " " + url, re.I)
        bhk = re.search(r"(\d)\s*BHK", name, re.I)
        loc = ((d.get("location") or {}).get("address") or {}).get("streetAddress", "")
        out.append(dict(listed=str(d.get("startTime", ""))[:10], bhk=int(bhk.group(1)) if bhk else None,
                        sqft=int(sq.group(1)) if sq else None, rent=rent, title=name, portal="squareyards", key="sq:" + m.group(1),
                        ptype=ptype_of(name), locality=re.sub(r"[^a-z0-9 ]+", "", loc.lower()).strip() or locality_of(name),
                        expires=str(d.get("endTime", ""))[:10]))
    return out


def discover(html: str, portal: str) -> set[str]:
    """Residential rent list URLs linked from a list page (the crawl frontier)."""
    pat = _MB_LIST if portal == "magicbricks" else _SQ_LIST
    return {u for u in set(pat.findall(html)) if not _NONRES_URL.search(u.rsplit("/", 1)[-1])}


# ----------------------------------------------------------------------------------------------------------------- the panel
def _load_panel(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=PANEL_COLS)
    df = pd.read_csv(path, dtype={"key": str, "locality": str, "ptype": str, "portal": str, "expires": str, "last_seen": str})
    for c in PANEL_COLS:
        if c not in df.columns:
            df[c] = np.nan
    for c in ("portal", "key", "last_seen", "ptype", "locality", "expires"):
        df[c] = df[c].astype(object)
    # rows written by the original diagnostic (before 2026-10-10) carry no portal/key: they are MagicBricks rows
    old = df.key.isna() | (df.key.astype(str) == "nan")
    if old.any():
        df.loc[old, "portal"] = "magicbricks"
        df.loc[old, "key"] = [_key("magicbricks", t, s, str(l)) for t, s, l in zip(df.title[old], df.sqft[old], df.listed[old])]
        df.loc[old, "last_seen"] = df.first_seen[old]
        df.loc[old, "ptype"] = df.title[old].map(ptype_of)
        df.loc[old, "locality"] = df.title[old].map(locality_of)
        df.loc[old, "n_seen"] = 1
    return df[PANEL_COLS]


def update_panel(path: Path, rows: list[dict], url: str, today: dt.date | None = None) -> tuple[int, int]:
    """Merge parsed listings into the panel; return (n_parsed, n_new) where new = unseen listings + asking-rent revisions."""
    today = (today or dt.date.today()).isoformat()
    df = _load_panel(path)
    latest = df.sort_values("first_seen").groupby("key").tail(1).set_index("key") if len(df) else pd.DataFrame()
    add, touch, now = [], {}, set()
    for r in rows:
        k = r["key"]
        if k in now:                                   # the same listing twice in one call (page overlap): count it once
            continue
        now.add(k)
        if k in latest.index:
            if float(latest.at[k, "rent"]) == float(r["rent"]):
                touch[k] = True
                continue
        add.append(dict(first_seen=today, source_url=url, last_seen=today, n_seen=1, **r))
    if touch:
        idx = df.index[df.key.isin(list(touch))]
        last_idx = df.loc[idx].sort_values("first_seen").groupby("key").tail(1).index
        fresh = df.loc[last_idx, "last_seen"].astype(str) != today
        df.loc[last_idx[fresh.values], "n_seen"] = pd.to_numeric(df.loc[last_idx[fresh.values], "n_seen"], errors="coerce").fillna(1) + 1
        df.loc[last_idx, "last_seen"] = today
    if add or touch:
        out = pd.DataFrame(df.to_dict("records") + add, columns=PANEL_COLS)      # records, not concat: no all-NA dtype guessing
        out.to_csv(path, index=False)
    return len(rows), len(add)


def update_file(path: Path, html: str, url: str, today: dt.date | None = None) -> tuple[int, int]:
    """Original API (MagicBricks list page HTML): append unseen listings; return (n_parsed, n_new)."""
    return update_panel(path, parse_listings(html), url, today)


# ----------------------------------------------------------------------------------------------------------------- crawl plan
def load_urls(root: Path) -> pd.DataFrame:
    p = Path(root) / URLS_CSV
    df = pd.read_csv(p, dtype=str, keep_default_na=False) if p.exists() else pd.DataFrame(columns=URL_COLS)
    have = set(df.url)
    seeds = [dict(portal="magicbricks", url=u) for u in LIST_URLS] + [dict(portal="squareyards", url=u) for u in SQ_SEEDS]
    new = [dict(s, discovered_on="seed", last_fetched="", last_n="") for s in seeds if s["url"] not in have]
    return pd.concat([x for x in (df, pd.DataFrame(new, columns=URL_COLS)) if len(x)], ignore_index=True)[URL_COLS]


def plan(urls: pd.DataFrame, budget: int) -> list[tuple[str, str]]:
    """Never-fetched URLs first, then the least recently fetched; at most `budget`."""
    u = urls.assign(_k=urls.last_fetched.replace("", "0000-00-00")).sort_values(["_k", "portal"])
    return list(zip(u.portal, u.url))[:budget]


def accrue(client, root: Path, today: dt.date | None = None, budget: int = DEFAULT_BUDGET) -> dict:
    """One polite crawl step.  Stops on the first non-200/404 reply (rate limit / block) - never retries around it."""
    root, today = Path(root), today or dt.date.today()
    panel = root / "data/rent_listings.csv"
    urls = load_urls(root)
    stats = dict(urls_fetched=0, pages=0, parsed=0, new=0, discovered=0, blocked=None)
    found: dict[str, str] = {}
    for portal, u in plan(urls, budget):
        pages = [u, u + "/page-2"] if portal == "magicbricks" else [u]
        n_url = 0
        for pu in pages:
            r = client.get(pu)
            if r.status_code == 404:
                break
            if r.status_code != 200:
                stats["blocked"] = f"HTTP {r.status_code} from {pu}"
                break
            rows = parse_listings(r.text) if portal == "magicbricks" else parse_squareyards(r.text)
            n, new = update_panel(panel, rows, pu, today)
            stats["pages"] += 1; stats["parsed"] += n; stats["new"] += new; n_url += n
            for f in discover(r.text, portal):
                found.setdefault(f, portal)
            if portal != "magicbricks" or n < 25:          # page 2 exists only behind a full page 1
                break
        urls.loc[urls.url == u, ["last_fetched", "last_n"]] = [today.isoformat(), str(n_url)]
        stats["urls_fetched"] += 1
        if stats["blocked"]:
            break
    have = set(urls.url)
    room = max(0, MAX_URLS - len(urls))
    add = [dict(portal=p, url=f, discovered_on=today.isoformat(), last_fetched="", last_n="") for f, p in sorted(found.items()) if f not in have][:room]
    stats["discovered"] = len(add)
    out = pd.concat([x for x in (urls, pd.DataFrame(add, columns=URL_COLS)) if len(x)], ignore_index=True)
    (root / URLS_CSV).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(root / URLS_CSV, index=False)
    stats["urls_known"] = int(len(out))
    return stats


# ----------------------------------------------------------------------------------------------------------------- diagnostics (original)
def clean(g: pd.DataFrame) -> pd.DataFrame:
    """Plausibility band, then a within-BHK junk screen (asking rent > 4x or < 1/4 of the median for that BHK, e.g. a 1 BHK at Rs75,000)."""
    ok = g[(g.rent >= MIN_RENT) & (g.rent <= MAX_RENT)]
    med = ok.groupby("bhk").rent.transform("median")
    return ok[((ok.rent <= 4 * med) & (ok.rent >= med / 4)) | ok.bhk.isna()]


def monthly_stats(path: Path) -> list[dict]:
    """Robust per-month statistics by month of listing: median rent of 2 and 3 BHK, median rent per sq ft, n kept / n dropped as junk.
    One row per listing (its first asking rent); revisions are not new listings."""
    if not Path(path).exists():
        return []
    df = pd.read_csv(path)
    if df.empty:
        return []
    if "key" in df.columns and df.key.notna().any():
        df = df.sort_values("first_seen").drop_duplicates("key", keep="first")
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


class RentListingsCollector:
    """Emits the listings-based STOCK rent candidate as R001 observations - only once R001 is switched to primary_source = rent_listings."""
    source_id = "rent_listings"
    last_snapshot_id = None

    def __init__(self, root: Path):
        self.root = Path(root)

    def collect(self, on_date):
        from .rajkot_shops import switched_items
        from .base import Observation
        if "R001" not in switched_items(self.root, self.source_id):
            return
        from ..rentlistings import candidate_series
        for per, v in candidate_series(self.root).items():
            y, m = int(per[:4]), int(per[5:7])
            yield Observation(dt.date(y, m, 1), self.source_id, "LISTINGS:stock-rent", "Listings-based stock rent (new-lease index, 12-month "
                              "re-pricing; modelled stand-in before the listings)", "R001", "RAJKOT", float(v), qty_base=1.0, base_unit="pc")
