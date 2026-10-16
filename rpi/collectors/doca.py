"""Department of Consumer Affairs (DoCA) daily RETAIL price reports for the Rajkot centre.

DoCA's Price Monitoring System collects daily retail (and wholesale) prices of ~40 essential commodities from 555+ centres; Rajkot is
centre 454. fcainfoweb.nic.in itself exposes centre data only behind a CAPTCHA form (never bypassed), but the civic project
cpi.reclaimchennai.city republishes the identical DoCA daily feed through an open, documented JSON API (Swagger at /api/docs; 29.9M
observations since 2009; robots.txt absent).  Because the mirror is a third party, EVERY refresh first proves it is faithful:
`check_mirror()` compares its all-India averages with the ones DoCA prints on its own home page for the same date (to 2 d.p.), and
the DoCA series is only ingested if every commodity agrees (see rpi/refresh.py `check:doca_mirror`).

What the data is: one reporter's quote per commodity per day for a standard local variety, in whole rupees, often unchanged for weeks
(70-99% of day-to-day changes are zero).  It is a genuine Rajkot RETAIL price but a coarse and sticky one, and 'standard quality'
is not our fixed brand.  Hence a per-item gate against the official Gujarat-urban item index (rpi/proxy_check.judge) decides which
items are wired; the rest are screened every run and only reported (status.json:doca_screen).

WINDOW (changed 2026-10-14).  START is now the first month of the official comparator, not the index base year.  The collector used to
ingest from 2025-01-01, which threw away 16 years of Rajkot prices and - because validate:proxies judges a proxy on the months present
in BOTH the proxy series and the official series - left every verdict resting on about 21 months, too short to separate a tracking
series from a drifting one.  The published index is unaffected by the wider window (rpi/index/engine.py drops quotes dated before
project.base_period), so the extra history exists purely to give the gate power.  Several commodities are quoted for the same basket
item (the five edible oils all feed F008); the index and the gate both treat those as matched SKUs of the one item (panel.py
quotes_to_arrays -> Jevons over matched quotes; proxy_check.chain_series), so a multi-commodity item is a panel and needs no special
case here.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

from .base import Collector, Observation
from .web_sources import _WebCollector

MIRROR = "https://cpi.reclaimchennai.city"
CENTRE_ID = 454                       # RAJKOT (Gujarat) in the mirror's centre list
DOCA_HOME = "https://fcainfoweb.nic.in/"
SOURCE_ID = "doca_rajkot"
START = "2014-01-01"                  # first month of the official item comparator; earlier DoCA months can add no gate power
# The balanced PANELS keep the short window: their rule is "centres quoted on EVERY day since the start", and over 12 years centres
# enter and leave, so a long start leaves 0 columns intact (observed 2026-10-14: doca_national 0 centres, doca_gujarat 2).  The panels
# exist to carry the handful of items no Rajkot series can (F011/F020/F024) and need no long history of their own.
PANEL_START = "2025-01-01"

# DoCA commodity id -> (basket item, unit label).  WIRED = accepted by the gate over the LONG window AND a strictly better evidence class
# than the incumbent source; the rest are screened every run and only reported.  Several ids may feed one item (that is a panel).
WIRED = {1: ("F002", "kg"), 10: ("F005", "kg"), 11: ("F003", "kg"), 16: ("F006", "L"),
         17: ("F008", "L"), 18: ("F008", "L"), 19: ("F008", "L"), 20: ("F008", "L"), 21: ("F008", "L"),
         22: ("F021", "kg"), 23: ("F022", "kg"), 24: ("F023", "kg"),
         37: ("F013", "kg"), 38: ("F026", "kg")}
# Screened every run, reported, never ingested.
# PROMOTION_RULE (fixed 2026-10-14; applied as a data edit in data/source_plan.csv, never in code):
#   a DoCA Rajkot-centre series replaces an item's primary source only when it passes a gate leg over the long window AND the incumbent
#   is a PROXY (non-Rajkot) source.  It never replaces an administered local price (F009 milk sits on the Sumul/Amul MRP through
#   `tariff`: a regulated Rajkot price beats a sticky single quote) and never displaces another Rajkot-local retail feed that is still
#   accruing (rajkot_shops F001/F004/F007/F016, judgeable about 2027-04) - same evidence class, and their own accrual is the point.
#   Applied 2026-10-14: F002 rice (commodity 1, leg C), F003 tur (11, legs B+C), F005 chana (10, legs B+C), and F008 edible oils
#   (panel 17/18/19/20/21, legs B+C) move doca_national -> doca_rajkot; F021/F022/F023 also move to Rajkot from a Gujarat panel/Gondal.
#   F006/F013/F026 stay; F025 stays on Gondal. Diagnostics: docs/data/status.json:proxy_validation and doca_screen.
CANDIDATES = {3: "F001", 4: "F001", 5: "F001", 6: "F001", 13: "F004", 33: "F009",
              25: "F025", 26: "F016", 27: "F016", 28: "F016", 29: "F016", 30: "F016", 31: "F016", 32: "F016",
              34: "F012", 35: "F011", 36: "F020", 39: "F014", 40: "F015", 41: "F024"}


def parse_history(text: str) -> list[tuple[dt.date, float]]:
    d = json.loads(text)
    pts = d.get("points") or []
    return [(dt.date.fromisoformat(a), float(b)) for a, b in pts if b is not None and float(b) > 0]


# --- ALL-INDIA DoCA retail panel ---------------------------------------------------------------------------------------------------
# The Rajkot centre alone is one sticky reporter and fails the gate for most items.  The same DoCA feed has ~500 centres.  Panel rule,
# fixed BEFORE looking at any verdict: take the centres that have a (carried-forward) quote on EVERY day since the panel start (a
# balanced panel, so centres entering or leaving cannot move the index), and form the daily Jevons mean (geometric mean across centres).
# Geography hierarchy for wiring (most local panel that passes the gate wins): Rajkot centre -> Gujarat centres -> all-India panel.
# A national panel is NOT a Rajkot price: it is reported in the PROXY bucket, never as direct/retail-local.
# NATIONAL_WIRED passed the gate on 2026-10-02 with the Rajkot centre failing (corr / drift in data/official/doca_panel_screen.csv)
# and is re-gated every refresh (validate:proxies).
# F002/F003/F005/F008 moved to the Rajkot centre on 2026-10-14 (PROMOTION_RULE above): the centre passes the long-window gate for
# all four, so only the commodities with no passing Rajkot series are still taken from a national panel.
NATIONAL_WIRED = {35: ("F011", "100g"), 36: ("F020", "dozen"), 41: ("F024", "kg")}
NATIONAL_CANDIDATES = {34: "F012", 39: "F014", 40: "F015", 32: "F016"}      # not independent through any other feed; screened every run
# GUJARAT panel: the same balanced-panel rule restricted to the Gujarat centres of the feed (state field of /api/meta). Wired only where the Rajkot
# centre fails, the Gujarat panel passes the gate (data/official/doca_panel_screen.csv, wire_to == gujarat) -> most local passing panel wins.
# RETIRED 2026-10-14: potato (the only item this panel carried) moved to the Rajkot centre, which passes the gate for it; the
# collector is registered only while this table is non-empty (rpi/refresh.py), so an empty panel cannot quietly publish nothing.
GUJARAT_WIRED: dict = {}
SERIES_LIMIT = 1200                                                                 # API maximum; the default (400 days) silently truncates


def official_items(root) -> pd.DataFrame:
    """Long official Gujarat-urban comparator by BASKET ITEM (columns = item_id).

    Requires data/official/official_item_spliced.csv, built from CPI2012 item history
    (2014-01..2025-12) and CPI2024's 2025-overlap/newer segment. Never fall back silently
    to CPI2024-only data: that would cap the overlap at about 21 months and invalidate
    the long-history DoCA gate.
    """
    root = Path(root)
    sp = root / "data/official/official_item_spliced.csv"
    if not sp.is_file():
        raise FileNotFoundError(f"long official comparator missing: {sp}; run scripts/build_official_spliced.py")
    d = pd.read_csv(sp, dtype={"item_id": str, "period": str})
    required = {"item_id", "period", "index_value"}
    if not required.issubset(d.columns):
        raise ValueError(f"{sp} must contain {sorted(required)}")
    return d.pivot_table(index="period", columns="item_id", values="index_value", aggfunc="first").sort_index()


def _gate_series(client, root, cid: int, item: str, store=None, source_id: str = SOURCE_ID, centre: bool = True):
    """Fetch one DoCA series (Rajkot centre or all-India panel) and gate it against the item's official index."""
    from ..proxy_check import judge
    if centre:
        url = f"{MIRROR}/api/centre/{CENTRE_ID}/history?commodity={cid}&start={START}&end={dt.date.today().isoformat()}"
    else:
        url = f"{MIRROR}/api/mapseries?commodity={cid}&start={PANEL_START}&end={dt.date.today().isoformat()}&limit={SERIES_LIMIT}"
    r = client.get(url)
    if r.status_code != 200:
        return None, None, {"item_id": item, "doca_commodity": cid, "verdict": "fetch_failed"}
    if store is not None:
        store.save(source_id + "_screen", r.url, None, r.content, r.status_code, "json")
    if centre:
        s = pd.Series({pd.Timestamp(d): p for d, p in parse_history(r.text)})
        if s.empty:
            return None, None, {"item_id": item, "doca_commodity": cid, "verdict": "no_data"}
        m = s.groupby(s.index.to_period("M")).mean()
        stale = round(float((s.diff() == 0).mean()), 2)
    else:
        lvl = panel_level(parse_mapseries(r.text))
        m = lvl.groupby(lvl.index.to_period("M")).mean()
        stale = round(float((lvl.diff() == 0).mean()), 2)
    m.index = m.index.astype(str)
    return m, stale, {"item_id": item, "doca_commodity": cid}


