import datetime as dt
from pathlib import Path
import pandas as pd
from rpi.collectors import ceat_tyres as c

HTML = '<script type="application/ld+json">[{"@type":"Product","sku":"1","name":"a","offers":{"price":"100.5"}},{"@type":"Product","sku":"2","offers":{"price":"0.0"}}]</script>'


def test_parse_products():
    assert c.parse_products(HTML) == {"1": 100.5, "2": 0.0}


class _R:
    status_code = 200
    text = HTML


class _C:
    def get(self, u):
        return _R()


def test_accrue_is_idempotent_per_day(tmp_path):
    pool = tmp_path / "pool.csv"
    pd.DataFrame({"sku": ["1", "9"], "name": ["a", "b"], "page": ["p", "p"]}).to_csv(pool, index=False)
    f = tmp_path / "live.csv"
    n, msg = c.accrue(f, pool, _C(), dt.date(2026, 10, 3))
    c.accrue(f, pool, _C(), dt.date(2026, 10, 3))
    d = pd.read_csv(f)
    assert n == 1 and len(d) == 1 and "1/2" in msg


def test_live_month_replaces_archive_month(tmp_path):
    a = tmp_path / "a.csv"
    pd.DataFrame({"ts": ["20260801000000", "20260801000000", "20260901000000"], "url": ["u"] * 3, "sku": ["1", "2", "1"], "name": ["x"] * 3, "price": [100.0, 200.0, 110.0]}).to_csv(a, index=False)
    lv = tmp_path / "l.csv"
    pd.DataFrame({"date": ["2026-09-05"], "sku": ["1"], "price": [120.0]}).to_csv(lv, index=False)
    p = c.monthly_panel(a, lv)
    assert p.loc["2026-09", "1"] == 120.0 and p.loc["2026-08", "2"] == 200.0


def test_ceat_pool_and_real_gate_recorded():
    pool = pd.read_csv("data/ceat/pool.csv", dtype=str)
    assert len(pool) == 47 and pool.page.nunique() == 12
    g = c.gate(Path("data/ceat/sku_prices.csv"), Path("data/ceat/live_prices.csv"), Path("data/official/mospi_cpi2024_gujarat_urban.csv"))
    assert g["verdict"] in ("fail", "pass", "pending") and g["item_id"] == "T006"
    plan = pd.read_csv("data/source_plan.csv", dtype=str).set_index("item_id")
    assert plan.loc["T006", "primary_source"] == "official_link" and plan.loc["C003", "primary_source"] == "official_link"
