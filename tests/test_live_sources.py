"""Tests for the dynamic real-data layer. Fixtures are table-only snapshots of the live pages (tests/fixtures/)."""
import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from rpi.collectors import labour_bureau as lb
from rpi.collectors import web_sources as w
from rpi.collectors.official_link import OfficialLinkCollector, linked_items
from rpi.fuel_events import update_events
from rpi.index.engine import price_update_weights
from rpi.quality import coverage_split

ROOT = Path(__file__).resolve().parent.parent
FX = Path(__file__).parent / "fixtures"


def fx(name):
    return (FX / name).read_text()


# ---- parsers ---------------------------------------------------------------------------------------------------
def test_parse_fuel_history():
    s = w.parse_gr_daily_fuel(fx("gr_petrol.html"))
    assert len(s) >= 8 and s[0][0] > s[-1][0]            # newest first
    assert 80 < s[0][1] < 130


def test_parse_lpg_monthly():
    m = dict(w.parse_gr_lpg_monthly(fx("gr_lpg.html")))
    assert m["2026-09"] == 947.0 and m["2026-03"] == 918.0 and m["2026-01"] == 858.0


def test_parse_gold_silver_units():
    d, k24, k22 = w.parse_gr_gold(fx("gr_gold.html"))[0]
    assert k24 > k22 > 5000                              # Rs per gram, 24K above 22K
    ds, ag = w.parse_gr_silver(fx("gr_silver.html"))[0]
    assert 50 < ag < 1000                                # converted from Rs/10g to Rs/g
    assert d == ds


def test_parse_mandi_rows():
    rows = w.parse_mandi_commodity(fx("mandi_tomato.html"))
    assert len(rows) >= 5
    d, mn, mx, modal, market = rows[0]
    assert mn <= modal <= mx and "Gondal" in market


def test_outlier_cleaner_removes_glitch():
    base = dt.date(2026, 9, 1)
    s = [(base + dt.timedelta(days=i), 102.0 + 0.1 * (i % 3)) for i in range(10)]
    s[5] = (s[5][0], 117.61)
    out = w.clean_outliers(s)
    assert all(p < 110 for _, p in out) and len(out) == 9


def test_real_fixture_has_no_glitch_after_cleaning():
    out = w.clean_outliers(w.parse_gr_daily_fuel(fx("gr_petrol.html")))
    assert max(p for _, p in out) < 110


# ---- fuel event updater ---------------------------------------------------------------------------------------
def _events():
    return pd.DataFrame([
        dict(item_id="T001", effective_from="2026-05-25", price=100.0, status="verified", source_class="primary",
             source_url="u", retrieved="2026-10-01", note="hike"),
        dict(item_id="T001", effective_from="2026-09-28", price=101.0, status="derived", source_class="derived",
             source_url="u", retrieved="2026-10-01", note="Monthly mean estimated from X"),
        dict(item_id="R003", effective_from="2026-06-01", price=900.0, status="verified", source_class="primary",
             source_url="u", retrieved="2026-10-01", note="lpg"),
    ])


def _pages():
    return {"T001": fx("gr_petrol.html"), "T002": fx("gr_diesel.html"), "R003": fx("gr_lpg.html")}


def test_update_events_replaces_derived_and_adds_scraped():
    new, log = update_events(_events(), _pages(), dt.date(2026, 10, 2))
    t1 = new[new.item_id == "T001"]
    assert not t1.note.fillna("").str.startswith("Monthly mean estimated").any()
    assert (t1.status == "scraped").sum() >= 1
    assert any("replaced" in l for l in log)
    assert float(new[(new.item_id == "R003")].sort_values("effective_from").price.iloc[-1]) == 947.0


def test_update_events_idempotent():
    once, _ = update_events(_events(), _pages(), dt.date(2026, 10, 2))
    twice, log2 = update_events(once, _pages(), dt.date(2026, 10, 3))
    assert len(once) == len(twice) and log2 == []


# ---- Labour Bureau --------------------------------------------------------------------------------------------
def test_lb_period_and_link():
    url = "/uploads/public/notice/MILCPI-IWAugust2026Epdf-abc.pdf"
    assert lb.letter_period(url) == "2026-08" and lb.prev_period("2026-01") == "2025-12"
    assert lb.find_letter_url(f'<a href="{url}">x</a>') == url


