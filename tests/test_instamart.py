"""Instamart Rajkot collector: parsing rules and the accrual contract.

The price rows come from a headless browser session (rpi/collectors/instamart.py) because every plain-HTTP route to a
Rajkot grocery shelf is blocked (DMart serves no Rajkot pincode; blinkit/zepto/bigbasket/jiomart answer 403/202 to a
non-browser client).  What is testable without a network is the part that can silently corrupt a series: which tile is
a product, which SKU maps to which basket item, and what unit price a pack implies.
"""
from __future__ import annotations

import json

import pandas as pd

from rpi.collectors import instamart as im


def _rows():
    return im.parse_items(json.load(open("tests/fixtures/instamart_rajkot_home.json")))


def test_parse_items_reads_mrp_and_offer_price_separately():
    rows = {r["sku_id"]: r for r in _rows()}
    assert rows["TEAGOLD1KG"]["price"] == 621.0          # what a shopper pays
    assert rows["TEAGOLD1KG"]["regular_price"] == 690.0  # MRP, the promo-free variant
    assert rows["TEAGOLD1KG"]["pack"] == "1 kg"
    assert rows["TEAGOLD500"]["in_stock"] is False


def test_parse_items_ignores_non_product_nodes():
    # the payload carries card chrome; only ItemCollectionCard variations may become rows
    assert all(r["sku_id"] for r in _rows())
    assert len(_rows()) == 5      # 3 products x variants: tea has a 1 kg and a 500 g SKU


def test_item_mapping_is_narrow_and_leaves_unknown_products_out():
    rows = {r["sku_id"]: r for r in _rows()}
    assert im.assign_item(rows["TEAGOLD1KG"]["name"], rows["TEAGOLD1KG"]["brand"]) == "F014"
    assert im.assign_item(rows["COLGATE200"]["name"], rows["COLGATE200"]["brand"]) == "P003"
    assert im.assign_item("Random Unmapped Thing", "X") is None


def test_build_pool_drops_unmapped_and_out_of_stock_skus():
    import datetime as dt
    pool = im.build_pool(_rows(), dt.date(2026, 11, 21))
    ids = set(pool.sku_id)
    assert {"TEAGOLD1KG", "COLGATE200"} <= ids
    assert "TEAGOLD500" not in ids          # out of stock at capture
    assert "ZZZ1" not in ids                # no basket item
    assert set(pool.item_id) == {"F014", "P003"}
    # fresh produce is left out on purpose: F021/F022/F023 already sit on the DoCA Rajkot centre
    assert "KFOYW0P0CZ" not in ids


def test_accrual_computes_unit_price_from_the_pack_label(tmp_path):
    import datetime as dt
    pool_csv = tmp_path / "pool.csv"
    im.build_pool(_rows(), dt.date(2026, 11, 21)).to_csv(pool_csv, index=False)
    n, msg = im.accrue(tmp_path / "live.csv", pool_csv, rows=_rows(), today=dt.date(2026, 11, 21))
    live = pd.read_csv(tmp_path / "live.csv")
    assert n == len(live) == 2   # only the mapped, in-stock SKUs
    tea = live[live.sku_id == "TEAGOLD1KG"].iloc[0]
    assert abs(tea.unit_price - 621.0) < 1e-6          # Rs/kg for a 1 kg pack
    tooth = live[live.sku_id == "COLGATE200"].iloc[0]
    assert abs(tooth.unit_price - 495.0) < 1e-6        # Rs/kg for a 200 g pack -> 99/0.2
    # re-running for the same day replaces, never duplicates
    im.accrue(tmp_path / "live.csv", pool_csv, rows=_rows(), today=dt.date(2026, 11, 21))
    assert len(pd.read_csv(tmp_path / "live.csv")) == 2
