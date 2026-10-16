"""Long-window geography screen for DoCA Rajkot/Gujarat/all-India retail panels.

The Rajkot centre uses START=2014-01; balanced Gujarat/all-India panels retain
PANEL_START=2025-01. All panels are judged against the CPI2012/CPI2024 splice and
report the A/B/C diagnostics and passing legs. Wiring order remains most-local-pass:
Rajkot centre -> Gujarat balanced panel -> all-India balanced panel. Rows screen
individual DoCA commodity series only. F008 is different: its live item-level gate
chains commodity IDs 17/18/19/20/21 together as a matched-SKU pool, so those five
commodity rows are tagged as component diagnostics and are not five independent item
promotions. The actual pooled F008 result is in docs/data/proxy_validation.csv.

Run from the repository root: `python scripts/screen_doca_panels.py`.
No API key is used; requests go to the public DoCA mirror and obey robots.txt/rate limits.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from rpi.collectors.base import PoliteClient
from rpi.collectors.doca import (
    CANDIDATES, CENTRE_ID, MIRROR, NATIONAL_CANDIDATES, NATIONAL_WIRED,
    PANEL_START, SERIES_LIMIT, START, WIRED, official_items, panel_level, parse_history, parse_mapseries,
)
from rpi.proxy_check import judge

OUT = ROOT / "data/official/doca_panel_screen.csv"
UA = "RajkotPriceIndex/1.0 (public research; contact: rpi-maintainers)"
F008_COMPONENTS = {"17", "18", "19", "20", "21"}
F008_POOL_NOTE = (
    "component screen only; active F008 gate uses one matched-SKU chain across DoCA commodities "
    "17/18/19/20/21 (see docs/data/proxy_validation.csv row F008)"
)


def _get(client, url, params=None):
    r = client.get(url, params=params)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.url}")
    return r


def _month(s: pd.Series) -> pd.Series:
    if s.empty:
        return s
    m = s.groupby(s.index.to_period("M")).mean()
    m.index = m.index.astype(str)
    return m


def _unavailable(reason: str) -> dict:
    return {
        "n_overlap": 0, "corr": None, "drift": None, "corr_12m": None,
        "r2": None, "slope": None, "drift_recent": None, "legs": [],
        "leg_status": {"A": "pending", "B": "pending", "C": "pending"},
        "verdict": "pending", "note": reason,
    }


def _flat(prefix: str, result: dict) -> dict:
    row = {f"{prefix}_{k}": result.get(k) for k in (
        "n_overlap", "corr", "drift", "corr_12m", "r2", "slope", "drift_recent", "verdict", "leg_status"
    )}
    row[f"{prefix}_legs"] = "+".join(result.get("legs") or []) or "none"
    if result.get("note"):
        row[f"{prefix}_note"] = result["note"]
    return row


def main() -> None:
    client = PoliteClient(UA, min_delay=0.5, timeout=120, retries=2)
    meta = _get(client, f"{MIRROR}/api/meta").json()
    gujarat = [str(c["id"]) for c in meta["centres"] if c.get("state") == "Gujarat"]
    official = official_items(ROOT)
    # Keep the commodity->item map complete, including screened-only series.
    items = {**WIRED, **NATIONAL_WIRED}
    for cid, item in {**CANDIDATES, **NATIONAL_CANDIDATES}.items():
        items.setdefault(cid, (item, ""))
    rows = []
    end = dt.date.today().isoformat()

    for cid, (item, _unit) in sorted(items.items()):
        if item not in official.columns:
            o = pd.Series(dtype=float)
        else:
            o = official[item].dropna()
        f008_component = item == "F008" and str(cid) in F008_COMPONENTS
        row = {
            "item_id": item, "doca_commodity": cid,
            "screen_scope": "combined_pool_component" if f008_component else "single_commodity_diagnostic",
            "active_gate_basis": F008_POOL_NOTE if f008_component else "commodity-level diagnostic only; active item gate is in docs/data/proxy_validation.csv",
            "start_rajkot": START, "start_balanced_panels": PANEL_START,
            "official_first": o.index.min() if len(o) else None,
            "official_last": o.index.max() if len(o) else None,
        }

        centre_url = f"{MIRROR}/api/centre/{CENTRE_ID}/history?commodity={cid}&start={START}&end={end}"
        centre_resp = _get(client, centre_url)
        points = parse_history(centre_resp.text)
        centre = pd.Series({pd.Timestamp(d): p for d, p in points})
        row["last_day"] = str(centre.index.max().date()) if len(centre) else None
        rajkot = judge(_month(centre), o) if len(centre) else _unavailable("no Rajkot-centre history")
        row.update(_flat("rajkot", rajkot))

        panel_url = f"{MIRROR}/api/mapseries?commodity={cid}&start={PANEL_START}&end={end}&limit={SERIES_LIMIT}"
        panel = parse_mapseries(_get(client, panel_url).text)
        for name, centres in (("gujarat", gujarat), ("india", None)):
            try:
                level = panel_level(panel, centres)
                result = judge(_month(level), o)
            except ValueError as exc:
                result = _unavailable(str(exc))
            row.update(_flat(name, result))

        row["wire_to"] = next((name for name in ("rajkot", "gujarat", "india")
                                if row.get(f"{name}_verdict") == "pass"), "none")
        rows.append(row)

    out = pd.DataFrame(rows).sort_values(["item_id", "doca_commodity"])
    out.to_csv(OUT, index=False)
    print(f"wrote {OUT}: {len(out)} commodity-level screens, {out.wire_to.value_counts().to_dict()}")
    print(f"NOTE: {F008_POOL_NOTE}")
    print(out[["item_id", "doca_commodity", "screen_scope", "rajkot_n_overlap", "rajkot_legs", "rajkot_verdict",
               "gujarat_verdict", "india_verdict", "wire_to"]].to_string(index=False))


if __name__ == "__main__":
    main()
