"""Eighth sweep: DoCA Rajkot retail quotes (mirror fidelity proof, collector, gate, coverage bucket)."""
import datetime as dt
import json
from pathlib import Path

import numpy as np
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
    assert {o.item_id for o in obs} == {i for i, _ in doca.WIRED.values()}
    # the ingest window must start with the official comparator, not the index base year: gate power is the months the proxy and the
    # official series BOTH cover, so a 2025-01 window would throw away 11 of the comparator's 12 years (2026-10-14).
    assert doca.START <= "2014-01-01"
    oil = [o for o in obs if o.item_id == "F006"][0]
    assert (oil.qty_base, oil.base_unit) == (1000.0, "ml") and oil.price == 50.0          # Rs per litre
    sugar = [o for o in obs if o.item_id == "F013"][0]
    assert (sugar.qty_base, sugar.base_unit) == (1000.0, "g")
    with pytest.raises(RuntimeError, match="stale"):
        list(doca.DocaRetailCollector(_Client(dt.date(2026, 9, 10))).collect(dt.date(2026, 10, 2)))


def test_monthly_gate_remains_decisive_while_long_legs_are_individually_pending():
    m = [f"2025-{i:02d}" for i in range(1, 13)]
    off = pd.Series(range(100, 112), index=m, dtype=float)
    good = off * 1.01
    bad = pd.Series([100.0 + 3 * i for i in range(12)], index=m)           # +33% against +11%
    assert judge(good, off)["verdict"] == "pass"
    assert judge(good, off)["legs"] == ["A"]                            # constant level offset is admissible
    j = judge(bad, off)
    assert j["verdict"] == "pending"                                   # B and C are still unevaluable
    assert j["legs"] == []
    assert j["leg_status"] == {"A": "fail", "B": "pending", "C": "pending"}


def test_long_series_fails_only_when_all_three_legs_are_evaluable_and_fail():
    months = pd.period_range("2020-01", periods=60, freq="M")
    rng = np.random.default_rng(1)
    official = pd.Series(np.exp(np.log(100.0) + np.cumsum(rng.normal(0.004, 0.02, len(months)))), index=months)
    proxy = pd.Series(np.exp(np.log(100.0) + np.cumsum(rng.normal(0.002, 0.03, len(months)))), index=months)
    j = judge(proxy, official)
    assert j["leg_status"] == {"A": "fail", "B": "fail", "C": "fail"}
    assert j["verdict"] == "fail" and j["legs"] == []


def test_refresh_preserves_upstream_source_snapshot_manifest(tmp_path):
    import json
    from rpi.refresh import source_snapshot_metadata

    assert source_snapshot_metadata(tmp_path) is None
    manifest = {"repository": "https://github.com/Nityahapani/rpi", "bot_commit": "abc123", "bot_run_id": "20261016T094753877494Z"}
    path = tmp_path / "data/source_snapshot.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert source_snapshot_metadata(tmp_path) == manifest


def test_prereg_arrival_ledger_is_not_backfilled_from_the_2014_splice():
    seen = pd.read_csv(ROOT / "data/preregistered/official_seen.csv", dtype={"item_id": str, "period": str})
    assert len(seen) > 0
    assert seen.period.min() >= "2025-01"
    assert set(seen.loc[seen.item_id == "K003", "period"]) <= {"2026-09"}


def test_prereg_arrival_selection_skips_history_for_newly_gated_items(tmp_path):
    from rpi.refresh import _prereg_official_arrivals

    months = pd.period_range("2025-01", "2026-09", freq="M").astype(str)
    seen = pd.DataFrame({"item_id": "F002", "period": months[:-1], "first_seen_on": "2026-10-07", "bootstrap": True})
    path = tmp_path / "data/preregistered/official_seen.csv"
    path.parent.mkdir(parents=True)
    seen.to_csv(path, index=False)
    vals = pd.Series(range(len(months)), index=months, dtype=float)
    chosen = _prereg_official_arrivals(tmp_path, {"F002": vals, "K003": vals})
    assert list(chosen["F002"].index.astype(str)) == ["2026-09"]
    assert list(chosen["K003"].index.astype(str)) == ["2026-09"]


