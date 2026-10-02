import json
from rpi.collectors import mrp_diary


def test_parse_product_variants():
    t = json.dumps({"product": {"handle": "h", "variants": [
        {"sku": "A", "title": "x", "price": "150.00", "compare_at_price": None},
        {"sku": "B", "title": "y", "price": "155.00", "compare_at_price": "180.00"}]}})
    r = mrp_diary.parse_product(t)
    assert [v["price"] for v in r] == [150.0, 155.0] and r[1]["compare_at"] == 180.0 and r[0]["compare_at"] is None


def test_seed_and_summary(tmp_path):
    import pandas as pd
    p = tmp_path / "d.csv"
    assert mrp_diary.seed_archive(p) == 4 and mrp_diary.seed_archive(p) == 0
    s = mrp_diary.summarise(pd.read_csv(p, dtype={"sku": str}))
    assert "0 price change" in s and "diagnostic only" in s


def test_panel_level_is_balanced_and_geometric():
    import numpy as np, pandas as pd
    from rpi.collectors import doca
    idx = pd.date_range("2025-01-01", periods=4)
    df = pd.DataFrame({str(i): [10.0 * (i + 1)] * 4 for i in range(6)}, index=idx)
    df["late"] = [np.nan, 99, 99, 99]                       # a centre that enters late must not move the level
    lvl = doca.panel_level(df)
    assert list(lvl.round(6).unique()) == [round(float(np.exp(np.log([10, 20, 30, 40, 50, 60]).mean())), 6)]
    df2 = df.copy(); df2.loc[idx[-1], "late"] = 5000
    assert doca.panel_level(df2).equals(lvl)


def test_panel_needs_enough_centres():
    import pandas as pd, pytest
    from rpi.collectors import doca
    with pytest.raises(ValueError):
        doca.panel_level(pd.DataFrame({"1": [1.0, 2.0], "2": [1.0, 2.0]}, index=pd.date_range("2025-01-01", periods=2)))


def test_parse_mapseries_zero_is_missing():
    import json
    from rpi.collectors import doca
    df = doca.parse_mapseries(json.dumps({"dates": ["2025-01-01", "2025-01-02"], "centres": {"7": [10, 0], "8": [20, 21]}}))
    assert df.loc["2025-01-02", "7"] != df.loc["2025-01-02", "7"] and df.loc["2025-01-02", "8"] == 21


def test_national_items_are_proxy_bucket():
    from rpi.proxy_check import PROXY_SOURCES, RETAIL_SOURCES
    assert "doca_national" in PROXY_SOURCES and "doca_national" not in RETAIL_SOURCES


def test_chai_is_proxy_with_conservative_step():
    import pandas as pd
    from rpi.proxy_check import PROXY_ITEMS
    assert "D002" in PROXY_ITEMS
    ev = pd.read_csv("data/tariff_events.csv")
    ev = ev[ev["item_id"] == "D002"].sort_values("effective_from")
    vals = ev["price"].astype(float).tolist()
    assert abs(vals[-1] / vals[0] - 1 - 0.1538) < 0.001
    b = pd.read_csv("data/basket.csv", dtype=str)
    assert b.loc[b.item_id == "D002", "tier"].iloc[0] == "C"


def test_superseded_local_feeds_stay_out_of_the_index():
    import sqlite3
    from rpi.superseded import sql_clause, SUPERSEDED_ITEMS
    assert set(SUPERSEDED_ITEMS) == {"F003", "F005", "F020", "F024"}
    c = sqlite3.connect(":memory:")
    c.executescript("CREATE TABLE products(sku_id, item_id, source_id);"
                    "INSERT INTO products VALUES('a','F003','mandi_rajkot_apmc'),('b','F003','doca_national'),"
                    "('c','F006','doca_rajkot'),('d','F020','necc_ahmedabad');")
    got = {r[0] for r in c.execute("SELECT sku_id FROM products p WHERE " + sql_clause("p"))}
    assert got == {"b", "c"}


def test_four_national_items_are_wired_and_proxy():
    import pandas as pd
    from rpi.collectors.doca import NATIONAL_WIRED
    assert {v[0] for v in NATIONAL_WIRED.values()} >= {"F003", "F005", "F020", "F024"}
    p = pd.read_csv("data/source_plan.csv", dtype=str).set_index("item_id")
    assert all(p.loc[i, "primary_source"] == "doca_national" for i in ("F003", "F005", "F020", "F024"))
