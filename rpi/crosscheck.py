"""Independent cross-check of the Rajkot APMC series (acrop.app / AgMarkNet republisher) against a second publisher.

agrobhai.com re-publishes the Rajkot Marketing Yard's own daily board: Rs per 20 kg (one 'mann'), a LOW and a HIGH price per crop,
no modal. acrop republishes the AgMarkNet modal in Rs/quintal. The two travel by different routes, so agreement is real
corroboration (not the same feed twice). The check is deliberately one-sided: the acrop modal, converted to Rs/20 kg, must fall
inside the yard's [low, high] band (+/- tolerance). It never feeds the index; it only labels the series 'cross-checked' or flags it.
"""
from __future__ import annotations

import datetime as dt
import re

from bs4 import BeautifulSoup

URL = "https://agrobhai.com/rajkot-apmc/"
# basket item -> Gujarati crop label on the yard board (acrop crop in brackets)
CROPS = {"F001": "ઘઉં લોકવન",    # wheat (Lokvan)
         "F003": "તુવેર",          # tur
         "F004": "મગ"}             # moong
# F005 (chana) is NOT cross-checked: acrop pools desi+kabuli varieties, so it was retired and replaced by this board itself
# (rpi/collectors/web_sources.py::YardBoardCollector). The first run of this check is what exposed the problem.
TOL = 0.03
LOOKBACK_DAYS = 2


def parse_yard_board(html: str) -> tuple[dt.date | None, dict[str, tuple[float, float]]]:
    """-> (board date, {gujarati crop: (low, high) in Rs/20 kg})."""
    soup = BeautifulSoup(html, "lxml")
    m = re.search(r"તારીખ:\s*(\d{2})-(\d{2})-(\d{4})", soup.get_text(" ", strip=True))
    day = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
    out: dict[str, tuple[float, float]] = {}
    for t in soup.find_all("table"):
        for r in t.find_all("tr"):
            c = [x.get_text(" ", strip=True) for x in r.find_all(["td", "th"])]
            if len(c) == 3 and re.fullmatch(r"\d+(\.\d+)?", c[1]) and re.fullmatch(r"\d+(\.\d+)?", c[2]):
                out.setdefault(c[0], (float(c[1]), float(c[2])))
    return day, out


def judge_band(modal_rs_per_kg: float, low: float, high: float, tol: float = TOL) -> str:
    per20 = modal_rs_per_kg * 20.0
    return "agree" if low * (1 - tol) <= per20 <= high * (1 + tol) else "DISAGREE"


def _crosscheck(conn, html: str, crops: dict, source_id: str, pincode: str, tol: float, board: str) -> list[dict]:
    day, table = parse_yard_board(html)
    res = []
    for item, crop in crops.items():
        row = {"board": board, "item_id": item, "crop": crop, "date": str(day), "verdict": "no_data"}
        if day is None or crop not in table:
            res.append(row); continue
        lo, hi = table[crop]
        # acrop lags the yard board by 0-2 days for some yards: take the latest acrop row within LOOKBACK_DAYS before the board date
        q = conn.execute("""SELECT o.price, o.obs_date FROM observations o JOIN products p ON p.sku_id=o.sku_id
                            WHERE p.source_id=? AND p.item_id=? AND o.pincode=? AND o.obs_date<=? AND o.obs_date>=?
                            ORDER BY o.obs_date DESC LIMIT 1""",
                         (source_id, item, pincode, day.isoformat(), (day - dt.timedelta(days=LOOKBACK_DAYS)).isoformat())).fetchone()
        row.update(yard_low_per20kg=lo, yard_high_per20kg=hi)
        if q is None:
            row["verdict"] = "no_acrop_row_for_date"
        else:
            row.update(acrop_modal_per20kg=round(q[0] * 20, 1), acrop_date=str(q[1])[:10], verdict=judge_band(q[0], lo, hi, tol))
        res.append(row)
    return res


def crosscheck_apmc(conn, html: str, tol: float = TOL) -> list[dict]:
    return _crosscheck(conn, html, CROPS, "mandi_rajkot_apmc", "MANDI:Rajkot APMC", tol, "Rajkot")


# Gondal yard board (same publisher). Chana is labelled plain 'ચણા' there and is desi chana (board 1,111-1,416/20 kg).
GONDAL_URL = "https://agrobhai.com/gondal-apmc/"
GONDAL_CROPS = {"F001": "ઘઉં લોકવન", "F003": "તુવેર", "F004": "મગ", "F005": "ચણા"}