def test_lb_text_parse():
    assert lb.parse_letter_text("Rajkot 146.0 146.2", "2026-08") == {"2026-07": 146.0, "2026-08": 146.2}
    assert lb.parse_letter_text("nothing here", "2026-08") is None


def test_lb_real_pdf():
    pytest.importorskip("pdfplumber")
    got = lb.parse_letter_pdf((FX / "lb_cpiiw_aug26_letter.pdf").read_bytes(), "2026-08")
    assert got == {"2026-07": 146.0, "2026-08": 146.2}


# ---- source plan + official link ------------------------------------------------------------------------------
def test_source_plan_covers_basket_once_and_weights_sum():
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str)
    basket = pd.read_csv(ROOT / "data/basket.csv", dtype=str)
    assert plan.item_id.is_unique and set(plan.item_id) == set(basket.item_id)
    wts = pd.read_csv(ROOT / "data/weights_cpi2024_gujarat_urban.csv")
    wcol = [c for c in wts.columns if "weight" in c][0]
    m = plan.merge(wts, on="item_id")
    assert abs(m[wcol].sum() - 100) < 0.5
    assert 20 < m[m["class"] == "independent"][wcol].sum() < 70      # honest: still a minority (55.1% by plan after DMart Ahmedabad, of which the DMart share is pending validation)


def test_official_link_emits_index_series():
    c = OfficialLinkCollector(ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv",
                              ROOT / "data/basket_official_map.csv", ROOT / "data/source_plan.csv")
    obs = list(c.collect(dt.date(2026, 10, 2)))
    assert obs and all(o.base_unit == "pc" and o.qty_base == 1.0 and o.obs_date.day == 1 for o in obs)
    items = {o.item_id for o in obs}
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str)
    assert "F021" in items and "P005" in items          # back-filled before independent feeds begin
    assert "T001" not in items and "R003" not in items  # tariff items keep their own real series
    assert set(linked_items(plan)) >= items


def test_price_update_weights_rolls_forward(tmp_path):
    off = pd.DataFrame([dict(level="item", period="2025-01", code="A", index_value=200.0),
                        dict(level="item", period="2025-01", code="B", index_value=100.0)])
    off.to_csv(tmp_path / "o.csv", index=False)
    pd.DataFrame([dict(item_id="x", official_item_code="A"), dict(item_id="y", official_item_code="B"),
                  dict(item_id="z", official_item_code="")]).to_csv(tmp_path / "m.csv", index=False)
    w0 = pd.Series({"x": 10.0, "y": 10.0, "z": 10.0})
    w1, label = price_update_weights(w0, "APPROX", "2025-01", tmp_path / "o.csv", tmp_path / "m.csv")
    assert abs(w1.sum() - 30) < 1e-9 and w1["x"] > w1["y"] == w1["z"] and "price-updated" in label
    w2, label2 = price_update_weights(w0, "APPROX", "2030-01", tmp_path / "o.csv", tmp_path / "m.csv")
    assert (w2 == w0).all() and label2 == "APPROX"       # unknown base month -> untouched


# ---- coverage honesty -------------------------------------------------------------------------------------------
def test_coverage_split_on_real_db():
    db = ROOT / "data/rpi.sqlite"
    if not db.exists():
        pytest.skip("run `python -m rpi refresh` first")
    import sqlite3
    from rpi.quality import coverage_split
    cs = coverage_split(sqlite3.connect(db), ROOT / "data/source_plan.csv")
    assert abs(sum(cs["plan_weight_pct"].values()) - 100) < 0.5
    assert cs["independent_weight_pct_ref"] <= cs["observed_weight_pct_ref"] <= 100


# ---- second wave of datasets: PNG, eggs, electricity model, milk, registry, pruning -------------------------------
def test_parse_png_monthly():
    rows = dict(w.parse_gr_png_monthly(fx("gr_png.html")))
    assert rows["2026-09"] == 49.02 and len(rows) >= 8


def test_parse_eggs_and_glitch_screen():
    s = w.parse_eggratelab(fx("eggratelab_ahmedabad.html"))
    assert len(s) >= 25 and all(3 < p < 12 for _, p in s)
    cleaned = w.clean_outliers(s)
    assert len(cleaned) <= len(s) and max(p for _, p in cleaned) < 9


