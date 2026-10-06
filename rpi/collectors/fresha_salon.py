"""P004 barber / beautician / salon services: Fresha venue price list for Rajkot (Style Inc with Prayag), archive + live diary + gate.

Source: a Fresha venue page (fresha.com/a/<venue>) embeds the venue's full service menu in its server-rendered __NEXT_DATA__ (service id, name, retail price).
robots.txt allows /a/* (it disallows /search*, booking paths and queries); the page is read at 2 s spacing.  Of the three Rajkot venues Fresha lists, only
Style Inc's page ships the menu in the HTML (Eklipz Men's and Ladies render it client-side), so the panel is ONE venue: a premium Rajkot salon
(haircut Rs 1,000).  That is a very thin, upper-end-biased PROXY for the official 'barber, beautician and spas' line.
Pool: every service id with a price at the 2026-10-06 selection (data/fresha/pool.csv, never edited silently).  History: the two Internet Archive captures of
the same page (2025-03-27, 2026-04-11) are merged as dated rows (src='wayback'); live rows are appended each refresh.  Index: matched-model Jevons over
services priced in both months.  Salon menus are re-priced about once a year, so short histories can look flat; the unchanged gate (>= 6 overlapping
months, corr >= 0.5, drift <= 0.10) decides.  PENDING-GATE proxy for P004.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

ITEM, CODE = "P004", "13.1.3.2.2.01"
VENUES = {"style-inc": "https://www.fresha.com/a/style-inc-with-prayag-rajkot-raj-nagar-main-road-bb8wt4ou"}
COLS = ["date", "key", "price", "src"]
POOL_COLS = ["key", "venue", "service_id", "name"]


def parse_menu(html: str) -> dict[str, tuple[str, float]]:
    """{service_id: (name, price)} from a venue page (both the 2025 and 2026 page layouts)."""
    out = {}
    for m in re.finditer(r'"__typename":"Service"(.{0,900}?)"retailPrice":\{"currency":"INR","value":(\d+(?:\.\d+)?)\}', html):
        s = re.search(r'"id":"s:(\d+)"', m.group(1))
        n = re.search(r'"name":"([^"]*)"', m.group(1))
        v = float(m.group(2))
        if s and v > 0:
            out.setdefault(s.group(1), ((n.group(1) if n else "").strip(), v))
    return out


def build_pool(client, pool_csv: Path) -> int:
    rows = []
    for v, url in VENUES.items():
        r = client.get(url)
        for sid, (nm, _) in (parse_menu(r.text) if r.status_code == 200 else {}).items():
            rows.append(dict(key=f"{v}:{sid}", venue=v, service_id=sid, name=nm))
    pool_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=POOL_COLS).to_csv(pool_csv, index=False)
    return len(rows)


def accrue(path: Path, pool_csv: Path, client, today: dt.date | None = None) -> tuple[int, str]:
    today = today or dt.date.today()
    pool = pd.read_csv(pool_csv, dtype=str)
    rows = []
    for v, url in VENUES.items():
        r = client.get(url)
        menu = parse_menu(r.text) if r.status_code == 200 else {}
        rows += [dict(date=today.isoformat(), key=f"{v}:{sid}", price=p, src="live") for sid, (_, p) in menu.items() if f"{v}:{sid}" in set(pool.key)]
    if not rows:
        return 0, "venue page unreadable"
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=COLS)
    new = pd.concat([old[old.date != today.isoformat()], pd.DataFrame(rows, columns=COLS)], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    new.sort_values(["date", "key"]).to_csv(path, index=False)
    return len(rows), f"{len(rows)}/{len(pool)} pool services priced"


class FreshaCollector:
    """Wires the diary (data/fresha/prices.csv: Wayback captures + live rows) into the index as a PENDING-GATE proxy for P004 (one SKU per service)."""
    source_id = "fresha_salon"
    last_snapshot_id = None

    def __init__(self, root: Path):
        self.live = Path(root) / "data/fresha/prices.csv"

    def collect(self, on_date):
        from .base import Observation
        if not self.live.exists():
            return
        d = pd.read_csv(self.live)
        d = d[d.price > 0]
        for r in d.itertuples():
            y, m, dd = (int(x) for x in r.date.split("-"))
            yield Observation(dt.date(y, m, dd), self.source_id, "FRESHA:" + r.key, "Salon service price, Style Inc Rajkot (Fresha) " + r.key,
                              ITEM, "RAJKOT", float(r.price), qty_base=1.0, base_unit="pc")


def monthly_panel(csv: Path) -> pd.DataFrame:
    if not csv.exists():
        return pd.DataFrame()
    lv = pd.read_csv(csv)
    lv = lv[lv.price > 0].copy()
    lv["m"] = lv.date.str[:7]
    return lv.groupby(["key", "m"]).price.median().reset_index().pivot(index="m", columns="key", values="price").sort_index()


def gate(csv: Path, official_csv: Path) -> dict:
    from ..proxy_check import chain_series, judge
    off = pd.read_csv(official_csv, dtype={"code": str})
    o = off[(off.level == "item") & (off.code == CODE)].set_index("period").index_value
    piv = monthly_panel(csv)
    if piv.empty:
        return dict(item_id=ITEM, verdict="pending", n_overlap=0, corr=None, drift=None, n_skus=0)
    piv = piv[piv.index <= o.index.max()]
    j = judge(chain_series(piv), o) if len(piv) else dict(verdict="pending", n_overlap=0, corr=None, drift=None)
    j.update(item_id=ITEM, n_skus=int(piv.notna().any().sum()))
    return j
