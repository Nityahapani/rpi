"""Listings panel (two portals) and the listings-based R001 candidate: parsing, panel keys/revisions, polite crawl, hedonic index,
stock conversion.  All offline (fake client, synthetic pages)."""
import datetime as dt
import json

import numpy as np
import pandas as pd

from rpi import rentlistings as RL
from rpi.collectors import rent_listings as rl
from rpi.config import ROOT


def _ra(name, price, start, landlord="Owner A"):
    return {"@context": "https://schema.org", "@type": "RentAction", "startTime": start, "endTime": "2026-12-31T00:00:00.000Z",
            "landlord": {"@type": "Person", "name": landlord}, "object": {"@type": "Residence", "name": name},
            "priceSpecification": {"@type": "PriceSpecification", "price": price, "priceCurrency": "INR"}}


def _page(records, links=()):
    body = "".join(f'<script type="application/ld+json">{json.dumps(r)}</script>' for r in records)
    return body + "".join(f'<a href="{u}">x</a>' for u in links)


def _sq(name, price, lid, desc="This 900 Square Feet semi-furnished flat", street="Mavdi"):
    return {"@type": "RentAction", "object": {"@type": "residence", "name": name}, "price": str(price), "startTime": "2026-10-01T00:00:00.000",
            "url": f"https://www.squareyards.com/rental-2-bhk-flat-in-mavdi/{lid}", "description": desc,
            "location": {"@type": "Place", "address": {"streetAddress": street}}}


def test_magicbricks_parse_drops_commercial_and_reads_type_and_locality():
    rows = rl.parse_listings(_page([
        _ra("3 BHK Flat  for Rent in Gokul Mathura, 150 Feet Ring Road, Rajkot 1500 Sqft", 31500, "2026-10-05T23:45:28.000Z"),
        _ra("Residential House for Rent in Mavdi, Rajkot 900 Sqft", 12000, "2026-10-04T10:00:00.000Z"),
        _ra("Commercial Office Space for Rent in Kalawad Road, Rajkot 500 Sqft", 20000, "2026-10-04T10:00:00.000Z"),
        _ra("Warehouse/ Godown for Rent in Metoda, Rajkot", 50000, "2026-10-04T10:00:00.000Z")]))
    assert [r["ptype"] for r in rows] == ["flat", "house"]
    assert rows[0]["locality"] == "150 feet ring road" and rows[0]["bhk"] == 3 and rows[0]["sqft"] == 1500 and rows[0]["listed"] == "2026-10-05"
    assert all("landlord" not in r and "Owner" not in json.dumps(r) for r in rows)              # names are never kept


def test_squareyards_parse_keys_on_the_portal_id_and_reads_area_from_the_description():
    rows = rl.parse_squareyards(_page([_sq("2 BHK Flat for Rent in Mavdi, Rajkot", 15000, 12345678),
                                       _sq("Shop for Rent in Yagnik Road, Rajkot", 16000, 10713688, "This 150 Square Feet furnished shop")]))
    assert len(rows) == 1 and rows[0]["key"] == "sq:12345678" and rows[0]["sqft"] == 900 and rows[0]["locality"] == "mavdi"


def test_panel_tracks_last_seen_and_revisions_and_counts_page_overlap_once(tmp_path):
    p = tmp_path / "r.csv"
    a = _ra("2 BHK Flat  for Rent in Raiya Road, Rajkot 675 Sqft", 17500, "2026-09-28T00:00:00.000Z")
    rows = rl.parse_listings(_page([a, a]))
    assert rl.update_panel(p, rows, "u", dt.date(2026, 10, 2)) == (2, 1)                    # duplicate within one call counted once
    assert rl.update_panel(p, rl.parse_listings(_page([a])), "u", dt.date(2026, 10, 5)) == (1, 0)
    df = pd.read_csv(p)
    assert len(df) == 1 and df.last_seen.iloc[0] == "2026-10-05" and int(df.n_seen.iloc[0]) == 2
    cut = dict(a, priceSpecification={"@type": "PriceSpecification", "price": 16500, "priceCurrency": "INR"})
    assert rl.update_panel(p, rl.parse_listings(_page([cut])), "u", dt.date(2026, 10, 9)) == (1, 1)   # an asking-rent cut is a revision
    df = pd.read_csv(p)
    assert len(df) == 2 and df.key.nunique() == 1 and df.rent.tolist() == [17500, 16500]