def parse_mapseries(text: str) -> pd.DataFrame:
    """/api/mapseries JSON -> DataFrame (index = date, columns = centre id as str, zeros = missing -> NaN)."""
    d = json.loads(text)
    idx = pd.to_datetime(d["dates"])
    df = pd.DataFrame({str(k): pd.Series(v, index=idx, dtype=float) for k, v in d["centres"].items()})
    return df.where(df > 0)


def panel_level(df: pd.DataFrame, centres: list[str] | None = None) -> pd.Series:
    """Pure: balanced-panel daily Jevons level (Rs/unit). `centres` restricts the panel (e.g. Gujarat); NaN-free columns only."""
    import numpy as np
    cols = [c for c in (centres if centres is not None else df.columns) if c in df.columns]
    sub = df[cols].dropna(axis=1, how="any")
    if sub.shape[1] < 5:
        raise ValueError(f"balanced panel has only {sub.shape[1]} centres")
    return np.exp(np.log(sub).mean(axis=1))


def parse_doca_home(html: str) -> tuple[dt.date | None, dict[str, float]]:
    """DoCA home page 'All India Average Retail Price(Rs/Kg) As on dd/mm/yyyy' tables -> (date, {commodity name: price})."""
    from bs4 import BeautifulSoup
    t = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" "))
    m = re.search(r"All India Average Retail Price\s*\(.{1,6}/Kg\)\s*As on (\d{2})/(\d{2})/(\d{4})", t)
    if not m:
        return None, {}
    day = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    end = t.find("All India Average Wholesale", m.end())
    block = t[m.end(): end if end > 0 else None]
    block = re.sub(r"All India Average Retail Price - [A-Za-z &]+ Commodity Prices", " ", block)
    block = re.sub(r"\s+", " ", block).strip()
    out = {n.strip(): float(v) for n, v in re.findall(r"([A-Za-z][A-Za-z/ ()@.]*?) (\d+(?:\.\d+)?)(?= [A-Z]|$)", block)}
    return day, out


