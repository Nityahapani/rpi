import pandas as pd
from pathlib import Path
from rpi.collectors import practo_fees as P
ROOT = Path(__file__).resolve().parents[1]

CARD = ('<div data-qa-id="doctor_card"><a href="/rajkot/doctor/dr-x-general-physician?practice_id=77&amp;specialization=GP"><h2 data-qa-id="doctor_name">Dr. X</h2></a>'
        '<span data-qa-id="practice_locality">Yagnik Road</span><span data-qa-id="doctor_clinic_name">X Clinic</span>'
        '<span data-qa-id="consultation_fee" class="">₹<!-- -->1,200</span></div>')
NOFEE = '<div data-qa-id="doctor_card"><a href="/rajkot/doctor/dr-y-general-physician?practice_id=78"><h2 data-qa-id="doctor_name">Dr. Y</h2></a></div>'


def test_parse_listing_reads_fee_and_skips_cards_without_one():
    r = P.parse_listing("<html>" + CARD + NOFEE + "</html>")
    assert r == [dict(key="dr-x-general-physician:77", name="Dr. X", clinic="X Clinic", locality="Yagnik Road", fee=1200.0)]


def test_scan_stops_at_a_repeated_page():
    class C:
        n = 0
        def get(self, url):
            self.n += 1
            class R: status_code = 200; text = CARD
            return R()
    c = C()
    d = P.scan(c, specialities=("general-physician",), max_pages=15)
    assert len(d) == 1 and c.n == 2


def test_pool_diary_collector_and_plan_wiring():
    from rpi.collectors.official_link import BACKFILL_SOURCES
    from rpi.index.engine import SINGLE_SERIES_SOURCES
    from rpi.proxy_check import PROXY_SOURCES, MULTI_SKU_SOURCES
    pool = pd.read_csv(ROOT / "data/practo/pool.csv")
    assert len(pool) >= 150 and pool.key.is_unique and not pool.speciality.str.contains("dentist").any()
    obs = list(P.PractoCollector(ROOT).collect(None))
    assert len(obs) >= 150 and all(o.item_id == "M003" and o.price > 0 and o.source_id == "practo_rajkot" for o in obs)
    for tup in (BACKFILL_SOURCES, SINGLE_SERIES_SOURCES, PROXY_SOURCES, MULTI_SKU_SOURCES):
        assert "practo_rajkot" in tup
    plan = pd.read_csv(ROOT / "data/source_plan.csv").set_index("item_id")
    assert plan.loc["M003", "primary_source"] == "practo_rajkot"
