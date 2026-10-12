import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from rpi.collectors import onemg_medicine as o

IN_STOCK = ('<script>{"priceBox":{"priceList":[{"type":"best_offer_default_view","mrp":{"displayText":"MRP ",'
            '"price":"\u20b914.26"}}]}}</script>')
SOLD_OUT = ('<script>{"priceBox":{"priceList":[{"type":"unavailable_view","mrp":{"displayText":"MRP ",'
            '"price":"\u20b914.02"}}]}}</script>')


class FakeClient:
    def __init__(self, text, status=200):
        self.text, self.status = text, status

    def get(self, url, params=None):
        return SimpleNamespace(status_code=self.status, text=self.text)


def _root(tmp_path: Path, primary: str = "tariff") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "data/onemg").mkdir(parents=True)
    (tmp_path / "data/onemg/pool.csv").write_text(
        "item_id,product_id,url,pack_units,pack_label\n"
        "M001,878516,https://www.1mg.com/drugs/calpol-500-tablet-878516,15,Calpol\n")
    (tmp_path / "data/source_plan.csv").write_text(
        "item_id,primary_source,class,note\r\nM001,%s,independent,x\r\n" % primary)
    return tmp_path


def test_parse_in_stock_pack_price():
    assert o.parse_pack_price(IN_STOCK) == 14.26


def test_sold_out_page_gives_no_quote():
    assert o.parse_pack_price(SOLD_OUT) is None


def test_missing_or_out_of_band_price_gives_no_quote():
    assert o.parse_pack_price('<html>no price</html>') is None
    assert o.parse_pack_price(IN_STOCK.replace("14.26", "5000")) is None


def test_accrue_writes_per_tablet_unit_price(tmp_path):
    root = _root(tmp_path)
    n, msg = o.accrue(FakeClient(IN_STOCK), root, dt.date(2026, 10, 12))
    assert n == 1 and msg == "ok"
    d = pd.read_csv(root / o.LIVE)
    assert abs(d.loc[0, "unit_price"] - 14.26 / 15) < 1e-6


def test_accrue_skips_sold_out_and_same_day_rerun_replaces(tmp_path):
    root = _root(tmp_path)
    n, msg = o.accrue(FakeClient(SOLD_OUT), root, dt.date(2026, 10, 12))
    assert n == 0 and "not priced" in msg
    o.accrue(FakeClient(IN_STOCK), root, dt.date(2026, 10, 12))
    o.accrue(FakeClient(IN_STOCK), root, dt.date(2026, 10, 12))
    assert len(pd.read_csv(root / o.LIVE)) == 1


def test_switched_items_follow_plan(tmp_path):
    assert o.switched_items(_root(tmp_path / "a", "onemg_medicine")) == ["M001"]
    assert o.switched_items(_root(tmp_path / "b", "tariff")) == []