def check_mirror(doca_home_html: str, meta_json: str, map_json: str, tol: float = 0.011) -> list[dict]:
    """Pure: compare the mirror's all-India averages for the DoCA home-page date with DoCA's own published figures."""
    day, home = parse_doca_home(doca_home_html)
    meta = json.loads(meta_json)
    names = {str(c["id"]): c["name"] for c in meta["commodities"]}
    mp = json.loads(map_json)
    if day is None or str(day) != mp.get("date"):
        return [{"commodity": "*", "verdict": "date_mismatch", "doca_date": str(day), "mirror_date": mp.get("date")}]
    res = []
    for cid, st in mp["national"].items():
        nm = names.get(cid)
        if nm in home:
            res.append({"commodity": nm, "doca": home[nm], "mirror": st["avg"], "verdict": "agree" if abs(home[nm] - st["avg"]) <= tol else "DISAGREE"})
    if len(res) < 15:
        res.append({"commodity": "*", "verdict": "too_few_compared", "n": len(res)})
    return res


class DocaRetailCollector(_WebCollector):
    """Rajkot-centre retail price for the gated items. Rs/kg or Rs/L; the whole history since START (2014-01) is returned on every
    call (about 4,000 daily points per commodity, idempotent upserts) so the gate can use the long comparator. The index engine
    clips pre-base observations at 2025-01, so this history affects validation only."""
    source_id = SOURCE_ID
    MAX_AGE_DAYS = 7

    def collect(self, on_date):
        for cid, (item, unit) in WIRED.items():
            url = f"{MIRROR}/api/centre/{CENTRE_ID}/history?commodity={cid}&start={START}&end={on_date.isoformat()}"
            pts = parse_history(self._get(url, self.source_id))
            if not pts:
                raise RuntimeError(f"no DoCA points for commodity {cid}")
            last = max(d for d, _ in pts)
            if (on_date - last).days > self.MAX_AGE_DAYS:
                raise RuntimeError(f"DoCA Rajkot feed for commodity {cid} is stale: last point {last}")
            base = "ml" if unit == "L" else "g"
            for d, p in pts:
                if d <= on_date:
                    yield Observation(d, self.source_id, f"doca{cid}|Rajkot", f"DoCA Rajkot centre retail, commodity {cid} (Rs/{unit})",
                                      item, "DOCA:Rajkot", p, qty_base=1000.0, base_unit=base)


