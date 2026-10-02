"""Agmarknet daily mandi prices via the data.gov.in API (Tier B inputs).

NOTE: Parser is written against the documented response shape and tested on a fixture.
It has NOT been verified against the live API from this build environment (no network
access to data.gov.in). Verify field names + commodity names on first live run.
The public demo key returns only ~10 records/request; register your own key and set
DATA_GOV_API_KEY.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import re

import pandas as pd

from .base import Collector, Observation

API = "https://api.data.gov.in/resource/{rid}"


def _norm(rec: dict) -> dict:
    return {k.lower().strip(): v for k, v in rec.items()}


def _f(x):
    try:
        v = float(str(x).replace(",", ""))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _date(x) -> dt.date | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(str(x).strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_records(records: list[dict], commodity_map: pd.DataFrame, markets: list[str] | None = None,
                  source_id: str = "agmarknet"):
    """Records -> Observations (price per kg = modal price per quintal / 100)."""
    cmap = [(r.commodity.strip().lower(), re.compile(r.variety_regex or ".*", re.I), r.item_id)
            for r in commodity_map.itertuples()]
    mk = {m.lower() for m in markets} if markets else None
    for raw in records:
        r = _norm(raw)
        market = str(r.get("market", "")).strip()
        if mk and not any(m in market.lower() for m in mk):
            continue
        d, modal = _date(r.get("arrival_date")), _f(r.get("modal_price"))
        if d is None or modal is None:
            continue
        commodity, variety = str(r.get("commodity", "")).strip(), str(r.get("variety", "")).strip()
        for cname, vre, item_id in cmap:
            if commodity.lower() == cname and vre.search(variety or ""):
                sku = f"{commodity}|{variety}|{market}|{r.get('grade', '')}".strip("|")
                yield Observation(
                    obs_date=d, source_id=source_id, source_sku=sku,
                    title=f"{commodity} {variety} @ {market} (wholesale modal, Rs/kg)",
                    item_id=item_id, pincode=f"MANDI:{market}", price=modal / 100.0,
                    qty_base=1000.0, base_unit="g")
                break


class AgmarknetCollector(Collector):
    source_id = "agmarknet"

    def __init__(self, client, store, settings: dict, commodity_map: pd.DataFrame, page_size: int = 100,
                 max_pages: int = 200):
        cfg = settings["agmarknet"]
        self.client, self.store, self.cfg = client, store, cfg
        self.cmap, self.page_size, self.max_pages = commodity_map, page_size, max_pages
        self.api_key = os.environ.get(cfg.get("api_key_env", "DATA_GOV_API_KEY"), "")

    def _fetch_all(self):
        if not self.api_key:
            raise RuntimeError("DATA_GOV_API_KEY not set (register a free key on data.gov.in)")
        url = API.format(rid=self.cfg["resource_id"])
        for commodity in sorted({c.strip() for c in self.cmap["commodity"]}):
            offset = 0
            for _ in range(self.max_pages):
                params = {"api-key": self.api_key, "format": "json", "limit": self.page_size,
                          "offset": offset, "filters[state]": self.cfg["state"],
                          "filters[commodity]": commodity}
                r = self.client.get(url, params=params)
                self.last_snapshot_id = self.store.save(self.source_id, url, params, r.content, r.status_code)
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code} from data.gov.in")
                recs = json.loads(r.content).get("records", [])
                yield from recs
                if len(recs) < self.page_size:
                    break
                offset += self.page_size

    def collect(self, on_date: dt.date):
        yield from parse_records(list(self._fetch_all()), self.cmap, self.cfg.get("markets"), self.source_id)
