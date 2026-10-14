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
    assert set(SUPERSEDED_ITEMS) == {"F003", "F005", "F020", "F021", "F024"}
    c = sqlite3.connect(":memory:")
    c.executescript("CREATE TABLE products(sku_id, item_id, source_id);"
                    "INSERT INTO products VALUES('a','F003','mandi_rajkot_apmc'),('b','F003','doca_national'),"
                    "('c','F006','doca_rajkot'),('d','F020','necc_ahmedabad'),"
                    "('e','F021','mandi_gondal'),('f','F021','doca_gujarat');")
    got = {r[0] for r in c.execute("SELECT sku_id FROM products p WHERE " + sql_clause("p"))}
    assert got == {"b", "c", "f"}


def test_national_panel_keeps_only_the_items_without_a_passing_rajkot_series():
    # 2026-10-14: F002/F003/F005/F008 left this panel for the Rajkot centre (they pass the long-window gate there and the panel is a
    # proxy); what remains is exactly the items no Rajkot series can carry, and the plan must agree with the collector.
    import pandas as pd
    from rpi.collectors.doca import NATIONAL_WIRED
    assert {v[0] for v in NATIONAL_WIRED.values()} == {"F011", "F020", "F024"}
    p = pd.read_csv("data/source_plan.csv", dtype=str).set_index("item_id")
    assert all(p.loc[i, "primary_source"] == "doca_national" for i in ("F011", "F020", "F024"))
    assert all(p.loc[i, "primary_source"] == "doca_rajkot" for i in ("F002", "F003", "F005", "F008"))


def test_gujarat_panel_is_retired_and_potato_moved_to_the_rajkot_centre():
    # 2026-10-14: the Rajkot centre passes the gate for potato over 150 months under the long comparator, so the most local passing
    # series wins and the Gujarat panel - whose only item this was - is empty and unregistered (rpi/refresh.py).
    import pandas as pd
    from rpi.collectors.doca import GUJARAT_WIRED, WIRED
    assert GUJARAT_WIRED == {}
    assert {i for i, _ in WIRED.values() if i == "F021"}
    p = pd.read_csv("data/source_plan.csv", dtype=str).set_index("item_id")
    assert p.loc["F021", "primary_source"] == "doca_rajkot"
    assert "doca_gujarat" not in set(p.primary_source)
    # the old short-window screen said otherwise; it is retained for provenance only
    s = pd.read_csv("data/official/doca_panel_screen.csv", dtype={"doca_commodity": str}).set_index("item_id")
    assert s.loc["F021", "wire_to"] == "gujarat" and s.loc["F021", "rajkot_verdict"] != "pass"
