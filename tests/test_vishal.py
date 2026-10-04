import datetime as dt
import pandas as pd
from rpi.collectors import vishal_diary as v

PAGE = '<script type="application/ld+json">{"@type":"Product","sku":"1","offers":{"@type":"Offer","price":"399.00","availability":"http://schema.org/OutOfStock"}}</script>'
LIST = '<script type="application/ld+json">{"@type":"ItemList","itemListElement":[{"@type":"ListItem","url":"https://x/a.html"},{"@type":"ListItem","url":"https://x/b.html"}]}</script>'


class _R:
    status_code = 200
    text = PAGE


class _C:
    def get(self, u):
        return _R()


def test_parse_product_ignores_pincode_dependent_stock():
    assert v.parse_product(PAGE) == (399.0, False)
    assert v.parse_product("<html></html>") is None
    assert v.parse_product(PAGE.replace("399.00", "0")) is None


def test_parse_itemlist():
    assert v.parse_itemlist(LIST) == ["https://x/a.html", "https://x/b.html"]


def test_accrue_idempotent_and_counts_unreadable(tmp_path):
    pool = tmp_path / "pool.csv"
    pd.DataFrame({"item_id": ["C002"], "url": ["https://x/a.html"]}).to_csv(pool, index=False)
    f = tmp_path / "live.csv"
    n, msg = v.accrue(f, pool, _C(), dt.date(2026, 10, 4)); v.accrue(f, pool, _C(), dt.date(2026, 10, 4))
    assert n == 1 and len(pd.read_csv(f)) == 1 and "1/1" in msg


def test_live_replaces_archive_month(tmp_path):
    pool = tmp_path / "p.csv"
    pd.DataFrame({"item_id": ["C002", "C002"], "url": ["u1", "u2"]}).to_csv(pool, index=False)
    a = tmp_path / "a.csv"
    pd.DataFrame({"ts": ["20260901000000", "20260901000000"], "url": ["u1", "u2"], "price": [100.0, 200.0]}).to_csv(a, index=False)
    lv = tmp_path / "l.csv"
    pd.DataFrame({"date": ["2026-09-05"], "item_id": ["C002"], "url": ["u1"], "price": [120.0], "in_stock": [0]}).to_csv(lv, index=False)
    p = v.monthly_panel(a, lv, pool, "C002")
    assert p.loc["2026-09", "u1"] == 120.0 and p.loc["2026-09", "u2"] == 200.0
