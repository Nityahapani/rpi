"""M003 doctor's consultation fee: Practo Rajkot listing pages (practo.com/rajkot/<speciality>?page=n), live diary + gate.

Source: Practo's public listing pages are server-rendered; each doctor card carries the doctor's profile link (slug + practice_id), the clinic, and the
"Consultation fee at clinic" the doctor has set.  robots.txt for `User-agent: *` disallows only searches (`?q=`), the appointment flow and APIs; listing
pages are allowed and are read at 2 s spacing.  Fees are what the doctor lists, not a billed price, and Practo covers the doctors who choose to be listed
(a self-selected, mostly private-practice set); Rajkot-specific.
Pool: every doctor x clinic (practice_id) found on the selection date in the specialities below with fee > 0 (data/practo/pool.csv, never edited silently).
Index: matched-model Jevons over pool members seen in both months (rpi/proxy_check.chain_series).  Fees change roughly once a year per doctor, so a short
history can look flat; the unchanged gate (>= 6 overlapping months, corr >= 0.5, drift <= 0.10) decides.  Wired as a PENDING-GATE proxy for M003.
"""
from __future__ import annotations

import datetime as dt
import html as _html
import re
from pathlib import Path

import pandas as pd

ITEM, CODE = "M003", "06.2.3.1.2.01"
SPECIALITIES = ("general-physician", "internal-medicine", "pediatrician", "gynecologist-obstetrician", "orthopedist", "dermatologist", "cardiologist",
                "ear-nose-throat-ent-specialist", "ophthalmologist", "psychiatrist", "neurologist", "urologist", "gastroenterologist", "diabetologist",
                "pulmonologist", "general-surgeon")   # allopathic physicians and surgeons; dentists and AYUSH are excluded (not the official 'doctor/surgeon fee' line)
MAX_PAGES = 15
COLS = ["date", "key", "speciality", "fee"]
POOL_COLS = ["key", "speciality", "name", "clinic", "locality"]
BASE = "https://www.practo.com/rajkot/"


def parse_listing(page_html: str) -> list[dict]:
    """doctor cards on one listing page -> dicts (key = '<profile slug>:<practice_id>', name, clinic, locality, fee)."""
    out = []
    for c in page_html.split('data-qa-id="doctor_card"')[1:]:
        m = re.search(r'href="/rajkot/doctor/([a-z0-9\-]+)\?practice_id=(\d+)', c)
        f = re.search(r'data-qa-id="consultation_fee"[^>]*>\s*₹(?:<!--[^>]*-->)?\s*([\d,]+)', c)
        if not m or not f:
            continue
        nm = re.search(r'data-qa-id="doctor_name"[^>]*>([^<]*)', c)
        cl = re.search(r'data-qa-id="doctor_clinic_name"[^>]*>([^<]*)', c)
        lo = re.search(r'data-qa-id="practice_locality"[^>]*>([^<]*)', c)
        out.append(dict(key=f"{m.group(1)}:{m.group(2)}", name=_html.unescape(nm.group(1)).strip() if nm else "",
                        clinic=_html.unescape(cl.group(1)).strip() if cl else "", locality=_html.unescape(lo.group(1)).strip() if lo else "",
                        fee=float(f.group(1).replace(",", ""))))
    return out


def scan(client, specialities=SPECIALITIES, max_pages=MAX_PAGES) -> pd.DataFrame:
    rows = []
    for sp in specialities:
        seen = set()
        for n in range(1, max_pages + 1):
            r = client.get(BASE + sp + (f"?page={n}" if n > 1 else ""))
            cards = parse_listing(r.text) if r.status_code == 200 else []
            new = [c for c in cards if c["key"] not in seen]
            if not new:
                break
            seen.update(c["key"] for c in new)
            rows += [dict(c, speciality=sp) for c in new]
    d = pd.DataFrame(rows)
    return d.drop_duplicates("key") if len(d) else d


def build_pool(client, pool_csv: Path) -> int:
    d = scan(client)
    d = d[d.fee > 0]
    pool_csv.parent.mkdir(parents=True, exist_ok=True)
    d[POOL_COLS].to_csv(pool_csv, index=False)
    return len(d)


def accrue(path: Path, pool_csv: Path, client, today: dt.date | None = None) -> tuple[int, str]:
    today = today or dt.date.today()
    pool = pd.read_csv(pool_csv, dtype=str)
    d = scan(client)
    if not len(d):
        return 0, "listing pages unreadable"
    d = d[d.key.isin(set(pool.key)) & (d.fee > 0)]
    rows = [dict(date=today.isoformat(), key=r.key, speciality=r.speciality, fee=r.fee) for r in d.itertuples()]
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=COLS)
    new = pd.concat([x for x in (old[old.date != today.isoformat()], pd.DataFrame(rows, columns=COLS)) if len(x)], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(path, index=False)
    return len(rows), f"{len(rows)}/{len(pool)} pool doctor-clinics priced"


class PractoCollector:
    """Wires the live diary (data/practo/live_fees.csv) into the index as a PENDING-GATE proxy for M003 (one SKU per doctor x clinic)."""
    source_id = "practo_rajkot"
    last_snapshot_id = None

    def __init__(self, root: Path):
        self.live = Path(root) / "data/practo/live_fees.csv"

    def collect(self, on_date):
        from .base import Observation
        if not self.live.exists():
            return
        d = pd.read_csv(self.live)
        d = d[d.fee > 0]
        for r in d.itertuples():
            y, m, dd = (int(x) for x in r.date.split("-"))
            yield Observation(dt.date(y, m, dd), self.source_id, "PRACTO:" + r.key[:80], "Practo listed consultation fee, Rajkot (" + r.speciality + ")",
                              ITEM, "RAJKOT", float(r.fee), qty_base=1.0, base_unit="pc")


def monthly_panel(live_csv: Path) -> pd.DataFrame:
    if not live_csv.exists():
        return pd.DataFrame()
    lv = pd.read_csv(live_csv)
    lv = lv[lv.fee > 0].copy()
    lv["m"] = lv.date.str[:7]
    return lv.groupby(["key", "m"]).fee.median().reset_index().pivot(index="m", columns="key", values="fee").sort_index()


def gate(live_csv: Path, official_csv: Path) -> dict:
    from ..proxy_check import chain_series, judge
    off = pd.read_csv(official_csv, dtype={"code": str})
    o = off[(off.level == "item") & (off.code == CODE)].set_index("period").index_value
    piv = monthly_panel(live_csv)
    if piv.empty:
        return dict(item_id=ITEM, verdict="pending", n_overlap=0, corr=None, drift=None, n_skus=0)
    piv = piv[piv.index <= o.index.max()]
    j = judge(chain_series(piv), o) if len(piv) else dict(verdict="pending", n_overlap=0, corr=None, drift=None)
    j.update(item_id=ITEM, n_skus=int(piv.notna().any().sum()))
    return j
