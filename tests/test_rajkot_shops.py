"""Rajkot web shops (SHADOW source): feed parsing, pack reading, polite accrual, switched-only emission, registry wiring."""
import datetime as dt
import json

import pandas as pd

from rpi.collectors import rajkot_shops as rs
from rpi.config import ROOT

SHOPIFY = {"products": [
    {"id": 1, "title": "Sugar (ખાંડ) - Everyday Sweetener", "variants": [
        {"id": 11, "title": "1 Kg", "price": "88.00", "compare_at_price": None, "available": True},
        {"id": 12, "title": "5 Kg", "price": "429.00", "compare_at_price": "450.00", "available": True},
        {"id": 13, "title": "2 Kg", "price": "174.00", "compare_at_price": None, "available": False}]},
    {"id": 2, "title": "Toor Dal (oil free)", "variants": [{"id": 21, "title": "1 Kg", "price": "0.00", "available": True}]},
]}
WOO = [
    {"id": 648, "name": "Refined Sunflower Oil 1-Ltr Pouch", "type": "simple", "is_in_stock": True, "is_purchasable": True,
     "prices": {"price": "18400", "regular_price": "18400", "currency_minor_unit": 2}},
    {"id": 653, "name": "Refined Sunflower Oil 15-Ltr Tin", "type": "simple", "is_in_stock": True, "is_purchasable": True,
     "prices": {"price": "262000", "regular_price": "270000", "currency_minor_unit": 2}},
    {"id": 999, "name": "Gift Box", "type": "variable", "prices": {"price": "100", "currency_minor_unit": 0}},
]


class _Resp:
    def __init__(self, status, payload, headers=None):
        self.status_code, self._p, self.headers = status, payload, headers or {}
        self.text = json.dumps(payload)

    def json(self):
        return self._p


class _Client:
    """Answers the two storefront endpoints from canned payloads; `blocked` hosts get HTTP 403."""
    def __init__(self, blocked=()):
        self.blocked, self.calls = set(blocked), []

    def get(self, url, params=None):
        self.calls.append(url)
        if any(b in url for b in self.blocked):
            return _Resp(403, {})
        if url.endswith("/products.json"):
            return _Resp(200, SHOPIFY if (params or {}).get("page", 1) == 1 else {"products": []})
        return _Resp(200, WOO, {"X-WP-TotalPages": "1"})


def test_parsers_read_prices_regular_prices_and_availability():
    rows = {r["variant_id"]: r for r in rs.parse_shopify(SHOPIFY)}
    assert rows["11"]["price"] == 88.0 and rows["11"]["regular_price"] is None and rows["11"]["available"]
    assert rows["12"]["regular_price"] == 450.0 and not rows["13"]["available"]
    woo = {r["variant_id"]: r for r in rs.parse_woo(WOO)}
    assert woo["648"]["price"] == 184.0 and woo["653"]["regular_price"] == 2700.0      # minor units -> rupees
    assert "999" not in woo                                                           # variable products need per-variation calls: skipped


def test_pack_is_read_from_the_label_including_hyphenated_storefront_sizes():
    assert rs.pack_of("Sugar", "1 Kg") == (1000.0, "g")
    assert rs.pack_of("Refined Sunflower Oil 15-Ltr Tin", "") == (15000.0, "ml")
    assert rs.pack_of("Double Filtered Groundnut Oil 15-Kg Tin", "Default Title") == (15000.0, "g")
    assert rs.pack_of("Moong Dal", "500 Gram") == (500.0, "g")


def _tmp_root(tmp_path, plan_rows):
    (tmp_path / "data/rajkot_shops").mkdir(parents=True)
    pool = pd.DataFrame([
        dict(item_id="F013", store="green_force", product_id="1", variant_id="11", product_title="Sugar", variant_title="1 Kg", qty_base=1000, base_unit="g"),
        dict(item_id="F013", store="green_force", product_id="1", variant_id="12", product_title="Sugar", variant_title="5 Kg", qty_base=5000, base_unit="g"),
        dict(item_id="F013", store="green_force", product_id="1", variant_id="13", product_title="Sugar", variant_title="2 Kg", qty_base=2000, base_unit="g"),
        dict(item_id="F003", store="green_force", product_id="2", variant_id="21", product_title="Toor Dal", variant_title="1 Kg", qty_base=1000, base_unit="g"),
        dict(item_id="F008", store="rani_oil", product_id="648", variant_id="648", product_title="Refined Sunflower Oil 1-Ltr Pouch", variant_title="", qty_base=1000, base_unit="ml"),
        dict(item_id="F008", store="rani_oil", product_id="653", variant_id="653", product_title="Refined Sunflower Oil 15-Ltr Tin", variant_title="", qty_base=15000, base_unit="ml"),
    ])
    pool.to_csv(tmp_path / rs.POOL, index=False)
    pd.DataFrame(plan_rows, columns=["item_id", "primary_source"]).to_csv(tmp_path / "data/source_plan.csv", index=False)
    return tmp_path


