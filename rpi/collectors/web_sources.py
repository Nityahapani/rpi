"""Live web collectors (all robots.txt-checked via PoliteClient, low volume, honest User-Agent).

Parsers are PURE functions on HTML text so they are unit-tested on saved fixtures and can be re-run on archived
raw snapshots. Every source below was inspected live on 2026-10-02:

  goodreturns.in   Rajkot petrol/diesel (daily table), LPG (monthly table), gold 22K + silver (daily tables)
                   NOTE: India Today shows the same numbers incl. the same glitch -> one underlying feed, NOT two sources.
  commodityonline  Gondal Veg. Market (Rajkot district) wholesale mandi prices; republishes Agmarknet, lags ~1 week.
                   The Rajkot APMC page itself is stale (Dec 2025) and carries only grains/oilseeds.
"""
from __future__ import annotations

import datetime as dt
import re

from bs4 import BeautifulSoup

from .base import Collector, Observation

GR = "https://www.goodreturns.in"
URLS = {
    "petrol": f"{GR}/petrol-price-in-rajkot.html",
    "diesel": f"{GR}/diesel-price-in-rajkot.html",
    "lpg": f"{GR}/lpg-price-in-rajkot.html",
    "gold": f"{GR}/gold-rates/rajkot.html",
    "silver": f"{GR}/silver-rates/rajkot.html",
    "png": f"{GR}/png-price-in-rajkot.html",
    "eggs": "https://eggratelab.com/ahmedabad-egg-rate-today",
}
MANDI_BASE = "https://www.commodityonline.com/mandi/gujarat/rajkot/gondal-vegmarket-gondal"
# basket item -> commodityonline slug
MANDI_ITEMS = {"F021": "potato", "F022": "onion", "F023": "tomato", "F024": "banana", "F025": "brinjal"}
# acrop.app republishes AgMarkNet (data.gov.in) per mandi; robots.txt allows generic agents. Added 2026-10-02.
ACROP_BASE = "https://acrop.app/mandi/gujarat/rajkot"
ACROP_MARKETS = {
    # source_id: (url path, market label, {basket item: acrop crop slug})
    "mandi_rajkot_apmc": ("rajkot", "Rajkot APMC", {"F001": "wheat", "F003": "tur", "F004": "moong"}),
    "mandi_rajkot_veg": ("rajkot-vegsub-yard", "Rajkot(Veg.Sub Yard) APMC", {"F021": "potato", "F022": "onion", "F023": "tomato", "F025": "brinjal"}),
}
# Other Rajkot-district yards as EXTRA quotes for the same staples (equal-weight Jevons with the Rajkot yard). One yard's modal swings
# with the quality mix of that day's arrivals (tur: Rs6,750 at Jasdan vs Rs8,250 at Gondal on the same day); several yards damp that.
# Excluded on purpose: Jasdan chana (modal jumped 4,750 -> 6,250 in one day: pooled varieties), Upleta/Dhoraji moong (no rows),
# Dhoraji/Upleta generally (thin reporting). Chana only where the yard reports desi chana (Gondal, Jetpur).
ACROP_DISTRICT = {
    "mandi_rajkot_district": [
        ("gondal", "Gondal APMC", {"F001": "wheat", "F003": "tur", "F004": "moong", "F005": "chana"}),
        ("jetpur-distrajkot", "Jetpur APMC", {"F001": "wheat", "F003": "tur", "F004": "moong", "F005": "chana"}),
        ("jasdan", "Jasdan APMC", {"F001": "wheat", "F003": "tur", "F004": "moong"}),
    ]}


# ----------------------------------------------------------------------------- helpers
def _num(txt: str) -> float | None:
    """'₹1,37,800 (+950)' -> 137800.0 ; 'Rs 2000 / Quintal' -> 2000.0"""
    t = txt.replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    return float(m.group(1)) if m else None


def _tables(html: str) -> list[list[list[str]]]:
    soup = BeautifulSoup(html, "lxml")
    return [[[c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])] for r in t.find_all("tr")]
            for t in soup.find_all("table")]