def test_electricity_model_matches_hand_calc():
    from rpi.electricity import build_events
    ev = build_events(ROOT / "data/electricity_base_tariff.csv", ROOT / "data/fppas_schedule.csv")
    p = dict(zip(ev.effective_from, ev.price))
    # 200 kWh: energy 50*3.05+50*3.50+100*4.15 = 742.5 ; fixed 25 ; FPPAS 2.30*200 = 460 ; duty 15%
    assert abs(p["2025-07-01"] - (742.5 + 25 + 460) * 1.15) < 0.01
    # Jul 2026: base 2.45 + 3.99% variable on the pre-duty bill
    assert abs(p["2026-07-01"] - (742.5 + 25 + 490) * 1.0399 * 1.15) < 0.01
    assert p["2025-07-01"] < p["2025-04-01"] < p["2026-07-01"]            # cut then hike, direction as reported


def test_electricity_update_is_idempotent_and_keeps_other_items(tmp_path):
    from rpi.electricity import update_events_file
    f = tmp_path / "ev.csv"
    pd.DataFrame([dict(item_id="T001", effective_from="2026-01-01", price=100.0, status="verified", source_class="p",
                       source_url="u", retrieved="2026-01-01", note="x")]).to_csv(f, index=False)
    args = (f, ROOT / "data/electricity_base_tariff.csv", ROOT / "data/fppas_schedule.csv")
    update_events_file(*args); a = pd.read_csv(f)
    update_events_file(*args); b = pd.read_csv(f)
    assert len(a) == len(b) and (a.item_id == "T001").sum() == 1 and (a.item_id == "R002").sum() == 4


def test_unverified_fppas_rows_are_ignored(tmp_path):
    from rpi.electricity import build_events
    sch = pd.read_csv(ROOT / "data/fppas_schedule.csv")
    sch.loc[len(sch)] = ["2026-09-01", 2.70, 0, "unverified", "https://billcalculator.in", "aggregator claim"]
    f = tmp_path / "s.csv"; sch.to_csv(f, index=False)
    ev = build_events(ROOT / "data/electricity_base_tariff.csv", f)
    assert "2026-09-01" not in set(ev.effective_from)                       # the Rs2.70 aggregator figure never enters


def test_milk_events_are_in_registry_with_provenance():
    ev = pd.read_csv(ROOT / "data/tariff_events.csv")
    m = ev[ev.item_id == "F009"].sort_values("effective_from")
    assert list(m.price) == [33.0, 34.0, 35.0] and m.source_url.notna().all()
    assert set(m.status) <= {"verified", "derived", "corroborated"}


def test_registry_staleness_alarm():
    from rpi.registry import review
    assert review(ROOT / "data/tariff_events.csv", dt.date(2026, 10, 2)) == []
    stale = review(ROOT / "data/tariff_events.csv", dt.date(2027, 9, 1))
    assert any(s.startswith("R002") for s in stale) and any(s.startswith("F009") for s in stale)


def test_prune_official_link_removes_items_with_independent_source(tmp_path):
    import sqlite3
    from rpi import db
    from rpi.refresh import prune_official_link
    conn = db.connect(tmp_path / "t.sqlite")
    for it in ("R002", "C001"):
        conn.execute("INSERT INTO products(sku_id,source_id,source_sku,item_id,title) VALUES(?,?,?,?,?)",
                     (f"official_link:{it}", "official_link", it, it, it))
        conn.execute("INSERT INTO observations(obs_date,sku_id,pincode,price) VALUES('2026-01-01',?, 'GJ',100)", (f"official_link:{it}",))
    conn.commit()
    msg = prune_official_link(conn, ROOT / "data/source_plan.csv")
    left = [r[0] for r in conn.execute("SELECT item_id FROM products")]
    assert left == ["C001"] and "1" in msg                                   # R002 is tariff-sourced now; C001 stays linked
    assert prune_official_link(conn, ROOT / "data/source_plan.csv") == "nothing to prune"


def test_plan_assigns_new_sources():
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str).set_index("item_id")
    assert plan.loc["R002", "primary_source"] == "tariff" and plan.loc["F009", "primary_source"] == "tariff"
    assert plan.loc["F020", "primary_source"] == "doca_national"  # NECC feed superseded 2026-10-02 (rpi/superseded.py)
    assert plan.loc["R005", "primary_source"] == "gr_png"
    assert plan.loc["T005", "class"] == "none"


