import numpy as np
import pandas as pd

from rpi.collectors.dmart import DmartCollector, pack_qty, parse_plp
from rpi.proxy_check import MULTI_SKU_SOURCES, PROXY_SOURCES, chain_series
from rpi.config import ROOT

PLP = {"totalRecords": 2, "products": [{"manufacturer": "Tata", "sKUs": [
    {"skuUniqueID": "11340", "name": "Tata Salt : 1 kg", "priceMRP": "32.00", "priceSALE": "29.00", "invStatus": "2", "buyable": "true", "variantTextValue": "1 kg"},
    {"skuUniqueID": "11339", "name": "Tata Salt Lite : 1 kg", "priceMRP": "55.00", "priceSALE": "50.00", "invStatus": "0", "buyable": "true", "variantTextValue": "1 kg"}]}]}


def test_parse_plp_and_pack_sizes():
    rows = parse_plp(PLP)
    assert [(r["sku"], r["mrp"], r["sale"], r["in_stock"]) for r in rows] == [(11340, 32.0, 29.0, True), (11339, 55.0, 50.0, False)]
    assert pack_qty("Dettol Original Soap : 4x100 g", "100 g x 4 U") == (400.0, "g")     # multiplier survives
    assert pack_qty("Tata Salt : 1 kg", "1 kg") == (1000.0, "g")
    assert pack_qty("Nippo B22 LED Bulb : 9 W", "9 W") == (None, None)                # unit price falls back to the shelf price per piece


def test_collector_skips_out_of_stock_and_reports_blocking(tmp_path):
    import json, datetime as dt

    class R:
        def __init__(self, code, text=""):
            self.status_code, self.text, self.content, self.url = code, text, text.encode(), "u"

    class C:
        def __init__(self, r): self.r, self.session = r, type("S", (), {"headers": {}})()
        def get(self, url, params=None): return self.r

    pool = tmp_path / "pool.csv"
    pd.DataFrame([dict(item_id="F015", sku=11340, cat=240235), dict(item_id="F015", sku=11339, cat=240235)]).to_csv(pool, index=False)
    col = DmartCollector(C(R(200, json.dumps(PLP))), None, pool_csv=pool.name, root=tmp_path)
    obs = list(col.collect(dt.date(2026, 10, 2)))
    assert [(o.source_sku, o.price, o.regular_price, o.item_id) for o in obs] == [("11340", 29.0, 32.0, "F015")]
    blocked = DmartCollector(C(R(403, "403 Forbidden")), None, pool_csv=pool.name, root=tmp_path)
    try:
        list(blocked.collect(dt.date(2026, 10, 2)))
        raise AssertionError("must stop on 403")
    except RuntimeError as e:
        assert "403" in str(e)


def test_pool_is_consistent_with_the_plan():
    pool = pd.read_csv(ROOT / "data/dmart/pool.csv")
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str, keep_default_na=False)
    assert set(pool.item_id) == set(plan.loc[plan.primary_source == "dmart_ahmedabad", "item_id"])
    assert (pool.groupby("item_id").size() >= 2).all() and pool.sku.is_unique
    assert "dmart_ahmedabad" in PROXY_SOURCES and "dmart_ahmedabad" in MULTI_SKU_SOURCES
    assert (plan.loc[plan.primary_source == "dmart_ahmedabad", "class"] == "independent").all()


def test_chain_series_is_immune_to_a_sku_dropping_out():
    # SKU b is missing in month 2 (out of stock): the level must follow SKU a only, not jump because b's price level is different
    piv = pd.DataFrame({"a": [100.0, 110.0, 121.0], "b": [1000.0, np.nan, 1210.0]}, index=["2026-10", "2026-11", "2026-12"])
    s = chain_series(piv)
    assert np.allclose(s.values, [100.0, 110.0, 121.0], rtol=1e-6)


def test_ceat_tyre_screen_is_recorded_and_not_wired():
    import pandas as pd
    from rpi.proxy_check import judge
    s = pd.read_csv("data/official/ceat_tyre_screen.csv", index_col=0)
    assert len(s) == 12 and s.n_skus.min() >= 40
    off = pd.read_csv("data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
    o = off[(off.level == "item") & (off.code == "07.2.1.1.1.01")].set_index("period").index_value
    j = judge(s.ceat_chain, o)
    assert j["verdict"] == "fail" and j["drift"] < 0.05           # near miss on correlation only
    plan = pd.read_csv("data/source_plan.csv", dtype=str).set_index("item_id")
    assert plan.loc["T006", "primary_source"] == "official_link"   # not wired: the gate decides
