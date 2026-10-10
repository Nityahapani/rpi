import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from rpi import switches as sw
from rpi.config import ROOT

RULES = {"F001": ("rajkot_shops", "2026-11")}


def _db(tmp_path):
    c = sqlite3.connect(tmp_path / "t.sqlite")
    c.executescript("""
        CREATE TABLE products(sku_id TEXT PRIMARY KEY, item_id TEXT, source_id TEXT);
        CREATE TABLE observations(obs_date TEXT, sku_id TEXT, pincode TEXT, price REAL, unit_price REAL, in_stock INTEGER);
        INSERT INTO products VALUES ('mandi','F001','mandi_rajkot_apmc'), ('shop','F001','rajkot_shops'), ('other','F002','doca_national');
        INSERT INTO observations VALUES
          ('2026-08-10','mandi','p',1,1,1),
          ('2026-09-10','mandi','p',1,1,1),
          ('2026-10-05','mandi','p',1,1,1),
          ('2026-10-09','shop','p',1,1,1),
          ('2026-10-20','mandi','p',1,1,1),
          ('2026-11-05','shop','p',1,1,1),
          ('2026-11-06','mandi','p',1,1,1),
          ('2026-09-10','shop','p',1,1,1),
          ('2026-11-06','other','p',1,1,1);
    """)
    return c


def _kept(c, rules):
    q = f"SELECT o.obs_date, p.source_id FROM observations o JOIN products p ON p.sku_id=o.sku_id WHERE {sw.clause(rules=rules)} ORDER BY 1,2"
    return c.execute(q).fetchall()


def test_no_rules_keeps_everything(tmp_path):
    c = _db(tmp_path)
    assert len(_kept(c, {})) == 9


def test_old_source_stops_at_the_switch_month_and_new_source_starts_at_the_link_month(tmp_path):
    kept = _kept(_db(tmp_path), RULES)
    # old source: up to Oct kept, Nov dropped
    assert ("2026-10-05", "mandi_rajkot_apmc") in kept and ("2026-10-20", "mandi_rajkot_apmc") in kept
    assert all(not (d >= "2026-11-01" and s == "mandi_rajkot_apmc") for d, s in kept)
    # new source: Sep (before the link month Oct) dropped; Oct (link month) and Nov kept
    assert ("2026-09-10", "rajkot_shops") not in kept
    assert ("2026-10-09", "rajkot_shops") in kept and ("2026-11-05", "rajkot_shops") in kept
    # items without a switch are untouched, even in Nov
    assert ("2026-11-06", "doca_national") in kept


def test_link_month_is_the_month_before_the_switch(tmp_path):
    c = _db(tmp_path)
    kept = _kept(c, {"F001": ("rajkot_shops", "2026-10")})
    assert ("2026-09-10", "rajkot_shops") in kept                      # Sep is the link month when the switch is Oct


def test_rules_are_validated(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text('[index.switches]\nF001 = ["rajkot_shops", "2026-13x"]\n')
    sw._load.cache_clear()
    with pytest.raises(ValueError):
        sw.load(p)
    sw._load.cache_clear()


def test_settings_switches_agree_with_the_plan():
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str, keep_default_na=False)
    assert sw.check_against_plan(plan) == []
    rules = sw.load()
    assert set(rules) == {"F001", "F004", "F007", "F016"}


def test_wholesale_calibration_stops_at_the_switch_month():
    import numpy as np
    from rpi.seasonal import calibrate_wholesale
    rel = pd.DataFrame({"F001": [0.0, 0.01, 0.02]}, index=pd.PeriodIndex(["2026-08", "2026-10", "2026-11"], freq="M"))
    n = pd.DataFrame({"F001": [5, 5, 5]}, index=rel.index)
    cal = {"F001": {"b0": -0.002, "sigma_wb": 0.0082, "sigma_prior": 0.0098}}
    tables = {"F001": (0.01, np.zeros(12))}                             # prior = 1% a month
    cutoffs = {"F001": "2025-01"}
    base, _ = calibrate_wholesale(rel, n, cutoffs, cal, tables, switch_from={})
    cut, _ = calibrate_wholesale(rel, n, cutoffs, cal, tables, switch_from={"F001": "2026-11"})
    assert base.loc["2026-11", "F001"] != 0.02                           # without a switch the wholesale beta still applies
    assert cut.loc["2026-10", "F001"] == base.loc["2026-10", "F001"]     # before the switch month: unchanged
    assert cut.loc["2026-11", "F001"] == 0.02                            # from the switch month: raw retail relative