# ---- acrop.app Rajkot mandi feeds, cutoff splice, proxy validation (added 2026-10-02) ----------------------------
class _FakeResp:
    def __init__(self, text): self.text, self.status_code = text, 200


class _FakeClient:
    def __init__(self, pages): self.pages, self.urls = pages, []
    def get(self, url):
        self.urls.append(url)
        return _FakeResp(self.pages[url.rstrip("/").split("/")[-1]])


def test_parse_acrop_rows_and_units():
    rows = w.parse_acrop_commodity(fx("acrop_wheat.html"))
    assert len(rows) >= 8 and rows[0][0] > rows[-1][0]
    d, lo, hi, modal = rows[0]
    assert lo <= modal <= hi and 1500 < modal < 6000            # wheat Rs/quintal
    bad = fx("acrop_wheat.html").replace("per quintal", "per kg")
    assert w.parse_acrop_commodity(bad) == []                   # unit guard: anything not 'per quintal' is refused
    swapped = fx("acrop_wheat.html").replace("₹2,720", "₹9,999", 1)
    assert len(w.parse_acrop_commodity(swapped)) == len(rows) - 1   # min>modal row dropped


def test_acrop_collector_converts_to_rs_per_kg_and_respects_date():
    cl = _FakeClient({s: fx("acrop_wheat.html") for s in ("wheat", "tur", "moong", "chana")})
    obs = list(w.AcropCollector(cl, None, "mandi_rajkot_apmc").collect(dt.date(2026, 9, 30)))
    assert {o.item_id for o in obs} == {"F001", "F003", "F004"}      # F005 chana retired from acrop (variety pooling)
    assert all(o.obs_date <= dt.date(2026, 9, 30) for o in obs)           # nothing from the future
    wheat = [o for o in obs if o.item_id == "F001" and o.obs_date == dt.date(2026, 9, 30)][0]
    assert abs(wheat.price - 28.36) < 1e-9 and wheat.qty_base == 1000.0 and wheat.base_unit == "g"
    assert all("/mandi/gujarat/rajkot/rajkot/" in u for u in cl.urls)
    veg = w.AcropCollector(_FakeClient({s: fx("acrop_veg_potato.html") for s in ("potato", "onion", "tomato", "brinjal")}), None, "mandi_rajkot_veg")
    assert {o.item_id for o in veg.collect(dt.date(2026, 10, 2))} == {"F021", "F022", "F023", "F025"}


def test_plan_wires_new_sources_everywhere():
    from rpi.collectors.official_link import BACKFILL_SOURCES
    from rpi.index.engine import SINGLE_SERIES_SOURCES
    from rpi.proxy_check import PROXY_SOURCES
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str).set_index("item_id")
    for it in ("F001", "F004"):
        assert plan.loc[it, "primary_source"] == "mandi_rajkot_apmc" and plan.loc[it, "class"] == "independent"
    assert plan.loc["F003", "primary_source"] == "doca_national" and plan.loc["F003", "class"] == "independent"  # superseded
    assert plan.loc["F005", "primary_source"] == "doca_national" and plan.loc["F005", "class"] == "independent"  # yard board superseded
    for src in ("mandi_rajkot_apmc", "mandi_rajkot_veg", "yard_rajkot_board"):
        assert src in BACKFILL_SOURCES and src in SINGLE_SERIES_SOURCES and src in PROXY_SOURCES
    assert set(w.ACROP_MARKETS) == {"mandi_rajkot_apmc", "mandi_rajkot_veg"}


def test_official_cutoff_never_double_counts_a_month(tmp_path):
    from rpi import db
    from rpi.collectors.official_link import independent_cutoffs, trim_official_overlap
    conn = db.connect(tmp_path / "t.sqlite")
    for sku, src in (("official_link:F001", "official_link"), ("mandi_rajkot_apmc:wheat", "mandi_rajkot_apmc")):
        conn.execute("INSERT INTO products(sku_id,source_id,source_sku,item_id,title) VALUES(?,?,?,?,?)", (sku, src, sku, "F001", sku))
    for d in ("2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01"):
        conn.execute("INSERT INTO observations(obs_date,sku_id,pincode,price) VALUES(?,?,?,?)", (d, "official_link:F001", "GJ", 100))
    for d in ("2026-09-15", "2026-10-01"):
        conn.execute("INSERT INTO observations(obs_date,sku_id,pincode,price) VALUES(?,?,?,?)", (d, "mandi_rajkot_apmc:wheat", "R", 28))
    conn.commit()
    assert independent_cutoffs(conn) == {"F001": "2026-09"}
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str, keep_default_na=False)
    assert "2" in trim_official_overlap(conn, plan)
    left = [r[0] for r in conn.execute("SELECT obs_date FROM observations WHERE sku_id='official_link:F001' ORDER BY 1")]
    assert left == ["2026-07-01", "2026-08-01"]
    assert trim_official_overlap(conn, plan) == "no official/independent overlap"       # idempotent


