"""Eighth sweep: DoCA Rajkot retail quotes (mirror fidelity proof, collector, gate, coverage bucket)."""
import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest

from rpi import db
from rpi.collectors import doca
from rpi.index.engine import SINGLE_SERIES_SOURCES
from rpi.proxy_check import GATED_SOURCES, judge
from rpi.quality import coverage_split

ROOT = Path(__file__).resolve().parent.parent
FX = Path(__file__).parent / "fixtures"


def _home():
    return (FX / "doca_home.html").read_text()


def _mirror_for(home_html, perturb=None, date=None):
    day, vals = doca.parse_doca_home(home_html)
    names = list(vals)
    meta = {"commodities": [{"id": i + 1, "name": n} for i, n in enumerate(names)]}
    nat = {str(i + 1): {"avg": vals[n] + (perturb or {}).get(n, 0.0)} for i, n in enumerate(names)}
    return json.dumps(meta), json.dumps({"date": date or str(day), "national": nat})


def test_parse_doca_home_reads_all_retail_commodities():
    day, v = doca.parse_doca_home(_home())
    assert day == dt.date(2026, 10, 1) and len(v) >= 40
    assert v["Sugar"] == 55.62 and v["Salt Pack (Iodised)"] == 22.47 and v["Garlic"] == 45.44      # first / last in their blocks
    assert "Rice" in v and not any("Wholesale" in k or "Average" in k for k in v)


def test_mirror_check_agrees_when_identical_and_flags_any_difference():
    meta, mp = _mirror_for(_home())
    assert all(r["verdict"] == "agree" for r in doca.check_mirror(_home(), meta, mp))
    meta, mp = _mirror_for(_home(), perturb={"Sugar": 0.5})
    bad = [r for r in doca.check_mirror(_home(), meta, mp) if r["verdict"] != "agree"]
    assert [r["commodity"] for r in bad] == ["Sugar"]
    meta, mp = _mirror_for(_home(), date="2026-09-30")                 # a stale mirror must not be trusted either
    assert doca.check_mirror(_home(), meta, mp)[0]["verdict"] == "date_mismatch"


def test_parse_history_drops_nulls_and_zeros():
    txt = json.dumps({"points": [["2026-09-01", 42.0], ["2026-09-02", None], ["2026-09-03", 0], ["2026-09-04", 43.0]]})
    assert doca.parse_history(txt) == [(dt.date(2026, 9, 1), 42.0), (dt.date(2026, 9, 4), 43.0)]


class _Resp:
    status_code = 200

    def __init__(self, text):
        self.text, self.content, self.url = text, text.encode(), "u"


class _Client:
    def __init__(self, last):
        self.last = last

    def get(self, url, params=None):
        d0, pts = dt.date(2026, 9, 1), []
        while d0 <= self.last:
            pts.append([d0.isoformat(), 50.0]); d0 += dt.timedelta(days=1)
        return _Resp(json.dumps({"points": pts}))


def test_collector_units_and_staleness():
    obs = list(doca.DocaRetailCollector(_Client(dt.date(2026, 10, 1))).collect(dt.date(2026, 10, 2)))
    assert {o.item_id for o in obs} == {"F006", "F013", "F026"}
    oil = [o for o in obs if o.item_id == "F006"][0]
    assert (oil.qty_base, oil.base_unit) == (1000.0, "ml") and oil.price == 50.0          # Rs per litre
    sugar = [o for o in obs if o.item_id == "F013"][0]
    assert (sugar.qty_base, sugar.base_unit) == (1000.0, "g")
    with pytest.raises(RuntimeError, match="stale"):
        list(doca.DocaRetailCollector(_Client(dt.date(2026, 9, 10))).collect(dt.date(2026, 10, 2)))


def test_gate_rejects_a_series_that_drifts_from_the_official_index():
    m = [f"2025-{i:02d}" for i in range(1, 13)]
    off = pd.Series(range(100, 112), index=m, dtype=float)
    good = off * 1.01
    bad = pd.Series([100.0 + 3 * i for i in range(12)], index=m)           # +33% against +11%
    assert judge(good, off)["verdict"] == "pass"
    assert judge(bad, off)["verdict"] == "fail"


def test_every_planned_source_is_single_series_aware_and_doca_is_gated():
    # A new primary source that is missing from SINGLE_SERIES_SOURCES is silently IMPUTED for tier-A items (min_matched=2):
    # this exact bug made sugar and groundnut oil read as a division mean until it was caught on 2026-10-02.
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str, keep_default_na=False)
    used = set(plan.primary_source) - {"none"}
    assert used <= set(SINGLE_SERIES_SOURCES), used - set(SINGLE_SERIES_SOURCES)
    assert "doca_rajkot" in GATED_SOURCES
    assert set(plan.loc[plan.primary_source == "doca_rajkot", "item_id"]) == {i for i, _ in doca.WIRED.values()}


def test_repo_wired_doca_items_have_a_gate_pass_history():
    # the data committed in the repo must still satisfy the gate that justified wiring the three items
    off = pd.read_csv(ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
    off = off[off.level == "item"].pivot_table(index="period", columns="code", values="index_value", aggfunc="first")
    mp = pd.read_csv(ROOT / "data/basket_official_map.csv", dtype=str, keep_default_na=False).set_index("item_id")
    conn = db.connect(ROOT / "data/rpi.sqlite")
    for item in ("F006", "F013", "F026"):
        q = pd.read_sql_query("SELECT substr(o.obs_date,1,7) m, AVG(o.unit_price) v FROM observations o JOIN products p ON p.sku_id=o.sku_id "
                              "WHERE p.item_id=? AND p.source_id='doca_rajkot' GROUP BY 1", conn, params=[item]).set_index("m")["v"]
        assert len(q) >= 18
        assert judge(q, off[mp.loc[item, "official_item_code"]].dropna())["verdict"] == "pass", item


def test_coverage_split_has_separate_retail_bucket(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str, keep_default_na=False)
    w = pd.DataFrame({"item_id": plan.item_id, "weight": 1.0})
    w.to_sql("weights", conn, if_exists="append", index=False)
    s = coverage_split(conn, ROOT / "data/source_plan.csv")["independent_split_pct"]
    retail = [v for k, v in s.items() if k.startswith("retail")]
    assert len(retail) == 1 and abs(retail[0] - 3 / len(plan) * 100) < 0.1
    assert abs(sum(s.values()) - plan[plan["class"] == "independent"].shape[0] / len(plan) * 100) < 0.2