def test_proxy_validation_csv_keeps_sources_verdicts_and_every_leg(tmp_path):
    import json
    import pandas as pd
    from rpi.refresh import write_proxy_validation

    path = write_proxy_validation(tmp_path / "docs/data/proxy_validation.csv", [
        {"item_id": "F008", "source_id": "doca_rajkot", "gate_type": "A/B/C", "n_overlap": 150,
         "verdict": "pass", "legs": ["B", "C"], "leg_status": {"A": "fail", "B": "pass", "C": "pass"}},
        {"item_id": "R001", "source_id": "rent_signal", "gate_type": "trend", "n_overlap": 21,
         "verdict": "fail", "legs": [], "leg_status": {"A": "n/a", "B": "n/a", "C": "n/a"}},
    ])
    d = pd.read_csv(path, dtype=str, keep_default_na=False).set_index("item_id")
    assert d.loc["F008", "source_id"] == "doca_rajkot"
    assert d.loc["F008", "legs"] == "B+C"
    assert json.loads(d.loc["F008", "leg_status"]) == {"A": "fail", "B": "pass", "C": "pass"}
    assert d.loc["R001", "gate_type"] == "trend" and d.loc["R001", "legs"] == ""


def test_C_recent_drift_is_pending_without_the_exact_24_month_anchor():
    months = pd.period_range("2024-01", periods=36, freq="M")
    rng = np.random.default_rng(1)
    official = pd.Series(np.exp(np.log(100.0) + np.cumsum(rng.normal(0.004, 0.02, len(months)))), index=months)
    proxy = pd.Series(np.exp(np.log(100.0) + np.cumsum(rng.normal(0.003, 0.03, len(months)))), index=months)
    anchor = months[-1] - 24
    official = official.drop(anchor)
    proxy = proxy.drop(anchor)

    j = judge(proxy, official)
    assert j["n_overlap"] == 35
    assert j["drift_recent"] is None
    assert j["leg_status"] == {"A": "fail", "B": "fail", "C": "pending"}
    assert j["verdict"] == "pending" and j["legs"] == []  # C remains unevaluable, so the overall gate is pending.


def test_long_gate_reports_B_and_C_independently():
    # A proportional level relation with slope 2 fails C (slope outside [0.5, 1.5]) and
    # full-window drift, but its annual changes still track: B must pass on its own.
    months = pd.period_range("2010-01", periods=60, freq="M")
    rng = np.random.default_rng(7)
    log_off = np.log(100.0) + np.cumsum(0.01 + rng.normal(0, 0.003, len(months)))
    official = pd.Series(np.exp(log_off), index=months)
    proxy = pd.Series(np.exp(2 * log_off + 1.0), index=months)
    j = judge(proxy, official)
    assert j["verdict"] == "pass" and j["legs"] == ["B"]
    assert j["leg_status"] == {"A": "fail", "B": "pass", "C": "fail"}
    assert j["corr_12m"] == 1.0 and j["slope"] == 2.0


def test_B_uses_annual_change_correlation_without_a_24_level_floor():
    # Acceptance sets the 24-month minimum for C, not B. With 21 levels there are nine
    # valid calendar-aligned 12-month changes: B can pass independently of A while C stays pending.
    months = pd.period_range("2024-01", periods=21, freq="M")
    rng = np.random.default_rng(77)
    log_off = np.log(100.0) + np.cumsum(0.02 + rng.normal(0, 0.002, len(months)))
    official = pd.Series(np.exp(log_off), index=months)
    proxy = pd.Series(np.exp(2 * log_off + 0.4), index=months)
    j = judge(proxy, official)
    assert j["n_overlap"] == 21
    assert j["verdict"] == "pass" and j["legs"] == ["B"]
    assert j["leg_status"] == {"A": "fail", "B": "pass", "C": "pending"}
    assert j["corr_12m"] == 1.0 and j["r2"] is None


def test_twelve_month_changes_are_calendar_aligned_across_gaps():
    months = pd.period_range("2018-01", periods=48, freq="M")
    rng = np.random.default_rng(15)
    log_off = np.log(100.0) + np.cumsum(rng.normal(0.006, 0.02, len(months)))
    log_proxy = 0.8 * log_off + rng.normal(0, 0.04, len(months))
    keep = months != pd.Period("2019-07", freq="M")
    official = pd.Series(np.exp(log_off[keep]), index=months[keep])
    proxy = pd.Series(np.exp(log_proxy[keep]), index=months[keep])
    got = judge(proxy, official)["corr_12m"]
    # Manual 12-calendar-month pairs from the unbroken source arrays; missing July 2019
    # removes pairs touching that month instead of shifting later pairs by one row.
    aligned = pd.DataFrame({"p": log_proxy, "o": log_off}, index=months).reindex(months)
    aligned.loc[pd.Period("2019-07", freq="M")] = np.nan
    d12 = aligned.diff(12).dropna()
    expected = round(float(d12.p.corr(d12.o)), 2)
    assert got == expected