def test_official_link_collector_respects_cutoff():
    col = OfficialLinkCollector(ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv", ROOT / "data/basket_official_map.csv",
                                ROOT / "data/source_plan.csv", cutoff={"F001": "2026-03"})
    obs = [o for o in col.collect(dt.date(2026, 10, 2)) if o.item_id == "F001"]
    assert obs and max(o.obs_date for o in obs) < dt.date(2026, 3, 1)


def test_proxy_judge_pending_pass_fail():
    from rpi.proxy_check import judge
    idx = [f"2026-{m:02d}" for m in range(1, 9)]
    off = pd.Series([100, 101, 103, 102, 104, 107, 106, 108.0], index=idx)
    assert judge(off.iloc[:4] * 0.3, off.iloc[:4])["verdict"] == "pending"           # < 6 overlapping months
    good = judge(off * 0.3 * 1.01, off)                                              # same shape, different level
    assert good["verdict"] == "pass" and good["corr"] > 0.99
    anti = pd.Series([108, 106, 104, 105, 103, 100, 101, 99.0], index=idx)
    assert judge(anti, off)["verdict"] == "fail"                                      # moves the wrong way


def test_coverage_split_reports_direct_vs_proxy():
    import sqlite3
    cs = coverage_split(sqlite3.connect(ROOT / "data/rpi.sqlite"), ROOT / "data/source_plan.csv")
    sp = cs["independent_split_pct"]
    assert abs(sum(sp.values()) - cs["plan_weight_pct"]["independent"]) < 0.2


def test_min_days_by_source_drops_partial_month_for_volatile_feeds(tmp_path):
    from rpi import db
    from rpi.index.panel import load_quotes
    conn = db.connect(tmp_path / "t.sqlite")
    for sku, src in (("m:a", "mandi_rajkot_apmc"), ("t:b", "tariff")):
        conn.execute("INSERT INTO products(sku_id,source_id,source_sku,item_id,title) VALUES(?,?,?,?,?)", (sku, src, sku, "X", sku))
    for d in range(1, 8):
        conn.execute("INSERT INTO observations(obs_date,sku_id,pincode,price,unit_price,in_stock) VALUES(?,?,?,?,?,1)", (f"2026-09-{d:02d}", "m:a", "R", 10, 10))
    conn.execute("INSERT INTO observations(obs_date,sku_id,pincode,price,unit_price,in_stock) VALUES('2026-10-01','m:a','R',11,11,1)")
    conn.execute("INSERT INTO observations(obs_date,sku_id,pincode,price,unit_price,in_stock) VALUES('2026-10-01','t:b','R',5,5,1)")
    conn.commit()
    q = load_quotes(conn, "unit_price", 1, {"mandi_rajkot_apmc": 5})
    got = {(r.source_id, str(r.period)) for r in q.itertuples()}
    assert ("mandi_rajkot_apmc", "2026-09") in got and ("mandi_rajkot_apmc", "2026-10") not in got   # 1-day month refused
    assert ("tariff", "2026-10") in got                                                               # administered: 1 quote is legitimate


# ---------------------------------------------------------------- second-sweep administered registers (R004 / K001 / S002)
def test_tariff_series_column_gives_parallel_skus_and_blank_stays_single():
    from rpi.collectors.tariff_events import expand_events
    ev = pd.DataFrame([
        dict(item_id="K001", series="a", effective_from="2026-01-01", price=100.0),
        dict(item_id="K001", series="b", effective_from="2026-01-01", price=200.0),
        dict(item_id="K001", series="b", effective_from="2026-02-01", price=300.0),
        dict(item_id="R004", series="", effective_from="2026-01-01", price=50.0)])
    obs = expand_events(ev, dt.date(2026, 2, 28))
    skus = {o.source_sku for o in obs}
    assert skus == {"K001:a", "K001:b", "R004"} and {o.item_id for o in obs} == {"K001", "R004"}
    assert [o.price for o in obs if o.source_sku == "K001:b"] == [200.0, 300.0]
    # an events file with no `series` column at all still works (back-compat)
    assert {o.source_sku for o in expand_events(ev.drop(columns="series"), dt.date(2026, 1, 31))} == {"K001", "R004"}


