"""Ninth sweep: the Gujarat statutory auto-rickshaw tariff register (T004)."""
from pathlib import Path

import pandas as pd

from rpi.index.engine import SINGLE_SERIES_SOURCES
from rpi.proxy_check import PROXY_ITEMS
from rpi.registry import REVIEW

ROOT = Path(__file__).resolve().parent.parent


def fare(first, per200, km):
    return first + round((km - 1.2) / 0.2) * per200


def test_tariff_arithmetic_matches_the_notified_rates():
    assert fare(20, 3, 3) == 47 and fare(25, 4, 3) == 61                # Rs15/km -> Rs20/km, 1.2 km minimum Rs20 -> 25
    assert fare(20, 3, 1.2) == 20 and fare(25, 4, 1.2) == 25
    steps = [fare(25, 4, k) / fare(20, 3, k) - 1 for k in (2, 3, 5)]
    assert 0.27 < min(steps) and max(steps) < 0.32                        # the trip-length choice moves the step by only +-3 pp


def test_register_rows_and_plan():
    ev = pd.read_csv(ROOT / "data/tariff_events.csv")
    t = ev[ev.item_id == "T004"].sort_values("effective_from")
    assert t.effective_from.tolist() == ["2025-01-01", "2026-08-07"]        # pre-step dated at base month, step at the true date
    assert t.price.tolist() == [47.0, 61.0] and set(t.status) == {"verified"}
    plan = pd.read_csv(ROOT / "data/source_plan.csv").set_index("item_id")
    assert plan.loc["T004", "primary_source"] == "tariff" and plan.loc["T004", "class"] == "independent"
    assert "tariff" in SINGLE_SERIES_SOURCES and "T004" in REVIEW


def test_regulated_maximum_is_counted_as_proxy_not_direct():
    assert "T004" in PROXY_ITEMS


def test_published_item_series_steps_in_august_not_imputed():
    import sqlite3
    c = sqlite3.connect(ROOT / "data/rpi.sqlite")
    r = c.execute("select max(run_id) from index_runs").fetchone()[0]
    v = c.execute("select min(variant) from index_results where run_id=?", (r,)).fetchone()[0]
    x = dict(c.execute("select period,value from index_results where run_id=? and variant=? and level='item' and key='T004'", (r, v)).fetchall())
    assert abs(x["2026-07"] - 100) < 0.01 and abs(x["2026-09"] - 100 * 61 / 47) < 0.05
    assert 100 * 61 / 47 > x["2026-08"] > 115                              # August blends 6 old days with 25 new days


def test_t004_event_check_waits_for_official_september():
    from rpi.event_check import check_events
    r = {e["item_id"]: e for e in check_events(ROOT)}["T004"]
    assert r["verdict"] in ("official_not_yet_published", "aligned", "official_muted", "official_overshoots")
    if r["verdict"] == "official_not_yet_published":
        assert r["pre"] == "2026-07" and r["post"] == "2026-09"             # partial effective month skipped


def test_rent_listings_parse_dedupe_and_junk_screen(tmp_path):
    from rpi.collectors import rent_listings as rl
    html = (ROOT / "tests/fixtures/magicbricks_rent_rajkot.html").read_text()
    rows = rl.parse_listings(html)
    assert len(rows) == 30 and all(r["rent"] > 0 and r["listed"].startswith("2026") for r in rows)
    p = tmp_path / "r.csv"
    assert rl.update_file(p, html, "u", __import__("datetime").date(2026, 10, 2)) == (30, 30)
    assert rl.update_file(p, html, "u", __import__("datetime").date(2026, 10, 3)) == (30, 0)       # idempotent
    st = {s["month"]: s for s in rl.monthly_stats(p)}
    assert st["2026-09"]["n_kept"] <= st["2026-09"]["n_listings"]
    assert rl.qualifying_months(list(st.values())) < 2                  # one page of 30 listings never qualifies as an index
    df = pd.read_csv(p)
    assert (df.rent == 75000).any() and not (rl.clean(df).rent == 75000).any()        # the Rs75,000 one-bedroom typo is screened out


def test_mrp_events_from_archive_carry_forward_and_midpoint_dating():
    import datetime as dt
    from rpi.collectors import mrp
    arc = pd.DataFrame([
        ("C001", "h1", "S1", 20241204000000, 549.0), ("C001", "h1", "S1", 20250320000000, 549.0),     # unchanged -> no event
        ("C001", "h1", "S1", 20250910000000, 579.0),                                                  # change bracketed by 20 Mar and 10 Sep 2025
        ("C001", "h2", "S2", 20250301000000, 499.0),                                                  # first snapshot after base -> derived
    ], columns=["item_id", "handle", "sku", "ts", "price"])
    rows = pd.DataFrame(mrp.events_from_archive(arc, dt.date(2026, 10, 2), live={"S1": 599.0, "S2": 499.0}))
    s1 = rows[rows.series == "jockey:S1"].sort_values("effective_from")
    assert s1.effective_from.tolist() == ["2025-01-01", "2025-06-15", "2026-03-22"] and s1.price.tolist() == [549.0, 579.0, 599.0]
    assert set(s1.status[1:]) == {"derived"}                                                          # bracket midpoints are never 'verified'
    s2 = rows[rows.series == "jockey:S2"]
    assert s2.status.tolist() == ["derived"] and s2.price.tolist() == [499.0]


def test_mrp_live_update_only_on_change_and_warns_when_missing():
    import datetime as dt
    from rpi.collectors import mrp
    ev = pd.DataFrame([dict(item_id="C001", series="jockey:S1", effective_from="2025-01-01", price=549.0),
                       dict(item_id="C001", series="jockey:S2", effective_from="2025-01-01", price=499.0),
                       dict(item_id="C002", series="jockey:S3", effective_from="2025-01-01", price=799.0)])
    pool = pd.DataFrame([dict(item_id="C001", sku="S1"), dict(item_id="C001", sku="S2"), dict(item_id="C002", sku="S3")])
    live = {"S1": (579.0, "h1"), "S2": (499.0, "h2")}                    # S1 repriced, S2 unchanged, S3 gone
    new, warn = mrp.live_updates(ev, pool, live, dt.date(2026, 10, 2))
    assert [(n["series"], n["price"]) for n in new] == [("jockey:S1", 579.0)] and warn == ["S3 missing from live feed"]
    prods = [{"handle": "h", "variants": [{"option1": "S", "sku": "a", "price": "1.00"}, {"option1": "M", "sku": "b", "price": "579.00"}]}]
    assert mrp.parse_live(prods) == {"b": (579.0, "h")}                   # size M only


def test_mrp_monthly_index_is_jevons_of_base_relatives():
    import datetime as dt
    from rpi.collectors import mrp
    ev = pd.DataFrame([dict(item_id="C001", series="jockey:A", effective_from="2025-01-01", price=100.0),
                       dict(item_id="C001", series="jockey:A", effective_from="2025-03-01", price=121.0),
                       dict(item_id="C001", series="jockey:B", effective_from="2025-01-01", price=200.0)])
    s = mrp.monthly_index(ev, "C001", dt.date(2025, 3, 31))
    assert round(s["2025-01"], 6) == 100 and round(s["2025-03"], 3) == round(100 * (1.21 ** 0.5), 3)       # sqrt(1.21 x 1.0) = 1.10