def crosscheck_gondal(conn, html: str, tol: float = TOL) -> list[dict]:
    return _crosscheck(conn, html, GONDAL_CROPS, "mandi_rajkot_district", "MANDI:Gondal APMC", tol, "Gondal")


# ---------------------------------------------------------------------------------------------------------------------------
# IBJA benchmark vs goodreturns Rajkot gold / silver (P005, P006)
# ---------------------------------------------------------------------------------------------------------------------------
# ibjarates.com republishes the India Bullion & Jewellers Association's daily AM/PM benchmark (Rs/10 g gold by purity, Rs/kg silver
# 999, ex-GST, ex-making). goodreturns publishes a city retail quote. The two are different publishers with different methods, so
# agreement is real corroboration that the Rajkot feed tracks the national benchmark, but the benchmark is NOT Rajkot-specific and a
# retail quote carries a dealer premium. The check is therefore a *band* test fixed in advance (never tuned after seeing data):
#   gold  22K: goodreturns per g must be within +/-3% of IBJA 916 (day mean of AM/PM) per g
#   silver   : goodreturns per g within +/-10% of IBJA silver 999 per g (retail silver carries a wide, unstable premium -> weak test)
# The page only holds the latest few days, so the check compares the days that overlap with our own stored observations.
IBJA_URL = "https://ibjarates.com/"
IBJA_GOLD_TOL = 0.03
IBJA_SILVER_TOL = 0.10


def parse_ibja_history(html: str) -> dict[str, dict[str, float]]:
    """-> {iso date: {'gold916_per_g': mean(AM,PM)/10, 'silver999_per_g': mean(AM,PM)/1000, 'am916', 'pm916'}}.

    The 'previous dates' block holds two striped tables (first AM, second PM), each with header ['', '999', '995', '916', '750',
    '585', 'Silver 999', 'Platinum 999'] and one row per day (dd/mm/yyyy)."""
    soup = BeautifulSoup(html, "lxml")
    blocks: list[dict[str, list[float]]] = []
    for t in soup.find_all("table"):
        rows = [[c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])] for r in t.find_all("tr")]
        if not rows or "916" not in rows[0] or not any("Silver" in c for c in rows[0]):
            continue
        hdr = rows[0]
        i916, isil = hdr.index("916"), next(i for i, c in enumerate(hdr) if "Silver" in c)
        d: dict[str, list[float]] = {}
        for r in rows[1:]:
            m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", r[0]) if r else None
            if m and len(r) > max(i916, isil) and r[i916].replace(".", "").isdigit() and r[isil].replace(".", "").isdigit():
                d[f"{m.group(3)}-{m.group(2)}-{m.group(1)}"] = [float(r[i916]), float(r[isil])]
        blocks.append(d)
    if len(blocks) < 2:
        return {}
    am, pm = blocks[0], blocks[1]
    out = {}
    for day in sorted(set(am) & set(pm)):
        g_am, s_am = am[day]; g_pm, s_pm = pm[day]
        out[day] = {"am916": g_am, "pm916": g_pm, "gold916_per_g": (g_am + g_pm) / 20.0, "silver999_per_g": (s_am + s_pm) / 2000.0}
    return out


def crosscheck_ibja(conn, html: str, gold_tol: float = IBJA_GOLD_TOL, silver_tol: float = IBJA_SILVER_TOL) -> list[dict]:
    hist = parse_ibja_history(html)
    res = []
    for item, key, tol in (("P005", "gold916_per_g", gold_tol), ("P006", "silver999_per_g", silver_tol)):
        row = {"board": "IBJA", "item_id": item, "verdict": "no_data", "tolerance": tol, "n_days": 0}
        prem = {}
        for day, v in hist.items():
            q = conn.execute("""SELECT o.price FROM observations o JOIN products p ON p.sku_id=o.sku_id
                                WHERE p.source_id='gr_metals' AND p.item_id=? AND substr(o.obs_date,1,10)=? LIMIT 1""", (item, day)).fetchone()
            if q is not None and v[key] > 0:
                prem[day] = q[0] / v[key] - 1.0
        if prem:
            row.update(n_days=len(prem), date=max(prem), premium_min=round(min(prem.values()), 4), premium_max=round(max(prem.values()), 4),
                       premium_by_day={d: round(p, 4) for d, p in sorted(prem.items())},
                       verdict="agree" if max(abs(p) for p in prem.values()) <= tol else "DISAGREE")
        res.append(row)
    return res