def test_admin_registers_present_with_provenance_and_in_plan():
    ev = pd.read_csv(ROOT / "data/tariff_events.csv")
    for item, n_series in (("R004", 1), ("K001", 2), ("S002", 2)):
        g = ev[ev.item_id == item]
        assert g.series.fillna("").nunique() == n_series and g.source_url.notna().all()
        assert set(g.status) <= {"verified", "corroborated", "derived"}
    a = ev[(ev.item_id == "K001") & (ev.series == "airtel_entry_unlimited")].sort_values("effective_from")
    assert list(a.price) == [299.0, 349.0] and a.effective_from.iloc[-1] == "2026-08-12"
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str).set_index("item_id")
    assert all(plan.loc[i, "primary_source"] == "tariff" and plan.loc[i, "class"] == "independent" for i in ("R004", "K001", "S002"))


def test_registry_alarms_cover_new_registers():
    from rpi.registry import review
    assert review(ROOT / "data/tariff_events.csv", dt.date(2026, 10, 2)) == []
    stale = review(ROOT / "data/tariff_events.csv", dt.date(2027, 6, 1))
    assert any(s.startswith("K001") for s in stale) and any(s.startswith("S002") for s in stale)


# ---------------------------------------------------------------- APMC cross-check + yard-board chana series
def test_yard_board_parser_and_band_judge():
    from rpi.crosscheck import parse_yard_board, judge_band
    day, board = parse_yard_board((ROOT / "tests/fixtures/agrobhai_rajkot_apmc.html").read_text())
    assert day == dt.date(2026, 10, 1) and board["ઘઉં લોકવન"] == (544.0, 575.0) and board["ચણા પીળા"] == (1180.0, 1421.0)
    assert judge_band(28.08, 544, 575) == "agree"          # acrop wheat modal Rs2,808/q = Rs28.08/kg
    assert judge_band(86.49, 1180, 1421) == "DISAGREE"     # acrop's pooled 'chana' modal: outside the yellow-chana band


def test_yard_board_collector_emits_chana_yellow_midpoint():
    from rpi.collectors.web_sources import YardBoardCollector
    class C:
        def get(self, url):
            class R: status_code = 200; text = (ROOT / "tests/fixtures/agrobhai_rajkot_apmc.html").read_text()
            return R()
    obs = list(YardBoardCollector(C(), None).collect(dt.date(2026, 10, 2)))
    assert len(obs) == 1 and obs[0].item_id == "F005" and obs[0].obs_date == dt.date(2026, 10, 1)
    assert abs(obs[0].price - (1180 + 1421) / 2 / 20) < 1e-9 and obs[0].base_unit == "g"
    assert list(YardBoardCollector(C(), None).collect(dt.date(2026, 9, 30))) == []      # never from the future


def test_acrop_chana_is_retired_and_plan_points_to_board():
    from rpi.collectors.web_sources import ACROP_MARKETS
    from rpi.refresh import RETIRED_SERIES
    assert "F005" not in ACROP_MARKETS["mandi_rajkot_apmc"][2] and ("mandi_rajkot_apmc", "F005") in RETIRED_SERIES
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str).set_index("item_id")
    assert plan.loc["F005", "primary_source"] == "doca_national"  # yard board superseded (rpi/superseded.py)
    import tomllib
    cfg = tomllib.loads((ROOT / "config/settings.toml").read_text())
    assert cfg["index"]["min_days_by_source"]["yard_rajkot_board"] >= 5


def test_reset_tariff_series_clears_only_tariff_rows(tmp_path):
    from rpi import db
    from rpi.refresh import reset_tariff_series
    conn = db.connect(tmp_path / "t.sqlite")
    for src in ("tariff", "official_link"):
        conn.execute("INSERT INTO products(sku_id,source_id,source_sku,item_id,title) VALUES(?,?,?,?,?)", (f"{src}:x", src, "x", "R004", "x"))
        conn.execute("INSERT INTO observations(obs_date,sku_id,pincode,price) VALUES('2023-04-01',?, 'GJ',1)", (f"{src}:x",))
    conn.commit()
    assert "cleared 1" in reset_tariff_series(conn)
    assert [r[0] for r in conn.execute("SELECT sku_id FROM observations")] == ["official_link:x"]


