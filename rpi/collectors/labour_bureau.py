"""Labour Bureau CPI-IW (2016=100) - Rajkot centre, from the monthly 'Monthly Indices' letter PDF.

The home page links the latest letter (MILCPI-IW<Month><Year>Epdf-<hash>.pdf). We discover that link, download it,
and read the 'Rajkot <prev> <curr>' row. Month labels inside the PDF are OCR-garbled, so the month comes from the
filename. Older letters can be fed to `parse_letter` too (history backfill).
"""
from __future__ import annotations

import datetime as dt
import io
import re

HOME = "https://www.labourbureau.gov.in"
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def find_letter_url(home_html: str) -> str | None:
    m = re.findall(r'href="([^"]*MILCPI-IW[A-Za-z]+\d{4}[^"]*\.pdf)"', home_html, re.I)
    return m[0] if m else None


def letter_period(url: str) -> str | None:
    m = re.search(r"MILCPI-IW([A-Za-z]+)(\d{4})", url, re.I)
    if not m or m.group(1).capitalize() not in _MONTHS:
        return None
    return f"{m.group(2)}-{_MONTHS.index(m.group(1).capitalize()) + 1:02d}"


def prev_period(p: str) -> str:
    y, mth = int(p[:4]), int(p[5:])
    return f"{y - 1}-12" if mth == 1 else f"{y}-{mth - 1:02d}"


def parse_letter_text(text: str, period: str, centre: str = "Rajkot") -> dict[str, float] | None:
    m = re.search(rf"{centre}\s+(\d{{2,3}}\.\d)\s+(\d{{2,3}}\.\d)", text)
    if not m:
        return None
    return {prev_period(period): float(m.group(1)), period: float(m.group(2))}


def parse_letter_pdf(pdf_bytes: bytes, period: str) -> dict[str, float] | None:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
    return parse_letter_text(text, period)


_M3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def parse_state_popover(html: str, state: str = "GUJARAT") -> dict[tuple[str, str], float]:
    """The Labour Bureau home page carries a server-rendered popover per state: 'Centre Name | <Month - Year> | <Month - Year>' and one
    row per CPI-IW centre (2016=100) for the last two months. Returns {(period 'YYYY-MM', centre): value}. Dynamic: every
    run of the pipeline picks up the newest two months for ALL centres of the state, so the local history accrues by itself."""
    m = re.search(rf'id="popover-content-{re.escape(state)}"(.*?)(?:id="popover-content-|\Z)', html, re.S)
    if not m:
        return {}
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()
    h = re.search(r"Centre Name (\w+) - (\d{4}) (\w+) - (\d{4})", text)
    if not h or h.group(1)[:3] not in _M3 or h.group(3)[:3] not in _M3:
        return {}
    periods = [f"{h.group(2)}-{_M3.index(h.group(1)[:3]) + 1:02d}", f"{h.group(4)}-{_M3.index(h.group(3)[:3]) + 1:02d}"]
    out = {}
    for name, a, b in re.findall(r"([A-Z][A-Za-z&.()' -]+?) (\d{2,3}\.\d) (\d{2,3}\.\d)", text[h.end():]):
        name = name.strip()
        out[(periods[0], name)] = float(a)
        out[(periods[1], name)] = float(b)
    return out