def test_every_planned_source_is_single_series_aware_and_doca_is_gated():
    # A new primary source that is missing from SINGLE_SERIES_SOURCES is silently IMPUTED for tier-A items (min_matched=2):
    # this exact bug made sugar and groundnut oil read as a division mean until it was caught on 2026-10-02.
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str, keep_default_na=False)
    used = set(plan.primary_source) - {"none"}
    assert used <= set(SINGLE_SERIES_SOURCES), used - set(SINGLE_SERIES_SOURCES)
    assert "doca_rajkot" in GATED_SOURCES
    assert set(plan.loc[plan.primary_source == "doca_rajkot", "item_id"]) == {i for i, _ in doca.WIRED.values()}


def test_doca_promotion_rule_keeps_administered_and_accruing_local_sources():
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str, keep_default_na=False).set_index("item_id")
    assert plan.loc["F009", "primary_source"] == "tariff"      # administered local milk tariff is not displaced
    assert all(plan.loc[i, "primary_source"] == "rajkot_shops" for i in ("F001", "F004", "F007", "F016"))
    assert plan.loc["F025", "primary_source"] == "mandi_gondal"  # explicit exception retained


def test_repo_wired_doca_items_have_a_gate_pass_history():
    # Validate the exact active source series in the committed DB against the required
    # long comparator. This also catches a source excluded by the superseded-feed filter.
    from rpi.proxy_check import validate_proxies
    from rpi.collectors.doca import START, PANEL_START
    assert START == "2014-01-01" and PANEL_START == "2025-01-01"
    conn = db.connect(ROOT / "data/rpi.sqlite")
    wired = {item for item, _ in doca.WIRED.values()}
    plan_path = ROOT / "data/source_plan.csv"
    plan = pd.read_csv(plan_path, dtype=str, keep_default_na=False).set_index("item_id")
    assert set(plan.loc[plan.primary_source == "doca_rajkot"].index) == wired
    series = {}
    results = validate_proxies(
        conn, ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv", ROOT / "data/basket_official_map.csv",
        plan_path, series_out=series, spliced_csv=ROOT / "data/official/official_item_spliced.csv",
    )
    by_item = {r["item_id"]: r for r in results}
    for item in sorted(wired):
        j = by_item[item]
        assert j["source_id"] == "doca_rajkot"
        assert series[item][2] == "doca_rajkot"
        assert j["proxy_months"] > 0
        assert j["verdict"] == "pass", (item, j)
        assert j["n_overlap"] >= 24                    # long overlap, not a thin accidental agreement
        assert j["legs"] and set(j["legs"]) <= {"A", "B", "C"}


def test_promoted_doca_sources_feed_index_and_f025_stays_gondal():
    from rpi.index.panel import load_quotes
    conn = db.connect(ROOT / "data/rpi.sqlite")
    q = load_quotes(conn)
    promoted = {"F002", "F003", "F005", "F008", "F021", "F022", "F023"}
    recent = q[(q.item_id.isin(promoted)) & (q.period >= pd.Period("2025-01", freq="M"))]
    old_sources = {
        "F002": "doca_national", "F003": "doca_national", "F005": "doca_national",
        "F008": "doca_national", "F021": "doca_gujarat", "F022": "mandi_gondal", "F023": "mandi_gondal",
    }
    for item in promoted:
        sources = set(recent.loc[recent.item_id == item, "source_id"])
        assert "doca_rajkot" in sources, item
        assert old_sources[item] not in sources, (item, sources)
    f025 = q[(q.item_id == "F025") & (q.period >= pd.Period("2025-01", freq="M"))]
    assert "mandi_gondal" in set(f025.source_id)
    assert "doca_rajkot" not in set(f025.source_id)


def test_coverage_split_has_separate_retail_bucket(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str, keep_default_na=False)
    w = pd.DataFrame({"item_id": plan.item_id, "weight": 1.0})
    w.to_sql("weights", conn, if_exists="append", index=False)
    s = coverage_split(conn, ROOT / "data/source_plan.csv")["independent_split_pct"]
    retail = [v for k, v in s.items() if k.startswith("retail")]
    from rpi.proxy_check import RETAIL_SOURCES
    n_retail = int((plan.primary_source.isin(RETAIL_SOURCES) & (plan["class"] == "independent")).sum())
    assert len(retail) == 1 and abs(retail[0] - n_retail / len(plan) * 100) < 0.1
    assert abs(sum(s.values()) - plan[plan["class"] == "independent"].shape[0] / len(plan) * 100) < 0.2