# ---------------------------------------------------------------- multi-yard staples (Gondal, Jetpur, Jasdan)
def test_district_collector_emits_one_series_per_yard_and_survives_one_bad_page():
    class C:
        def __init__(self): self.urls = []
        def get(self, url):
            self.urls.append(url)
            class R: pass
            r = R()
            if "/jasdan/tur" in url:
                r.status_code, r.text = 500, ""
            else:
                r.status_code, r.text = 200, fx("acrop_wheat.html")
            return r
    cl = C()
    obs = list(w.AcropCollector(cl, None, "mandi_rajkot_district").collect(dt.date(2026, 9, 30)))
    skus = {(o.item_id, o.source_sku) for o in obs}
    assert ("F001", "wheat|Gondal APMC") in skus and ("F001", "wheat|Jetpur APMC") in skus and ("F001", "wheat|Jasdan APMC") in skus
    assert not any(i == "F003" and "Jasdan" in k for i, k in skus)           # the failed page is skipped, the rest survive
    assert any(i == "F005" and "Gondal" in k for i, k in skus) and not any(i == "F005" and "Jasdan" in k for i, k in skus)
    assert {o.pincode for o in obs} == {"MANDI:Gondal APMC", "MANDI:Jetpur APMC", "MANDI:Jasdan APMC"}
    assert all("/mandi/gujarat/rajkot/" in u for u in cl.urls)


def test_gondal_board_crosscheck_bands():
    from rpi.crosscheck import parse_yard_board, GONDAL_CROPS
    day, board = parse_yard_board((ROOT / "tests/fixtures/agrobhai_gondal_apmc.html").read_text())
    assert day == dt.date(2026, 10, 1) and all(c in board for c in GONDAL_CROPS.values())
    assert board["ચણા"] == (1111.0, 1416.0)


def test_district_source_wired_everywhere():
    from rpi.index.engine import SINGLE_SERIES_SOURCES
    from rpi.proxy_check import PROXY_SOURCES
    import tomllib
    cfg = tomllib.loads((ROOT / "config/settings.toml").read_text())
    assert "mandi_rajkot_district" in PROXY_SOURCES and "mandi_rajkot_district" in SINGLE_SERIES_SOURCES
    assert cfg["index"]["min_days_by_source"]["mandi_rajkot_district"] >= 5


def test_crosscheck_uses_latest_acrop_row_within_lookback(tmp_path):
    from rpi import db
    from rpi.crosscheck import crosscheck_gondal
    conn = db.connect(tmp_path / "t.sqlite")
    conn.execute("INSERT INTO products(sku_id,source_id,source_sku,item_id,title) VALUES('d:w','mandi_rajkot_district','w','F001','w')")
    for d, p in (("2026-09-29", 29.5), ("2026-09-30", 29.67)):                       # board date is 1 Oct; acrop lags by a day
        conn.execute("INSERT INTO observations(obs_date,sku_id,pincode,price) VALUES(?,'d:w','MANDI:Gondal APMC',?)", (d, p))
    conn.commit()
    html = (ROOT / "tests/fixtures/agrobhai_gondal_apmc.html").read_text()
    r = {x["item_id"]: x for x in crosscheck_gondal(conn, html)}
    assert r["F001"]["verdict"] == "agree" and r["F001"]["acrop_date"] == "2026-09-30"
    conn.execute("DELETE FROM observations WHERE obs_date='2026-09-30'"); conn.execute("UPDATE observations SET obs_date='2026-09-25'"); conn.commit()
    assert {x["item_id"]: x for x in crosscheck_gondal(conn, html)}["F001"]["verdict"] == "no_acrop_row_for_date"   # too old: not compared


