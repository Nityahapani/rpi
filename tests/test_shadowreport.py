"""Tests for the shadowreport module (shadow-vs-actual report). Synthetic repos in tmp_path; one smoke run on the real data."""
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from shadowreport import compare, feeds as F
from shadowreport.cli import main
from shadowreport.report import build, render_markdown, write
from rpi.rentsignal import CODE

ROOT = Path(__file__).resolve().parent.parent
AS_OF = dt.date(2026, 10, 13)


def _csv(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n")


def _synthetic_repo(root: Path, *, onemg_date="2026-10-12", onemg_unit=0.950667, tariff=0.9765) -> Path:
    _csv(root / "data/tariff_events.csv", f"""
item_id,series,effective_from,price,status,source_class,source_url,retrieved,note
M001,,2025-09-22,0.966,verified,x,x,x,x
M001,,2026-04-01,{tariff},verified,x,x,x,x
""")
    _csv(root / "data/onemg_prices.csv", f"""
date,item_id,product_id,pack_units,pack_price,unit_price,url
{onemg_date},M001,878516,15,14.26,{onemg_unit},https://www.1mg.com/x
""")
    _csv(root / "data/hathway_broadband_prices.csv", """
date,plan_name,speed,item_id,price,currency,url
2026-10-10,Beginners Plan,75 Mbps,K003,500.0,INR,https://www.hathway.com/x
""")
    _csv(root / "data/apple_store_prices.csv", """
date,part_number,item_id,price,currency,url
2026-10-10,MYE73HN/A,K002,89900.0,INR,https://www.apple.com/x
""")
    _csv(root / "data/green_mercado_prices.csv", "date,product_id,item_id,title,pack,price,mrp,currency,url")
    _csv(root / "data/rajkot_shops_prices.csv", """
date,store,item_id,variant_id,pack,price,regular_price,qty_base,base_unit,unit_price
2026-10-09,green_force,F002,1,1 Kg,111.0,111.0,1000.0,g,111.0
""")
    _csv(root / "data/rent_listings.csv", """
first_seen,listed,bhk,sqft,rent,title,source_url,portal,key,last_seen,ptype,locality,expires,n_seen
2026-10-01,2026-10-01,2,900,15000,t,u,magicbricks,k1,2026-10-01,flat,a,,1
""")
    (root / "data/official").mkdir(parents=True, exist_ok=True)
    rows = ["period,level,code,index_value"] + [f"{p},item,{CODE},{100 + i * 0.3:.2f}" for i, p in enumerate(
        [f"2025-{m:02d}" for m in range(1, 13)] + [f"2026-{m:02d}" for m in range(1, 10)])]
    (root / "data/official/mospi_cpi2024_gujarat_urban.csv").write_text("\n".join(rows) + "\n")
    (root / "data/official/shadow_sources.json").write_text(json.dumps({"candidates": {"rajkot_shops": {"items": [
        {"item_id": "F001", "name": "Atta", "gate_vs_official": {"verdict": "pending", "n_overlap": 0}, "status": "accruing"}]}}}))
    return root


# ------------------------------------------------------------------ registry

def test_registry_has_unique_ids_valid_kinds_and_six_feeds():
    ids = [f.id for f in F.FEEDS]
    assert len(ids) == len(set(ids)) == 6
    assert {f.kind for f in F.FEEDS} <= {"price", "gate", "rent"}


def test_green_mercado_is_inactive_not_an_alarm():
    gm = next(f for f in F.FEEDS if f.id == "green_mercado")
    assert gm.active is False


# ------------------------------------------------------------------ reference lookup and gaps

def test_tariff_lookup_uses_latest_effective_date_on_or_before_the_quote(tmp_path):
    root = _synthetic_repo(tmp_path)
    assert F.tariff_price_at(root, "M001", "2026-10-12") == (0.9765, "2026-04-01")
    assert F.tariff_price_at(root, "M001", "2026-01-01") == (0.966, "2025-09-22")
    assert F.tariff_price_at(root, "M001", "2025-01-01") == (None, None)
    assert F.tariff_price_at(root, "K999", "2026-10-12") == (None, None)


def test_price_gap_is_the_percent_difference_to_the_reference(tmp_path):
    root = _synthetic_repo(tmp_path)
    feed = next(f for f in F.FEEDS if f.id == "onemg_calpol")
    rows = F.price_rows(root, feed, AS_OF)
    assert len(rows) == 1 and rows[0]["reference"] == 0.9765
    assert rows[0]["gap_pct"] == pytest.approx(-2.65, abs=0.01)


def test_price_rows_skip_unparseable_prices(tmp_path):
    root = _synthetic_repo(tmp_path)
    _csv(root / "data/onemg_prices.csv", """
date,item_id,product_id,pack_units,pack_price,unit_price,url
2026-10-12,M001,1,15,14.26,,x
2026-10-11,M001,1,15,14.26,0.95,x
""")
    feed = next(f for f in F.FEEDS if f.id == "onemg_calpol")
    assert [r["date"] for r in F.price_rows(root, feed, AS_OF)] == ["2026-10-11"]


# ------------------------------------------------------------------ statuses

def _feed(**kw):
    base = dict(id="x", label="x", kind="price", path="p", item="M001", reference="r", freshness_days=14)
    base.update(kw)
    return F.Feed(**base)


def test_inactive_feed_reports_inactive_whatever_its_quotes():
    assert compare.feed_status(_feed(active=False), {"n_quotes": 0}) == "inactive"


def test_no_quotes_stale_out_of_band_tracking_pending():
    f = _feed()
    assert compare.feed_status(f, {"n_quotes": 0}) == "no_quotes"
    assert compare.feed_status(f, {"n_quotes": 2, "days_since_last": 30, "n_with_reference": 2, "latest_gap_pct": 0}) == "stale"
    assert compare.feed_status(f, {"n_quotes": 2, "days_since_last": 1, "n_with_reference": 2, "latest_gap_pct": 15}) == "out_of_band"
    assert compare.feed_status(f, {"n_quotes": 2, "days_since_last": 1, "n_with_reference": 2, "latest_gap_pct": 2}) == "tracking"
    assert compare.feed_status(_feed(reference=None), {"n_quotes": 2, "days_since_last": 1, "n_with_reference": 0}) == "pending"


def test_a_judged_fail_beats_stale_and_out_of_band():
    f = _feed(kind="rent")
    assert compare.feed_status(f, {"n_quotes": 3, "days_since_last": 99, "judged_verdict": "fail"}) == "fail"


def test_overall_is_the_worst_active_status_and_ignores_inactive():
    assert compare.overall(["tracking", "stale", "inactive"]) == "stale"
    assert compare.overall(["pending", "inactive"]) == "pending"
    assert compare.overall(["inactive", "inactive"]) == "inactive"
    assert compare.overall(["pass", "tracking"]) == "tracking"


# ------------------------------------------------------------------ rent comparison

def test_rent_comparison_below_minimum_overlap_is_reported_not_judged():
    s = pd.Series([100.0, 101.0, 102.0], index=["2026-07", "2026-08", "2026-09"])
    o = pd.Series([100.0, 100.5, 101.0], index=["2026-07", "2026-08", "2026-09"])
    c = compare.rent_comparison(s, o)
    assert c["n_overlap_months"] == 3 and c["judged"] is False and c["verdict"] == "pending"
    assert c["gap_cum_pp"] is not None


def test_rent_comparison_is_judged_with_the_trend_gate_on_enough_overlap():
    idx = [f"2025-{m:02d}" for m in range(1, 13)] + [f"2026-{m:02d}" for m in range(1, 9)]
    trend = np.linspace(100, 110, len(idx))
    s = pd.Series(trend, index=idx)
    o = pd.Series(trend * 1.0, index=idx)          # same trend: the gap is zero
    c = compare.rent_comparison(s, o)
    assert c["judged"] is True and c["verdict"] == "pass"


def test_missing_official_series_is_pending_not_a_crash(tmp_path):
    root = _synthetic_repo(tmp_path)
    (root / "data/official/mospi_cpi2024_gujarat_urban.csv").unlink()
    rep = build(root, AS_OF)
    rent = next(f for f in rep["feeds"] if f["id"] == "rent_listings")
    assert rent["status"] == "pending" and "official_error" in rep["detail"]


def test_rent_comparison_with_no_overlap_is_pending():
    c = compare.rent_comparison(pd.Series([1.0], index=["2026-01"]), pd.Series([1.0], index=["2025-01"]))
    assert c["n_overlap_months"] == 0 and c["verdict"] == "pending"


# ------------------------------------------------------------------ full build on a synthetic repo

def test_build_covers_all_feeds_and_marks_green_mercado_inactive(tmp_path):
    root = _synthetic_repo(tmp_path)
    rep = build(root, AS_OF)
    assert [f["id"] for f in rep["feeds"]] == [f.id for f in F.FEEDS]
    st = {f["id"]: f["status"] for f in rep["feeds"]}
    assert st["green_mercado"] == "inactive"
    assert st["onemg_calpol"] == "tracking"
    assert st["hathway_k003"] == "pending"
    assert st["rajkot_shops"] == "pending"
    assert rep["overall"] in set(F.SEVERITY) - {"pass"} | {"pending"}


def test_stale_feed_turns_the_overall_status_stale(tmp_path):
    root = _synthetic_repo(tmp_path)
    rep = build(root, dt.date(2026, 12, 1))
    st = {f["id"]: f["status"] for f in rep["feeds"]}
    assert st["onemg_calpol"] == "stale" and rep["overall"] == "stale"


def test_write_produces_json_and_markdown(tmp_path):
    root = _synthetic_repo(tmp_path / "repo")
    rep = build(root, AS_OF)
    jp, mp = write(rep, tmp_path / "out")
    assert json.loads(jp.read_text())["as_of"] == "2026-10-13"
    text = mp.read_text()
    assert "Overall:" in text and "1mg Calpol" in text and "Green Mercado" in text


def test_render_markdown_has_one_row_per_feed(tmp_path):
    rep = build(_synthetic_repo(tmp_path), AS_OF)
    md = render_markdown(rep)
    assert md.count("| **") == len(F.FEEDS)


# ------------------------------------------------------------------ CLI

def test_cli_report_and_check_exit_codes(tmp_path, capsys):
    root = _synthetic_repo(tmp_path / "repo")
    out = tmp_path / "out"
    assert main(["report", "--root", str(root), "--as-of", "2026-10-13", "--out", str(out)]) == 0
    assert (out / "shadow_report.json").exists()
    assert main(["check", "--root", str(root), "--as-of", "2026-10-13", "--out", str(out)]) == 0
    assert main(["check", "--root", str(root), "--as-of", "2026-12-01", "--out", str(out)]) == 1


def test_cli_feeds_lists_every_feed(capsys):
    assert main(["feeds"]) == 0
    printed = capsys.readouterr().out
    for f in F.FEEDS:
        assert f.id in printed


# ------------------------------------------------------------------ real data (smoke)

def test_real_repo_builds_a_report_with_all_feeds():
    rep = build(ROOT, AS_OF)
    assert len(rep["feeds"]) == len(F.FEEDS)
    assert rep["overall"] in set(F.SEVERITY) | {"inactive", "pending"}
    calpol = next(f for f in rep["feeds"] if f["id"] == "onemg_calpol")
    assert calpol["n_quotes"] >= 1