class DocaNationalCollector(_WebCollector):
    """All-India balanced-panel DoCA retail level for the items whose Rajkot centre fails the gate but whose national panel passes."""
    source_id = "doca_national"
    MAX_AGE_DAYS = 7

    def collect(self, on_date):
        for cid, (item, unit) in NATIONAL_WIRED.items():
            url = f"{MIRROR}/api/mapseries?commodity={cid}&start={PANEL_START}&end={on_date.isoformat()}&limit={SERIES_LIMIT}"
            lvl = panel_level(parse_mapseries(self._get(url, self.source_id)))
            last = lvl.index.max().date()
            if (on_date - last).days > self.MAX_AGE_DAYS:
                raise RuntimeError(f"DoCA national panel for commodity {cid} is stale: last day {last}")
            base, qty = {"L": ("ml", 1000.0), "dozen": ("pc", 12.0), "100g": ("g", 100.0)}.get(unit, ("g", 1000.0))
            for d, p in lvl.items():
                if d.date() <= on_date:
                    yield Observation(d.date(), self.source_id, f"doca{cid}|India", f"DoCA all-India balanced-panel retail Jevons level, commodity {cid} (Rs/{unit})",
                                      item, "DOCA:India", float(p), qty_base=qty, base_unit=base)


class DocaGujaratCollector(_WebCollector):
    """Gujarat-centres balanced-panel DoCA retail level for the items whose Rajkot centre fails the gate but whose Gujarat panel passes."""
    source_id = "doca_gujarat"
    MAX_AGE_DAYS = 7

    def collect(self, on_date):
        meta = json.loads(self._get(f"{MIRROR}/api/meta", self.source_id))
        centres = [str(c["id"]) for c in meta["centres"] if c.get("state") == "Gujarat"]
        for cid, (item, unit) in GUJARAT_WIRED.items():
            url = f"{MIRROR}/api/mapseries?commodity={cid}&start={PANEL_START}&end={on_date.isoformat()}&limit={SERIES_LIMIT}"
            lvl = panel_level(parse_mapseries(self._get(url, self.source_id)), centres)
            last = lvl.index.max().date()
            if (on_date - last).days > self.MAX_AGE_DAYS:
                raise RuntimeError(f"DoCA Gujarat panel for commodity {cid} is stale: last day {last}")
            for d, p in lvl.items():
                if d.date() <= on_date:
                    yield Observation(d.date(), self.source_id, f"doca{cid}|Gujarat", f"DoCA Gujarat-centres balanced-panel retail Jevons level, commodity {cid} (Rs/{unit})",
                                      item, "DOCA:Gujarat", float(p), qty_base=1000.0, base_unit="g")