def _date(txt: str) -> dt.date | None:
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(txt.strip(), fmt).date()
        except ValueError:
            pass
    return None


# ----------------------------------------------------------------------------- goodreturns parsers
def parse_gr_daily_fuel(html: str) -> list[tuple[dt.date, float]]:
    """Daily Rajkot petrol/diesel history table: [Date, Price, Change]."""
    for t in _tables(html):
        if t and t[0][:2] == ["Date", "Price"]:
            out = [(_date(r[0]), _num(r[1])) for r in t[1:] if len(r) >= 2]
            return [(d, p) for d, p in out if d and p]
    return []


def parse_gr_lpg_monthly(html: str) -> list[tuple[str, float]]:
    """Monthly 14.2 kg domestic price table -> [('2026-09', 947.0), ...]."""
    out = []
    for t in _tables(html):
        if t and t[0][0] == "Date" and any("Domestic (14.2" in c for c in t[0]):
            col = [i for i, c in enumerate(t[0]) if "Domestic (14.2" in c][0]
            for r in t[1:]:
                try:
                    p = dt.datetime.strptime(r[0].strip(), "%B %Y")
                except ValueError:
                    continue
                v = _num(r[col])
                if v:
                    out.append((p.strftime("%Y-%m"), v))
    return out


def parse_gr_gold(html: str) -> list[tuple[dt.date, float, float]]:
    """Daily gold history: [(date, 24K Rs/g, 22K Rs/g)]."""
    for t in _tables(html):
        if t and t[0][:3] == ["Date", "24K", "22K"]:
            rows = [(_date(r[0]), _num(r[1]), _num(r[2])) for r in t[1:] if len(r) >= 3]
            return [x for x in rows if x[0] and x[1] and x[2]]
    return []


def parse_gr_silver(html: str) -> list[tuple[dt.date, float]]:
    """Daily silver history table gives Rs per 10 g -> returns Rs per gram."""
    for t in _tables(html):
        if t and t[0][0] == "Date" and "10 gram" in t[0][1]:
            rows = [(_date(r[0]), _num(r[1])) for r in t[1:] if len(r) >= 2]
            return [(d, p / 10.0) for d, p in rows if d and p]
    return []


def parse_gr_png_monthly(html: str) -> list[tuple[str, float]]:
    """Rajkot domestic PNG (Rs/SCM) monthly table [Date, Price, Change] -> [('2026-09', 49.02), ...]."""
    out = []
    for t in _tables(html):
        if t and t[0][:2] == ["Date", "Price"]:
            for r in t[1:]:
                try:
                    m = dt.datetime.strptime(r[0].strip(), "%B %Y")
                except ValueError:
                    continue
                v = _num(r[1])
                if v:
                    out.append((m.strftime("%Y-%m"), v))
    return out


def parse_eggratelab(html: str) -> list[tuple[dt.date, float]]:
    """NECC advisory wholesale egg rate, Rs per egg: 30-day table 'Date / City | Egg price'. Dates are dd-mm-yyyy."""
    for t in _tables(html):
        if t and t[0][0].startswith("Date") and "Egg price" in t[0][1]:
            out = []
            for r in t[1:]:
                try:
                    d = dt.datetime.strptime(r[0].strip(), "%d-%m-%Y").date()
                except ValueError:
                    continue
                v = _num(r[1])
                if v:
                    out.append((d, v))
            return out
    return []


# ----------------------------------------------------------------------------- mandi parser
def parse_mandi_commodity(html: str) -> list[tuple[dt.date, float, float, float, str]]:
    """Per-commodity page -> [(date, min, max, modal Rs/quintal, market)] (newest first, ~10 days)."""
    out = []
    for t in _tables(html):
        if t and t[0][:2] == ["Commodity", "Arrival Date"]:
            for r in t[1:]:
                if len(r) < 7:
                    continue
                d, lo, hi, mo = _date(r[1]), _num(r[4]), _num(r[5]), _num(r[6])
                if d and mo:
                    out.append((d, lo, hi, mo, r[3]))
    return out