def test_ibja_history_parse_and_crosscheck(tmp_path):
    from rpi import db
    from rpi.crosscheck import crosscheck_ibja, parse_ibja_history
    html = (ROOT / "tests/fixtures/ibjarates_home.html").read_text()
    h = parse_ibja_history(html)
    assert sorted(h) == ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"]
    d = h["2026-10-01"]                                    # AM 136197, PM 135694 per 10 g (916); silver 221954 / 220829 per kg
    assert (d["am916"], d["pm916"]) == (136197.0, 135694.0)
    assert abs(d["gold916_per_g"] - 13594.55) < 0.01 and abs(d["silver999_per_g"] - 221.3915) < 1e-6
    conn = db.connect(tmp_path / "t.sqlite")
    for sku, item in (("g:p5", "P005"), ("g:p6", "P006")):
        conn.execute("INSERT INTO products(sku_id,source_id,source_sku,item_id,title) VALUES(?,'gr_metals',?,?,?)", (sku, item, item, item))
    rows = {"P005": {"2026-09-28": 13770, "2026-09-29": 13645, "2026-09-30": 13715, "2026-10-01": 13685, "2026-10-02": 13780},
            "P006": {"2026-09-28": 240, "2026-09-29": 240, "2026-09-30": 240, "2026-10-01": 235}}
    for item, series in rows.items():
        for day, price in series.items():
            conn.execute("INSERT INTO observations(obs_date,sku_id,pincode,price) VALUES(?,?,'360001',?)", (day, "g:p5" if item == "P005" else "g:p6", price))
    conn.commit()
    r = {x["item_id"]: x for x in crosscheck_ibja(conn, html)}
    assert r["P005"]["verdict"] == "agree" and r["P005"]["n_days"] == 4          # 2 Oct has no IBJA row yet -> not compared
    assert 0.0 < r["P005"]["premium_min"] <= r["P005"]["premium_max"] < 0.03      # retail quote sits slightly above the benchmark
    assert r["P006"]["verdict"] == "agree"
    conn.execute("UPDATE observations SET price=price*1.08 WHERE sku_id='g:p5'"); conn.commit()          # a feed 8% off the benchmark must be caught
    assert {x["item_id"]: x for x in crosscheck_ibja(conn, html)}["P005"]["verdict"] == "DISAGREE"
    assert parse_ibja_history("<html></html>") == {}


# ---- sixth sweep: PNG tariff overlay (goodreturns lags the 3 Sep 2026 Gujarat Gas hike) ----------------------------
def test_png_overlay_applies_while_goodreturns_is_stale():
    import datetime as dt
    base = dict(w.parse_gr_png_monthly(fx("gr_png.html")))
    ev = [dict(date=dt.date(2026, 9, 3), price=53.22, prev=49.02)]
    out = w.apply_png_events(base, ev, dt.date(2026, 10, 2))
    assert out["2026-08"] == 49.02                                 # before the event: untouched
    assert abs(out["2026-09"] - (49.02 * 2 + 53.22 * 28) / 30) < 1e-3   # event month: day-weighted
    assert out["2026-10"] == 53.22                                 # current month beyond the table: new tariff
    # the verified register in the repo is consistent with the arithmetic that reconciles the press reports
    assert abs(46.69 * 1.05 - 49.02) < 0.01 and abs(53.22 - 49.02 - 4.20) < 1e-9
    assert w.load_png_events(ROOT / "data/png_events.csv")[0]["price"] == 53.22


def test_png_overlay_defers_to_goodreturns_once_it_catches_up():
    import datetime as dt
    base = dict(w.parse_gr_png_monthly(fx("gr_png.html")))
    base["2026-09"], base["2026-10"] = 53.22, 53.22                # goodreturns updated
    ev = [dict(date=dt.date(2026, 9, 3), price=53.22, prev=49.02)]
    out = w.apply_png_events(base, ev, dt.date(2026, 10, 2))
    assert out["2026-09"] == 53.22 and out["2026-10"] == 53.22 and out["2026-08"] == 49.02
    # a goodreturns value that is neither old nor new (a later, unrecorded revision) is never overridden
    base["2026-10"] = 55.0
    assert w.apply_png_events(base, ev, dt.date(2026, 10, 2))["2026-10"] == 55.0


def test_registry_review_covers_png_register(tmp_path):
    import datetime as dt
    from rpi.registry import review
    warns = review(ROOT / "data/tariff_events.csv", today=dt.date(2026, 10, 2), extra={"R005": ROOT / "data/png_events.csv"})
    assert not any(x.startswith("R005") for x in warns)
    late = review(ROOT / "data/tariff_events.csv", today=dt.date(2028, 1, 1), extra={"R005": ROOT / "data/png_events.csv"})
    assert any(x.startswith("R005") for x in late)
