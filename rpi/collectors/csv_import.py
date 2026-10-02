"""Generic importer for manual / partner / one-off price files.

Columns: date,source,source_sku,title,item_id,pincode,price[,regular_price,pack,in_stock,on_promo,delivery_fee]
`pack` is parsed for quantity (e.g. '5 kg', '6 x 100 g'); unit prices are computed on ingest.
"""
from __future__ import annotations
import datetime as dt
import pandas as pd
from .base import Collector, Observation
from ..units import parse_quantity


class CsvImportCollector(Collector):
    def __init__(self, path, source_id: str = "manual_csv"):
        self.path, self.source_id = path, source_id

    def collect(self, on_date: dt.date):
        df = pd.read_csv(self.path, dtype={"pincode": str})
        for r in df.itertuples():
            q = parse_quantity(str(getattr(r, "pack", "") or getattr(r, "title", "")))
            reg = getattr(r, "regular_price", None)
            yield Observation(
                obs_date=pd.to_datetime(r.date).date(),
                source_id=getattr(r, "source", None) or self.source_id,
                source_sku=str(r.source_sku), title=str(r.title), item_id=r.item_id,
                pincode=str(r.pincode), price=float(r.price),
                regular_price=None if pd.isna(reg) else float(reg),
                qty_base=q[0] if q else None, base_unit=q[1] if q else None,
                in_stock=bool(getattr(r, "in_stock", 1)), on_promo=bool(getattr(r, "on_promo", 0)),
                delivery_fee=float(getattr(r, "delivery_fee", 0) or 0))