def screen_national(client, official_csv, mapping_csv, store=None, start: str = START) -> list[dict]:
    """Gate the all-India panel for NATIONAL_CANDIDATES (report only)."""
    from ..proxy_check import judge
    root = Path(official_csv).resolve().parents[2]
    off = official_items(root)
    out = []
    for cid, item in NATIONAL_CANDIDATES.items():
        m, _, row = _gate_series(client, root, cid, item, store, source_id="doca_national", centre=False)
        if m is None:
            out.append(row); continue
        o = off[item].dropna() if item in off.columns else pd.Series(dtype=float)
        j = judge(m, o)
        j.update(row, panel="all-India")
        out.append(j)
    return out


def screen_candidates(client, official_csv, mapping_csv, store=None, start: str = START) -> list[dict]:
    """Gate every NOT-yet-wired DoCA commodity against its official item index; report verdicts and the leg that carried them."""
    from ..proxy_check import judge
    root = Path(official_csv).resolve().parents[2]
    off = official_items(root)
    out = []
    for cid, item in CANDIDATES.items():
        m, stale, row = _gate_series(client, root, cid, item, store)
        if m is None:
            out.append(row); continue
        o = off[item].dropna() if item in off.columns else pd.Series(dtype=float)
        j = judge(m, o)
        j.update(row, panel="rajkot-centre", stale_share=stale,
                 doca_change_pct=round(float(m.iloc[-1] / m.iloc[0] * 100 - 100), 1) if len(m) > 1 else None)
        out.append(j)
    return out


def run_mirror_check(client) -> tuple[str, list[dict]]:
    """Live fidelity proof: mirror vs DoCA's own home page, same date. Returns (message, results); never raises on disagreement."""
    home = client.get(DOCA_HOME)
    if home.status_code != 200:
        return f"DoCA home page HTTP {home.status_code}", [{"commodity": "*", "verdict": "doca_home_unreachable"}]
    day, _ = parse_doca_home(home.text)
    if day is None:
        return "DoCA home page layout changed (no retail table)", [{"commodity": "*", "verdict": "doca_home_unparsed"}]
    meta = client.get(f"{MIRROR}/api/meta")
    mp = client.get(f"{MIRROR}/api/map", params={"date": day.isoformat()})
    if meta.status_code != 200 or mp.status_code != 200:
        return "mirror unreachable", [{"commodity": "*", "verdict": "mirror_unreachable"}]
    res = check_mirror(home.text, meta.text, mp.text)
    n_ok = sum(r["verdict"] == "agree" for r in res)
    return f"{n_ok}/{len(res)} commodities identical to DoCA home page ({day})", res
