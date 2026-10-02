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
items are wired; the rest are screened every run and only reported (status.json:doca_screen).  Observed 2026-10-02: groundnut oil,
sugar and gur pass; atta, tur, sunflower oil, potato, tomato, brinjal fail by 16-60 points of cumulative drift.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import pandas as pd

from .base import Collector, Observation
from .web_sources import _WebCollector

MIRROR = "https://cpi.reclaimchennai.city"
CENTRE_ID = 454                       # RAJKOT (Gujarat) in the mirror's centre list
DOCA_HOME = "https://fcainfoweb.nic.in/"
SOURCE_ID = "doca_rajkot"
START = "2025-01-01"

# DoCA commodity id -> (basket item, unit label). WIRED = passed the gate on 2026-10-02 (and is re-gated every refresh).
WIRED = {16: ("F006", "L"), 37: ("F013", "kg"), 38: ("F026", "kg")}
# Screened every run, reported, never ingested.
CANDIDATES = {4: "F001", 11: "F003", 13: "F004", 10: "F005", 20: "F008", 35: "F011", 34: "F012", 39: "F014", 40: "F015",
              32: "F016", 22: "F021", 23: "F022", 24: "F023", 41: "F024", 25: "F025", 36: "F020", 1: "F002"}


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
NATIONAL_WIRED = {1: ("F002", "kg"), 20: ("F008", "L"), 35: ("F011", "100g"),
                  11: ("F003", "kg"), 10: ("F005", "kg"), 36: ("F020", "dozen"), 41: ("F024", "kg")}
NATIONAL_CANDIDATES = {34: "F012", 39: "F014", 40: "F015", 32: "F016"}      # not independent through any other feed; screened every run
SERIES_LIMIT = 1200                                                                 # API maximum; the default (400 days) silently truncates


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
    """Rajkot-centre retail price for the gated items. Rs/kg or Rs/L; the whole history since the panel start is returned on every
    call (about 600 rows per item, idempotent upserts) so the series is complete from the base month with no official back-fill."""
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
            url = f"{MIRROR}/api/mapseries?commodity={cid}&start={START}&end={on_date.isoformat()}&limit={SERIES_LIMIT}"
            lvl = panel_level(parse_mapseries(self._get(url, self.source_id)))
            last = lvl.index.max().date()
            if (on_date - last).days > self.MAX_AGE_DAYS:
                raise RuntimeError(f"DoCA national panel for commodity {cid} is stale: last day {last}")
            base, qty = {"L": ("ml", 1000.0), "dozen": ("pc", 12.0), "100g": ("g", 100.0)}.get(unit, ("g", 1000.0))
            for d, p in lvl.items():
                if d.date() <= on_date:
                    yield Observation(d.date(), self.source_id, f"doca{cid}|India", f"DoCA all-India balanced-panel retail Jevons level, commodity {cid} (Rs/{unit})",
                                      item, "DOCA:India", float(p), qty_base=qty, base_unit=base)


def screen_national(client, official_csv, mapping_csv, store=None, start: str = "2025-01-01") -> list[dict]:
    """Gate the national panel for NATIONAL_CANDIDATES (report only)."""
    from ..proxy_check import judge
    mp = pd.read_csv(mapping_csv, dtype=str, keep_default_na=False).set_index("item_id")
    off = pd.read_csv(official_csv, dtype={"code": str})
    off = off[off.level == "item"].pivot_table(index="period", columns="code", values="index_value", aggfunc="first")
    out = []
    for cid, item in NATIONAL_CANDIDATES.items():
        r = client.get(f"{MIRROR}/api/mapseries?commodity={cid}&start={start}&end={dt.date.today().isoformat()}&limit={SERIES_LIMIT}")
        if r.status_code != 200:
            out.append({"item_id": item, "doca_commodity": cid, "verdict": "fetch_failed"})
            continue
        if store is not None:
            store.save("doca_national_screen", r.url, None, r.content, r.status_code, "json")
        lvl = panel_level(parse_mapseries(r.text))
        m = lvl.groupby(lvl.index.to_period("M")).mean()
        m.index = m.index.astype(str)
        code = mp.loc[item, "official_item_code"]
        j = judge(m, off[code].dropna() if code in off.columns else pd.Series(dtype=float))
        j.update(item_id=item, doca_commodity=cid, panel="all-India")
        out.append(j)
    return out


def screen_candidates(client, official_csv, mapping_csv, store=None, start: str = "2025-01-01") -> list[dict]:
    """Gate every NOT-yet-wired DoCA commodity against its official item index; report verdicts (never ingests)."""
    from ..proxy_check import judge
    mp = pd.read_csv(mapping_csv, dtype=str, keep_default_na=False).set_index("item_id")
    off = pd.read_csv(official_csv, dtype={"code": str})
    off = off[off.level == "item"].pivot_table(index="period", columns="code", values="index_value", aggfunc="first")
    today = dt.date.today().isoformat()
    out = []
    for cid, item in CANDIDATES.items():
        r = client.get(f"{MIRROR}/api/centre/{CENTRE_ID}/history?commodity={cid}&start={start}&end={today}")
        if r.status_code != 200:
            out.append({"item_id": item, "doca_commodity": cid, "verdict": "fetch_failed"})
            continue
        if store is not None:
            store.save(SOURCE_ID + "_screen", r.url, None, r.content, r.status_code, "json")
        s = pd.Series({pd.Timestamp(d): p for d, p in parse_history(r.text)})
        if s.empty:
            out.append({"item_id": item, "doca_commodity": cid, "verdict": "no_data"})
            continue
        m = s.groupby(s.index.to_period("M")).mean()
        m.index = m.index.astype(str)
        code = mp.loc[item, "official_item_code"] if item in mp.index else ""
        o = off[code].dropna() if code in off.columns else pd.Series(dtype=float)
        j = judge(m, o)
        j.update(item_id=item, doca_commodity=cid, official_item=mp.loc[item, "official_item_name"] if item in mp.index else "",
                 stale_share=round(float((s.diff() == 0).mean()), 2),
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
