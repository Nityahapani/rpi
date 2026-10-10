import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from rpi.collectors import apple_store as a

FIXTURE = (
    '<script>{"partNumber":"MYE93HN/A","dimensionCapacity":"256gb","price":{"fullPrice":99900.00}}</script>'
    '<script>{"partNumber":"MYE73HN/A","dimensionCapacity":"128gb","price":{"fullPrice":89900.00}}</script>'
)


class FakeClient:
    def __init__(self, text, status=200):
        self.text, self.status = text, status

    def get(self, url, params=None):
        return SimpleNamespace(status_code=self.status, text=self.text)


def _root(tmp_path: Path, plan_primary: str = "official_link") -> Path:
    (tmp_path / "data/apple_store").mkdir(parents=True)
    (tmp_path / "data/apple_store/pool.csv").write_text("part_number,item_id,model,capacity,colour\nMYE73HN/A,K002,iPhone 16,128 GB,Black\n")
    (tmp_path / "data/apple_store_prices.csv").write_text("date,part_number,item_id,price,currency,url\n")
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data/source_plan.csv").write_text(
        "item_id,primary_source,class,note\r\nK002,%s,%s,x\r\n" % (plan_primary, "independent" if plan_primary == "apple_store" else "linked"))
    return tmp_path


def test_parse_price_reads_the_entry_of_the_asked_part_number_only():
    assert a.parse_price(FIXTURE, "MYE73HN/A") == 89900.0
    assert a.parse_price(FIXTURE, "MYE93HN/A") == 99900.0


def test_parse_price_refuses_absent_or_implausible_prices():
    assert a.parse_price(FIXTURE, "NOPE/A") is None
    assert a.parse_price('"partNumber":"MYE73HN/A" "fullPrice":5', "MYE73HN/A") is None      # below the band
    assert a.parse_price('"partNumber":"MYE73HN/A"', "MYE73HN/A") is None                    # no price in window


def test_accrue_writes_one_row_and_a_same_day_rerun_replaces_it(tmp_path):
    root = _root(tmp_path)
    today = dt.date(2026, 10, 10)
    assert a.accrue(FakeClient(FIXTURE), root, today) == (1, "ok")
    assert a.accrue(FakeClient(FIXTURE.replace("89900", "91900")), root, today) == (1, "ok")
    d = pd.read_csv(root / a.LIVE, dtype=str)
    assert len(d) == 1 and d.price.iloc[0] == "91900.0"


def test_accrue_reports_a_missing_part_and_writes_nothing_for_it(tmp_path):
    root = _root(tmp_path)
    n, msg = a.accrue(FakeClient("<html>no models today</html>"), root, dt.date(2026, 10, 10))
    assert n == 0 and "MYE73HN/A" in msg
    assert len(pd.read_csv(root / a.LIVE)) == 0


def test_accrue_stops_on_a_non_200_reply(tmp_path):
    root = _root(tmp_path)
    assert a.accrue(FakeClient("", status=403), root, dt.date(2026, 10, 10))[0] == 0


def test_live_frame_uses_the_shared_shadow_schema(tmp_path):
    root = _root(tmp_path)
    a.accrue(FakeClient(FIXTURE), root, dt.date(2026, 10, 10))
    f = a.live_frame(root)
    assert list(f.columns) == ["date", "item_id", "sku", "unit_price", "price", "regular_price", "qty_base", "base_unit", "title", "store"]
    assert f.item_id.tolist() == ["K002"] and f.sku.tolist() == ["apple:MYE73HN/A"] and f.price.iloc[0] == 89900.0


def test_collector_is_silent_until_k002_is_switched(tmp_path):
    root = _root(tmp_path)
    a.accrue(FakeClient(FIXTURE), root, dt.date(2026, 10, 10))
    assert list(a.AppleStoreCollector(root).collect(dt.date(2026, 10, 10))) == []


def test_collector_emits_observations_once_switched(tmp_path):
    root = _root(tmp_path, plan_primary="apple_store")
    a.accrue(FakeClient(FIXTURE), root, dt.date(2026, 10, 10))
    obs = list(a.AppleStoreCollector(root).collect(dt.date(2026, 10, 10)))
    assert len(obs) == 1 and obs[0].price == 89900.0 and obs[0].item_id == "K002"