def parse_acrop_commodity(html: str) -> list[tuple[dt.date, float, float, float]]:
    """acrop.app per-crop mandi page -> [(date, min, max, modal Rs/quintal)] newest first (about 10 dates in the HTML).
    Only rows explicitly priced 'per quintal' are accepted (the site can show other units); anything else is skipped."""
    out = []
    for t in _tables(html):
        if t and t[0][:2] == ["Date", "Modal Price"]:
            for r in t[1:]:
                if len(r) < 4 or "per quintal" not in r[1]:
                    continue
                try:
                    d = dt.datetime.strptime(r[0].strip(), "%d %b %Y").date()
                except ValueError:
                    continue
                mo, lo, hi = _num(r[1]), _num(r[2]), _num(r[3])
                if mo and lo and hi and lo <= mo <= hi:     # internally inconsistent rows are dropped
                    out.append((d, lo, hi, mo))
    return out


def clean_outliers(series: list[tuple[dt.date, float]], max_jump: float = 0.08, window: int = 7) -> list[tuple[dt.date, float]]:
    """Drop points that deviate > max_jump from the rolling median of neighbours (fuel pages carry glitches such as a
    Rs117.61 'high' among Rs101-102 prices). Conservative: only isolated spikes are removed."""
    pts = sorted(series)
    keep = []
    for i, (d, p) in enumerate(pts):
        nb = [q for j, (_, q) in enumerate(pts) if j != i and abs(j - i) <= window // 2]
        if len(nb) >= 2:
            med = sorted(nb)[len(nb) // 2]
            if abs(p / med - 1) > max_jump:
                continue
        keep.append((d, p))
    return keep


# ----------------------------------------------------------------------------- collectors
def _tables_only(html: str) -> str:
    """Archive only the <table> elements (all the parsers read) - full pages are ~650 KB of site chrome."""
    from bs4 import BeautifulSoup
    return "<html><body>" + "".join(str(t) for t in BeautifulSoup(html, "html.parser").find_all("table")) + "</body></html>"


class _WebCollector(Collector):
    def __init__(self, client, store=None):
        self.client, self.store = client, store

    def _get(self, key_or_url: str, source_id: str) -> str:
        url = URLS.get(key_or_url, key_or_url)
        r = self.client.get(url)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} for {url}")
        if self.store is not None:
            self.last_snapshot_id = self.store.save(source_id, url, None, _tables_only(r.text).encode(), r.status_code, "html")
        return r.text


class MetalsCollector(_WebCollector):
    """Rajkot gold 22K (Rs/g) -> P005 and silver (Rs/g) -> P006. Daily; page holds ~10 days so each run backfills."""
    source_id = "gr_metals"

    def collect(self, on_date):
        for d, _g24, g22 in parse_gr_gold(self._get("gold", self.source_id)):
            yield Observation(d, self.source_id, "gold22k", "Gold 22K Rajkot (Rs/g, goodreturns)", "P005", "RJT", g22,
                              qty_base=1.0, base_unit="g")
        for d, p in parse_gr_silver(self._get("silver", self.source_id)):
            yield Observation(d, self.source_id, "silver", "Silver Rajkot (Rs/g, goodreturns)", "P006", "RJT", p,
                              qty_base=1.0, base_unit="g")


def apply_png_events(base: dict[str, float], events: list[dict], on_date: dt.date) -> dict[str, float]:
    """Overlay curated, dated Gujarat Gas tariff revisions on the (laggy) goodreturns monthly series.

    goodreturns updates its table late (or not at all: still 49.02 on 2 Oct 2026, a month after the 3 Sep hike), so a flat
    carry-forward silently misses real tariff changes. For each event (effective date d, new price p, previous price q):
      * a month is overridden ONLY while goodreturns still shows the pre-event price q (i.e. it has not caught up);
        once goodreturns shows anything else, we trust goodreturns for that month;
      * the event month gets the day-weighted average price (q before d, p from d), later months get p.
    Months run from the first goodreturns month up to on_date's month. Prices are tax-inclusive Rs/SCM.
    """
    if not base:
        return {}
    first, last = min(base), max(base)
    months, y, m = [], int(first[:4]), int(first[5:])
    while (y, m) <= (on_date.year, on_date.month):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    out, carried = {}, base[first]
    for per in months:
        carried = base.get(per, carried)  # goodreturns value for the month, carried forward when absent
        v = carried
        for e in sorted(events, key=lambda e: e["date"]):
            d, p, q = e["date"], e["price"], e["prev"]
            if abs(v - q) > 0.005:
                continue  # goodreturns has moved on from the pre-event price: do not override
            ms = dt.date(int(per[:4]), int(per[5:]), 1)
            me = (dt.date(ms.year + (ms.month == 12), ms.month % 12 + 1, 1))
            if me <= d:
                continue
            if ms >= d:
                v = p
            else:
                days = (me - ms).days
                v = round((q * (d - ms).days + p * (me - d).days) / days, 4)
        out[per] = v
    return out


def load_png_events(path) -> list[dict]:
    import pandas as pd
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        return []
    df = df[df.status.isin(["verified", "derived"])]
    return [dict(date=pd.to_datetime(r.effective_from).date(), price=float(r.price), prev=float(r.prev_price))
            for r in df.itertuples()]


class PngCollector(_WebCollector):
    """Rajkot domestic PNG tariff (Gujarat Gas via goodreturns monthly table), Rs/SCM, tax-inclusive -> R005.
    Monthly; ~10 months of history. Curated tariff revisions (data/png_events.csv) are overlaid while goodreturns lags."""
    source_id = "gr_png"
    events_path = None  # set by refresh; None = no overlay

    def collect(self, on_date):
        rows = dict(parse_gr_png_monthly(self._get("png", self.source_id)))
        events = load_png_events(self.events_path) if self.events_path else []
        series = apply_png_events(rows, events, on_date) if events else None
        if series is None:  # no overlay: original behaviour (carry the latest price forward into the current month)
            series = dict(rows)
            if rows:
                last = max(rows)
                cur = on_date.replace(day=1)
                if cur > dt.date(int(last[:4]), int(last[5:]), 1):
                    series[cur.strftime("%Y-%m")] = rows[last]
        for per, price in sorted(series.items()):
            y, m = int(per[:4]), int(per[5:])
            yield Observation(dt.date(y, m, 1), self.source_id, "png_domestic", "Domestic PNG Rajkot (Rs/SCM incl. tax)",
                              "R005", "RJT", price)


class EggCollector(_WebCollector):
    """NECC daily wholesale egg rate for the Ahmedabad zone (Gujarat). Advisory price, not a Rajkot retail price -> Tier B proxy.
    eggratelab also lists a 'Rajkot' page, but it tracks Ahmedabad with a small premium, so the actual NECC zone is used."""
    source_id = "necc_ahmedabad"

    def collect(self, on_date):
        for d, p in clean_outliers(parse_eggratelab(self._get("eggs", self.source_id))):
            yield Observation(d, self.source_id, "necc_ahmedabad", "Egg, NECC wholesale Ahmedabad (Rs/egg)", "F020", "AHM", p,
                              qty_base=1.0, base_unit="pc")


class MandiCollector(_WebCollector):
    """Gondal Veg. Market (Rajkot district) wholesale modal price, Rs/kg. Tier B proxy for retail produce."""
    source_id = "mandi_gondal"

    def __init__(self, client, store=None, items: dict[str, str] | None = None):
        super().__init__(client, store)
        self.items = items or MANDI_ITEMS

    def collect(self, on_date):
        for item_id, slug in self.items.items():
            rows = parse_mandi_commodity(self._get(f"{MANDI_BASE}/{slug}", self.source_id))
            for d, lo, hi, modal, market in rows:
                yield Observation(d, self.source_id, f"{slug}|{market}", f"{slug} @ {market} (wholesale modal, Rs/kg)",
                                  item_id, f"MANDI:{market}", modal / 100.0, qty_base=1000.0, base_unit="g")


class AcropCollector(_WebCollector):
    """AgMarkNet mandi modal price (Rs/quintal -> Rs/kg) for one Rajkot-district market, via acrop.app.
    Tier B proxy: WHOLESALE raw commodity standing in for the retail item (e.g. wheat -> packaged atta). The modal price mixes
    varieties upstream, so single-day moves can be mix shifts; the monthly Jevons mean damps that."""

    def __init__(self, client, store=None, source_id: str = "mandi_rajkot_apmc"):
        super().__init__(client, store)
        self.source_id = source_id
        if source_id in ACROP_DISTRICT:
            self.markets = ACROP_DISTRICT[source_id]
        else:
            self.markets = [ACROP_MARKETS[source_id]]

    def collect(self, on_date):
        for path, market, items in self.markets:
            for item_id, slug in items.items():
                url = f"{ACROP_BASE}/{path}/{slug}"
                try:
                    rows = parse_acrop_commodity(self._get(url, self.source_id))
                except RuntimeError:
                    if len(self.markets) > 1:       # one yard's page failing must not drop the others
                        continue
                    raise
                for d, lo, hi, modal in rows:
                    if d > on_date:
                        continue
                    yield Observation(d, self.source_id, f"{slug}|{market}", f"{slug} @ {market} (wholesale modal, Rs/kg)",
                                      item_id, f"MANDI:{market}", modal / 100.0, qty_base=1000.0, base_unit="g")


class YardBoardCollector(_WebCollector):
    """Rajkot Marketing Yard daily board (via agrobhai.com): Rs per 20 kg LOW/HIGH per named variety -> F005 chana dal proxy.

    Why this exists: acrop's 'chana' page pools every Bengal-gram variety (its own min-max spans Rs5,900-10,780/q, i.e. desi/yellow
    AND kabuli/white), so its modal jumped between varieties and was NOT a clean series for chana dal (made from desi/yellow chana).
    The yard board names the variety, so we take 'chana yellow' only. Price = midpoint of low/high / 20 (Rs/kg). A midpoint is not a
    modal; it is used purely as a consistently-defined series for chained price relatives."""
    source_id = "yard_rajkot_board"
    VARIETY = {"F005": "ચણા પીળા"}

    def collect(self, on_date):
        from ..crosscheck import URL, parse_yard_board
        day, board = parse_yard_board(self._get(URL, self.source_id))
        if day is None or day > on_date:
            return
        for item_id, crop in self.VARIETY.items():
            if crop in board:
                lo, hi = board[crop]
                yield Observation(day, self.source_id, "chana_yellow|Rajkot yard board", "chana (yellow) @ Rajkot yard board (mid of low/high, Rs/kg)",
                                  item_id, "MANDI:Rajkot APMC", (lo + hi) / 2.0 / 20.0, qty_base=1000.0, base_unit="g")


# ----------------------------------------------------------------------------- fuel event updater
def decide_fuel_event(last_price: float | None, scraped: float | None, tol: float = 0.0005) -> bool:
    """Append a new tariff event iff the cleaned latest scraped price differs from the last recorded one."""
    if scraped is None:
        return False
    return last_price is None or abs(scraped / last_price - 1) > tol


def fuel_events_from_pages(petrol_html: str, diesel_html: str, lpg_html: str, today: dt.date):
    """-> list of dict(item_id, effective_from, price, ...) for the latest cleaned observations (pure)."""
    out = []
    for item, html in (("T001", petrol_html), ("T002", diesel_html)):
        s = clean_outliers(parse_gr_daily_fuel(html))
        if s:
            d, p = s[-1]
            out.append({"item_id": item, "effective_from": d.isoformat(), "price": p})
    lp = parse_gr_lpg_monthly(lpg_html)
    if lp:
        m, p = sorted(lp)[-1]
        out.append({"item_id": "R003", "effective_from": m + "-01", "price": p, "monthly_only": True})
    return out
