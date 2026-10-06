import datetime as dt
import json
import pandas as pd
from pathlib import Path
from rpi.collectors import cinema_diary as C, fresha_salon as F
ROOT = Path(__file__).resolve().parents[1]


def ev(start, price, fmt="2D"):
    return '<script type="application/ld+json">' + json.dumps(dict({"@type": "ScreeningEvent", "name": "X", "startDate": start, "videoFormat": fmt, "offers": {"@type": "Offer", "price": price}})) + "</script>"


def test_cinema_day_price_is_cheapest_weekday_evening_2d():
    html = "".join([ev("2026-10-07T12:00:00+05:30", 90), ev("2026-10-07T18:15:00+05:30", 240), ev("2026-10-07T19:00:00+05:30", 200),
                    ev("2026-10-07T22:00:00+05:30", 260), ev("2026-10-07T20:00:00+05:30", 120, "3D")])
    d, p, n = C.day_price(C.parse_events(html))
    assert (d, p, n) == (dt.date(2026, 10, 7), 200.0, 3)      # noon show, 3D show excluded


def test_cinema_skips_weekends_and_thin_days():
    wk = "".join(ev(f"2026-10-10T{h}:00:00+05:30", 200) for h in (18, 19, 20))     # Saturday
    assert C.day_price(C.parse_events(wk)) is None
    assert C.day_price(C.parse_events(ev("2026-10-07T18:00:00+05:30", 200))) is None


def test_fresha_menu_parser_reads_both_layouts():
    a = '"__typename":"Service","caption":"20 min","formattedRetailPrice":"from ₹1,000","id":"s:11","name":"Cut ","retailPrice":{"currency":"INR","value":1000},"variants":[]'
    b = '"__typename":"Service","name":"Wash","caption":"5 min","id":"s:12","retailPrice":{"currency":"INR","value":250.0}'
    assert F.parse_menu(a + "}," + b) == {"11": ("Cut", 1000.0), "12": ("Wash", 250.0)}


def test_pools_collectors_and_plan_wiring():
    from rpi.collectors.official_link import BACKFILL_SOURCES
    from rpi.index.engine import SINGLE_SERIES_SOURCES
    from rpi.proxy_check import PROXY_SOURCES, MULTI_SKU_SOURCES
    for s in ("district_cinema", "fresha_salon"):
        for tup in (BACKFILL_SOURCES, SINGLE_SERIES_SOURCES, PROXY_SOURCES, MULTI_SKU_SOURCES):
            assert s in tup
    assert len(pd.read_csv(ROOT / "data/cinema/pool.csv")) == 8
    assert len(pd.read_csv(ROOT / "data/fresha/pool.csv")) >= 90
    co = list(C.CinemaCollector(ROOT).collect(None))
    fo = list(F.FreshaCollector(ROOT).collect(None))
    assert co and all(o.item_id == "S001" and o.price > 0 for o in co)
    assert len(fo) >= 250 and all(o.item_id == "P004" and o.price > 0 for o in fo)
    plan = pd.read_csv(ROOT / "data/source_plan.csv").set_index("item_id")
    assert plan.loc["S001", "primary_source"] == "district_cinema" and plan.loc["P004", "primary_source"] == "fresha_salon"


def test_gates_stay_pending_until_six_overlapping_months():
    off = ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv"
    assert F.gate(ROOT / "data/fresha/prices.csv", off)["verdict"] == "pending"
    assert C.gate(ROOT / "data/cinema/live_prices.csv", off)["verdict"] == "pending"