def test_rows_from_the_original_diagnostic_get_the_same_key_as_new_rows(tmp_path):
    p = tmp_path / "r.csv"
    pd.DataFrame([dict(first_seen="2026-10-02", listed="2026-09-28", bhk=2, sqft=675.0, rent=17500.0,
                       title="2 BHK Flat for Rent in Raiya Road, Rajkot 675 Sqft", source_url="u")]).to_csv(p, index=False)
    a = _ra("2 BHK Flat  for Rent in Raiya Road, Rajkot 675 Sqft", 17500, "2026-09-28T00:00:00.000Z")
    assert rl.update_panel(p, rl.parse_listings(_page([a])), "u", dt.date(2026, 10, 9)) == (1, 0)
    df = pd.read_csv(p)
    assert len(df) == 1 and df.portal.iloc[0] == "magicbricks" and df.last_seen.iloc[0] == "2026-10-09"


def test_discovery_keeps_residential_list_urls_and_the_plan_is_least_recently_fetched_first():
    html = _page([], links=["https://www.magicbricks.com/flats-for-rent-in-mavdi-rajkot-pppfr",
                            "https://www.magicbricks.com/office-space-for-rent-in-rajkot-pppfr",
                            "https://www.magicbricks.com/villa-for-rent-in-rajkot-pppfr"])
    assert rl.discover(html, "magicbricks") == {"https://www.magicbricks.com/flats-for-rent-in-mavdi-rajkot-pppfr",
                                                "https://www.magicbricks.com/villa-for-rent-in-rajkot-pppfr"}
    urls = pd.DataFrame([dict(portal="magicbricks", url="a", discovered_on="seed", last_fetched="2026-10-08", last_n="30"),
                         dict(portal="magicbricks", url="b", discovered_on="seed", last_fetched="", last_n=""),
                         dict(portal="squareyards", url="c", discovered_on="seed", last_fetched="2026-10-01", last_n="9")])
    assert [u for _, u in rl.plan(urls, 2)] == ["b", "c"]


class _Resp:
    def __init__(self, status, text):
        self.status_code, self.text = status, text


class _Client:
    def __init__(self, block_after=None):
        self.calls, self.block_after = [], block_after

    def get(self, url, params=None):
        self.calls.append(url)
        if self.block_after is not None and len(self.calls) > self.block_after:
            return _Resp(403, "")
        if url.endswith("/page-2"):
            return _Resp(404, "")
        if "squareyards" in url:
            return _Resp(200, _page([_sq("2 BHK Flat for Rent in Mavdi, Rajkot", 15000, 99999999)]))
        full = [_ra(f"2 BHK Flat  for Rent in Raiya Road, Rajkot {700 + i} Sqft", 15000 + 10 * i, "2026-10-01T00:00:00.000Z") for i in range(30)]
        return _Resp(200, _page(full, links=["https://www.magicbricks.com/flats-for-rent-in-mavdi-rajkot-pppfr"]))


def test_crawl_asks_for_page_two_only_behind_a_full_page_and_stops_on_a_block(tmp_path):
    (tmp_path / "data").mkdir()
    c = _Client()
    st = rl.accrue(c, tmp_path, dt.date(2026, 10, 10), budget=2)
    assert st["urls_fetched"] == 2 and st["blocked"] is None and st["new"] == 30 and st["discovered"] == 1
    assert c.calls[1].endswith("/page-2")                                                  # page 1 was full (30 listings)
    urls = pd.read_csv(tmp_path / rl.URLS_CSV, dtype=str, keep_default_na=False)
    assert (urls.last_fetched == "2026-10-10").sum() == 2
    c2 = _Client(block_after=1)
    st = rl.accrue(c2, tmp_path, dt.date(2026, 10, 11), budget=5)
    assert st["blocked"] and "HTTP 403" in st["blocked"] and st["urls_fetched"] == 1       # the block came on page 2 of the first URL
    assert len(c2.calls) == 2                                                              # ... and nothing was requested after it


