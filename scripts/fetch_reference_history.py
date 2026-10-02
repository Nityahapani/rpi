"""Fetch the long-history REFERENCE datasets (not index inputs): WFP India retail prices (HDX) and the NECC egg archive.

* WFP / HDX 'India - Food Prices' (World Food Programme price database; Indian source = DoCA/DES retail price monitoring).
  Rajkot and Ahmedabad retail rows, Apr 2010 - Jul 2023 (Gujarat reporting stops in 2023-07 upstream).  CC-BY-IGO.
  https://data.humdata.org/dataset/wfp-food-prices-for-india
* NECC daily 'Suggested' egg rate, Ahmedabad zone, 2009-01-01 -> today (publisher e2necc.com; civic archive
  https://eggs.reclaimchennai.city/data/egg_prices_daily.csv), reduced to calendar-month means.

Run:  PYTHONPATH=. python3 scripts/fetch_reference_history.py     (writes data/reference/*.csv; one-off, not part of refresh)
"""
import io
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/reference")
OUT.mkdir(parents=True, exist_ok=True)
HDX = "https://data.humdata.org/api/3/action/package_show?id=wfp-food-prices-for-india"

meta = requests.get(HDX, timeout=60).json()["result"]
url = next(r["url"] for r in meta["resources"] if r["name"].endswith("Food Prices") or r["name"] == "India - Food Prices")
raw = pd.read_csv(io.StringIO(requests.get(url, timeout=300).text), skiprows=[1], low_memory=False)
w = raw[raw.market.isin(["Rajkot", "Ahmedabad"]) & (raw.pricetype == "Retail")]
w = w[["date", "market", "commodity", "unit", "priceflag", "price"]].sort_values(["market", "commodity", "date"])
w.to_csv(OUT / "wfp_gujarat_retail.csv", index=False)
print("WFP rows", len(w), "resource modified", meta["last_modified"], "|", w.date.min(), "->", w.date.max())

d = pd.read_csv(io.StringIO(requests.get("https://eggs.reclaimchennai.city/data/egg_prices_daily.csv", timeout=300).text), parse_dates=["date"])
a = d[(d.zone == "Ahmedabad") & (d.series == "NECC Suggested")].set_index("date").price_inr
m = a.resample("MS").agg(["mean", "count"]).rename(columns={"mean": "price_inr_per_egg", "count": "days"})
m.index = m.index.strftime("%Y-%m"); m.index.name = "period"
m.round(4).to_csv(OUT / "necc_ahmedabad_monthly.csv")
print("NECC months", len(m), m.index.min(), "->", m.index.max())
