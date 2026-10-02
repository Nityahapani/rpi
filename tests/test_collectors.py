import datetime as dt
import pandas as pd
from rpi.collectors.agmarknet import parse_records
from rpi.collectors.tariff_events import expand_events
from rpi.collectors.base import robots_allows, PoliteClient

CMAP = pd.DataFrame({"commodity": ["Potato", "Onion"], "variety_regex": [".*", ".*"], "item_id": ["F021", "F022"]})

def test_agmarknet_parse_fixture():
    recs = [  # shape documented for the data.gov.in Agmarknet resource
        {"State": "Gujarat", "District": "Rajkot", "Market": "Rajkot", "Commodity": "Potato", "Variety": "Potato",
         "Grade": "FAQ", "Arrival_Date": "02/10/2026", "Min_Price": "1500", "Max_Price": "2100", "Modal_Price": "1800"},
        {"state": "Gujarat", "district": "Surat", "market": "Surat", "commodity": "Potato", "variety": "x",
         "arrival_date": "02/10/2026", "modal_price": "9999"},                 # other market: filtered
        {"state": "Gujarat", "district": "Rajkot", "market": "Gondal", "commodity": "Onion", "variety": "Red",
         "arrival_date": "02/10/2026", "modal_price": "NA"},                    # bad price: skipped
        {"state": "Gujarat", "district": "Rajkot", "market": "Gondal", "commodity": "Wheat", "variety": "x",
         "arrival_date": "02/10/2026", "modal_price": "2500"},                  # unmapped commodity
    ]
    obs = list(parse_records(recs, CMAP, ["Rajkot", "Gondal"]))
    assert len(obs) == 1
    o = obs[0]
    assert o.item_id == "F021" and abs(o.price - 18.0) < 1e-9 and o.obs_date == dt.date(2026, 10, 2)

def test_tariff_time_weighting():
    ev = pd.DataFrame({"item_id": ["R003", "R003"], "effective_from": ["2026-01-01", "2026-02-16"],
                       "price": [800.0, 900.0]})
    obs = {o.obs_date: o.price for o in expand_events(ev, dt.date(2026, 3, 31))}
    assert abs(obs[dt.date(2026, 1, 1)] - 800.0) < 1e-9
    assert abs(obs[dt.date(2026, 2, 1)] - (15 * 800 + 13 * 900) / 28) < 1e-9
    assert abs(obs[dt.date(2026, 3, 1)] - 900.0) < 1e-9

def test_robots():
    txt = "User-agent: *\nDisallow: /private/\n"
    assert robots_allows(txt, "RPI", "https://x.com/public/a")
    assert not robots_allows(txt, "RPI", "https://x.com/private/a")

def test_polite_client_rate_limits():
    sleeps, t = [], [0.0]
    class R:
        status_code, content, text = 200, b"{}", ""
    class S:
        headers = {}
        def get(self, *a, **k): return R()
    c = PoliteClient("RPI", min_delay=2.0, respect_robots=False, session=S(),
                     sleep=lambda x: (sleeps.append(x), t.__setitem__(0, t[0] + x)), clock=lambda: t[0])
    c.get("https://a.com/1"); c.get("https://a.com/2")
    assert sleeps and abs(sleeps[0] - 2.0) < 1e-9