def _synthetic(effects, n=150, seed=3, lag=1):
    rng = np.random.default_rng(seed)
    rows = []
    for m, e in effects.items():
        for _ in range(n):
            bhk = int(rng.choice([1, 2, 3, 4], p=[0.2, 0.4, 0.3, 0.1]))
            sq = float(rng.normal(450 + 300 * bhk, 80))
            loc = str(rng.choice(["raiya road", "mavdi", "kalawad road", "other"]))
            y = 9.4 + e + 0.4 * np.log(sq / 900) + {1: -0.4, 2: 0.0, 3: 0.3, 4: 0.6}[bhk] + {"raiya road": 0.1, "mavdi": -0.1, "kalawad road": 0.2, "other": 0.0}[loc]
            rows.append(dict(month=m, lag_days=lag, lrent=y + rng.normal(0, 0.08), bhk_c=bhk, lsqft_c=np.log(sq / 900), sqft_missing=0.0,
                             furnished_page=0.0, ptype="flat", loc_c=loc, portal="magicbricks"))
    return pd.DataFrame(rows)


def test_hedonic_index_recovers_known_month_effects_and_sets_the_flags():
    eff = {"2026-07": 0.0, "2026-08": 0.02, "2026-09": 0.05, "2026-10": 0.03}
    df = _synthetic(eff)
    df.loc[df.month == "2026-07", "lag_days"] = 60                                        # July captured late: a survivor month
    idx = RL.hedonic_index(df, n_boot=30, today=dt.date(2026, 10, 20)).set_index("month")
    for m, e in eff.items():
        assert abs(np.log(idx.at[m, "index"] / 100) - e) < 0.03, m
    assert idx.at["2026-08", "lo90"] < idx.at["2026-08", "index"] < idx.at["2026-08", "hi90"]
    assert bool(idx.at["2026-07", "survivor"]) and not bool(idx.at["2026-08", "survivor"])
    assert not bool(idx.at["2026-10", "complete"]) and bool(idx.at["2026-09", "usable"]) and not bool(idx.at["2026-10", "usable"])


def test_stock_candidate_is_the_model_without_listings_and_the_12_month_listing_average_with_them():
    months = pd.period_range("2025-01", "2026-12", freq="M").strftime("%Y-%m")
    modelled = pd.Series(100 * np.exp(0.002 * np.arange(len(months))), index=months)
    s0 = RL.stock_candidate(pd.Series(dtype=float), modelled, set())
    assert np.allclose(s0.set_index("month").level.reindex(months), modelled) and (s0.listing_share == 0).all()
    lm = months[5:]                                                                        # listings from 2025-06, all usable, +1% a month
    new = pd.Series(100 * np.exp(0.01 * np.arange(len(lm))), index=lm)
    s = RL.stock_candidate(new, modelled, set(lm)).set_index("month")
    assert abs(s.at["2025-07", "listing_share"] - 1 / 12) < 1e-12                        # first usable change: 2025-06 -> 2025-07
    assert abs(s.at["2026-06", "dlog"] - 0.01) < 1e-12 and s.at["2026-06", "listing_share"] == 1.0   # full window: new-lease growth
    assert abs(s.at["2025-12", "dlog"] - (0.002 + 6 * 0.008 / 12)) < 1e-12               # half a window: halfway between model and listings


def test_stock_candidate_extends_beyond_the_model_only_with_a_full_listing_window():
    mm = pd.period_range("2025-01", "2026-06", freq="M").strftime("%Y-%m")
    modelled = pd.Series(100 * np.exp(0.002 * np.arange(len(mm))), index=mm)
    lm = pd.period_range("2025-03", "2026-09", freq="M").strftime("%Y-%m")
    s = RL.stock_candidate(pd.Series(100 * np.exp(0.01 * np.arange(len(lm))), index=lm), modelled, set(lm)).set_index("month")
    assert s.index[-1] == "2026-09" and bool(s.at["2026-09", "from_listings_only"])
    lm2 = pd.period_range("2026-01", "2026-09", freq="M").strftime("%Y-%m")               # only 8 changes by 2026-09: no extension
    s2 = RL.stock_candidate(pd.Series(100 * np.exp(0.01 * np.arange(len(lm2))), index=lm2), modelled, set(lm2))
    assert s2.month.iloc[-1] == "2026-06"


def test_screen_on_the_real_panel_reports_a_verdict_and_never_departs_from_the_model_without_usable_months():
    from rpi.collectors.rent_signal import level_series
    r = RL.screen(ROOT, write=False, n_boot=20)
    assert r["verdict"] and r["gate_vs_official"]["gate"] == "trend" and r["n_listings_used"] > 100
    sc = pd.DataFrame(r["stock_candidate"]).set_index("month").level
    if r["listing_share_latest"] == 0:
        m = level_series(ROOT)
        common = sc.index.intersection(m.index)
        assert len(common) >= 14 and np.allclose(sc[common], m[common])