def test_accrue_prices_the_pool_skips_unavailable_and_zero_prices(tmp_path):
    root = _tmp_root(tmp_path, [("F013", "doca_rajkot"), ("F008", "doca_national")])
    n, msg = rs.accrue(_Client(), root, dt.date(2026, 10, 10))
    live = pd.read_csv(root / rs.LIVE, dtype={"variant_id": str})
    assert n == 4 and set(live.variant_id) == {"11", "12", "648", "653"}           # 13 out of stock, 21 priced at zero
    tin = live[live.variant_id == "653"].iloc[0]
    assert tin.unit_price == round(2620 / 15, 4) and tin.regular_price == 2700.0      # per litre, from the label
    assert "green_force 2/4 priced" in msg and "rani_oil 2/2 priced" in msg


def test_a_blocked_store_is_skipped_and_its_earlier_rows_of_the_day_survive(tmp_path):
    root = _tmp_root(tmp_path, [])
    rs.accrue(_Client(), root, dt.date(2026, 10, 10))
    n, msg = rs.accrue(_Client(blocked=("ranioil",)), root, dt.date(2026, 10, 10))
    live = pd.read_csv(root / rs.LIVE, dtype={"variant_id": str})
    assert "rani_oil: HTTP 403" in msg and set(live[live.store == "rani_oil"].variant_id) == {"648", "653"}
    assert len(live) == 4                                                                   # green_force replaced, not duplicated


def test_collector_emits_nothing_in_shadow_and_only_switched_items_after_a_switch(tmp_path):
    root = _tmp_root(tmp_path, [("F013", "doca_rajkot"), ("F008", "doca_national")])
    rs.accrue(_Client(), root, dt.date(2026, 10, 10))
    assert list(rs.RajkotShopsCollector(root).collect(dt.date(2026, 10, 10))) == []
    pd.DataFrame([("F013", "rajkot_shops"), ("F008", "doca_national")], columns=["item_id", "primary_source"]).to_csv(
        root / "data/source_plan.csv", index=False)
    obs = list(rs.RajkotShopsCollector(root).collect(dt.date(2026, 10, 10)))
    assert {o.item_id for o in obs} == {"F013"} and {o.source_sku for o in obs} == {"green_force:11", "green_force:12"}
    assert all(o.pincode == "360003" and o.base_unit == "g" for o in obs)


def test_registries_know_the_shadow_sources_so_a_switch_needs_no_code_change():
    from rpi.collectors.official_link import BACKFILL_SOURCES
    from rpi.index.engine import SINGLE_SERIES_SOURCES
    from rpi.proxy_check import GATED_SOURCES, MULTI_SKU_SOURCES, PROXY_SOURCES, RETAIL_SOURCES
    for src in ("rajkot_shops", "field_diary"):
        assert src in RETAIL_SOURCES and src in MULTI_SKU_SOURCES and src in GATED_SOURCES
        assert src in BACKFILL_SOURCES and src in SINGLE_SERIES_SOURCES and src not in PROXY_SOURCES   # a Rajkot shelf price is not a proxy


def test_the_committed_pool_is_rajkot_only_parseable_and_maps_to_basket_items():
    pool = pd.read_csv(ROOT / rs.POOL, dtype=str)
    items = set(pd.read_csv(ROOT / "registry/items.csv", dtype=str).item_id)
    assert set(pool.store) <= set(rs.STORES) and set(pool.item_id) <= items
    assert (pd.to_numeric(pool.qty_base) > 0).all() and set(pool.base_unit) <= {"g", "ml"}
    assert not pool.duplicated(["store", "variant_id"]).any() and len(pool) >= 30
    assert {"F016", "F002", "F008", "F003", "F005"} <= set(pool.item_id)                    # the out-of-city staples this source exists for
