"""Official MoSPI CPI (base 2024=100) via api.mospi.gov.in - the benchmark every other source is audited against.

Endpoint (verified live 2026-10-02, no token needed for the unified 2024-base endpoint):
    GET /api/cpi/getCPIData?base_year=2024&series=Current&year=..&state_code=10&sector_code=2&limit<=100&page=n
State codes for base 2024 differ from CPI-2012 (Gujarat = 10 here). Sector: 1 rural, 2 urban, 3 combined.
Provisional state-level item indices are thin-sample: MoSPI says interpret cautiously.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

import pandas as pd

from ..http_compat import session

BASE = "https://api.mospi.gov.in"


def _level(r: dict) -> tuple[str, str | None]:
    if r.get("item"): return "item", r["item"]
    if r.get("sub_class"): return "sub_class", r["sub_class"]
    if r.get("class"): return "class", r["class"]
    if r.get("group"): return "group", r["group"]
    if (r.get("division") or "") == "CPI (General)": return "general", "CPI (General)"
    return "division", r.get("division")


def fetch_cpi(state_code: int = 10, sector_code: int = 2, years=(2025, 2026), raw_dir: Path | None = None,
              sleep: float = 0.4, sess=None) -> pd.DataFrame:
    s = sess or session()
    rows, page, total_pages = [], 1, 1
    while page <= total_pages:
        r = s.get(f"{BASE}/api/cpi/getCPIData", params=dict(
            base_year="2024", series="Current", year=",".join(map(str, years)), state_code=state_code,
            sector_code=sector_code, limit=100, page=page), timeout=90)
        r.raise_for_status()
        j = r.json()
        if "data" not in j:
            raise RuntimeError(f"unexpected MoSPI response: {str(j)[:200]}")
        if raw_dir:
            Path(raw_dir).mkdir(parents=True, exist_ok=True)
            (Path(raw_dir) / f"cpi_state{state_code}_sector{sector_code}_p{page}.json").write_text(r.text)
        rows += j["data"]
        total_pages = j["meta_data"]["totalPages"]
        page += 1
        time.sleep(sleep)
    df = pd.DataFrame(rows)
    lv = df.apply(lambda r: _level(r), axis=1, result_type="expand")
    df["level"], df["name"] = lv[0], lv[1]
    df["period"] = pd.to_datetime(df["year"].astype(str) + "-" + df["month"], format="%Y-%B").dt.to_period("M").astype(str)
    df["index_value"] = pd.to_numeric(df["index"], errors="coerce")
    df["inflation_pct"] = pd.to_numeric(df["inflation"], errors="coerce")
    return df[["period", "state", "sector", "level", "code", "name", "index_value", "inflation_pct", "imputation",
               "division", "group", "class", "sub_class", "item"]]
