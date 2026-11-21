"""Regression: re-ingesting unchanged history must not move fetched_at forward.

2026-11-07 incident: DocaRetailCollector re-yields its full history since
2014-01 on every refresh. persist() used INSERT OR REPLACE with
fetched_at=now(), so one refresh stamped all 55,622 historical rows with
the refresh date. The as-of vintage test
(test_items_backtest::test_as_of_panel_contains_no_same_day_or_later_source_fetches,
cutoff 2026-10-16) then saw an empty panel and the daily workflow failed
every day from 2026-11-08, because pytest runs before the refresh.
"""
import datetime as dt

import pandas as pd

from rpi import db, ingest
from rpi.collectors.base import Observation
from rpi.config import ROOT


def _conn(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    ingest.load_basket(conn, pd.read_csv(ROOT / "data/basket.csv", dtype={"division": str}))
    ingest.load_weights(conn, pd.read_csv(ROOT / "data/weights_cpi2024_gujarat_urban.csv"))
    return conn


def _fetched(conn):
    return conn.execute(
        "SELECT fetched_at FROM observations WHERE sku_id='doca_rajkot:doca1|Rajkot' AND obs_date='2025-03-01'"
    ).fetchone()[0]


def test_reingest_unchanged_price_preserves_fetched_at(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    obs = [Observation(dt.date(2025, 3, 1), "doca_rajkot", "doca1|Rajkot",
                       "DoCA test", "F002", "DOCA:Rajkot", 42.0, qty_base=1000.0, base_unit="g")]
    monkeypatch.setattr(ingest, "now_iso", lambda: "2026-10-14T00:00:00+00:00")
    ingest.persist(conn, obs)
    assert _fetched(conn) == "2026-10-14T00:00:00+00:00"

    # Full-history re-yield weeks later, same price: vintage must not move.
    monkeypatch.setattr(ingest, "now_iso", lambda: "2026-11-07T00:00:00+00:00")
    ingest.persist(conn, obs)
    assert _fetched(conn) == "2026-10-14T00:00:00+00:00"
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1


def test_reingest_revised_price_gets_new_fetched_at(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(ingest, "now_iso", lambda: "2026-10-14T00:00:00+00:00")
    ingest.persist(conn, [Observation(dt.date(2025, 3, 1), "doca_rajkot", "doca1|Rajkot",
                                      "DoCA test", "F002", "DOCA:Rajkot", 42.0, qty_base=1000.0, base_unit="g")])
    # A revised price is new information: it was not known at the old vintage.
    monkeypatch.setattr(ingest, "now_iso", lambda: "2026-11-07T00:00:00+00:00")
    ingest.persist(conn, [Observation(dt.date(2025, 3, 1), "doca_rajkot", "doca1|Rajkot",
                                      "DoCA test", "F002", "DOCA:Rajkot", 43.5, qty_base=1000.0, base_unit="g")])
    assert _fetched(conn) == "2026-11-07T00:00:00+00:00"
    assert conn.execute("SELECT price FROM observations").fetchone()[0] == 43.5
