"""Rajkot field price diary (SHADOW source): validation that names every rejected row, matched-model SKUs, switched-only emission."""
import datetime as dt

import pandas as pd

from rpi.collectors import field_diary as fd
from rpi.config import ROOT

ITEMS = {"F014", "F024", "P001"}


def _rows(*rows):
    return pd.DataFrame(rows, columns=fd.COLS).astype(str)


def test_valid_rows_get_unit_prices_and_a_stable_sku():
    df = _rows(("2026-10-05", "smart_nana_mava", "F014", "Tata Tea", "Premium", "250 g", "140", "150", "AB", ""),
               ("2026-10-05", "fruit_vendor_raiya", "F024", "Robusta banana", "", "1 dozen", "60", "", "AB", ""))
    ok, problems = fd.validate(df, ITEMS, dt.date(2026, 10, 10))
    assert problems == [] and len(ok) == 2
    tea = ok[ok.item_id == "F014"].iloc[0]
    assert tea.unit_price == 560.0 and tea.regular_price == 150.0 and tea.sku == "smart-nana-mava-tata-tea-premium-250-g"
    assert ok[ok.item_id == "F024"].iloc[0].unit_price == 5.0                      # per piece: Rs60 a dozen


def test_every_rejected_row_is_reported_with_its_reason():
    df = _rows(("2026-13-01", "s", "F014", "", "", "250 g", "140", "", "", ""),
               ("2026-12-01", "s", "F014", "", "", "250 g", "140", "", "", ""),
               ("2026-10-01", "s", "X999", "", "", "250 g", "140", "", "", ""),
               ("2026-10-01", "", "F014", "", "", "250 g", "140", "", "", ""),
               ("2026-10-01", "s", "F014", "", "", "250 g", "abc", "", "", ""),
               ("2026-10-01", "s", "F014", "", "", "a packet", "140", "", "", ""))
    ok, problems = fd.validate(df, ITEMS, dt.date(2026, 10, 10))
    assert ok.empty and len(problems) == 6
    for needle in ("not YYYY-MM-DD", "in the future", "unknown item_id", "store is empty", "not a number", "no readable size"):
        assert any(needle in p for p in problems), needle


def test_outliers_are_excluded_and_duplicates_keep_the_last_row():
    base = [("2026-10-0%d" % d, "s%d" % d, "P001", "Lux", "", "125 g", "40", "", "", "") for d in range(1, 6)]
    df = _rows(*base, ("2026-10-06", "s6", "P001", "Lux", "", "125 g", "400", "", "", ""),       # a typo: ten times the price
               ("2026-10-01", "s1", "P001", "Lux", "", "125 g", "42", "", "", ""))                # same visit recorded twice
    ok, problems = fd.validate(df, ITEMS, dt.date(2026, 10, 10))
    assert any("more than 4x" in p for p in problems) and any("duplicate" in p for p in problems)
    assert len(ok) == 5 and ok[ok.store == "s1"].price.tolist() == [42.0]


def test_collector_emits_only_after_a_switch(tmp_path):
    (tmp_path / "data/field_diary").mkdir(parents=True)
    (tmp_path / "registry").mkdir()
    pd.DataFrame({"item_id": sorted(ITEMS)}).to_csv(tmp_path / "registry/items.csv", index=False)
    _rows(("2026-10-05", "smart_nana_mava", "F014", "Tata Tea", "", "250 g", "140", "", "AB", "")).to_csv(tmp_path / fd.PRICES, index=False)
    plan = tmp_path / "data/source_plan.csv"
    pd.DataFrame([("F014", "dmart_ahmedabad")], columns=["item_id", "primary_source"]).to_csv(plan, index=False)
    assert list(fd.FieldDiaryCollector(tmp_path).collect(None)) == []
    pd.DataFrame([("F014", "field_diary")], columns=["item_id", "primary_source"]).to_csv(plan, index=False)
    obs = list(fd.FieldDiaryCollector(tmp_path).collect(None))
    assert len(obs) == 1 and obs[0].source_id == "field_diary" and obs[0].qty_base == 250.0


def test_target_list_is_the_out_of_city_items_no_web_shop_covers():
    t = fd.target_items(ROOT)
    shops = set(pd.read_csv(ROOT / "data/rajkot_shops/pool.csv", dtype=str).item_id)
    assert "F024" in set(t.item_id) and not (set(t.item_id) & shops)
    assert set(t.primary_source) <= set(fd.OUT_OF_CITY_SOURCES)
