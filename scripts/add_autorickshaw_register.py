"""T004 - Auto-rickshaw fare for a FIXED 3 km in-city trip, Rs (statutory tariff, Gujarat Ports & Transport Dept).

Tariff (urban, daytime), a Motor Vehicles Act s.67 fare notification:
  2022 notification (Jun 2022; PTI/Goodreturns 8 Jun 2022): minimum Rs20 for the first 1.2 km, then Rs15/km = Rs3 per 200 m.
        Kept in force until it was cancelled on 7 Aug 2026 (the 2026 notification says it replaces the 2022 one; ABP Asmita,
        GSTV, News18 Gujarati, Gujarat Samachar all say 'about three years without a hike').
  2026 notification effective 7 Aug 2026 (Gujarat Samachar 7 Aug, ABP Asmita 8 Aug, GSTV 8 Aug, News18 Gujarati 8 Aug; the Gandhinagar
        meeting of 22 Jun 2026 had agreed the numbers): minimum Rs25 for the first 1.2 km, then Rs4 per 200 m = Rs20/km.
Fixed trip: 3 km = minimum (1.2 km) + (3-1.2)/0.2 = 9 slabs.   old: 20 + 9x3 = 47    new: 25 + 9x4 = 61   (+29.8%)
Sensitivity: 2 km +28.1%, 5 km +31.2%, 1.2 km +25% -> the choice of trip length moves the step by only +-3 pp.
Night surcharge (+50%, 23:00-05:00), waiting charge and out-of-city 1.5x are NOT modelled (day tariff only).

CAVEATS (also in sources.csv): a notified fare is a legal MAXIMUM, not an observed paid fare; many Rajkot autos are unmetered and
bargain.  It is therefore counted in the PROXY share (like the NPPA ceiling), not the direct share.  The pre-step quote is dated
2025-01-01 (the base month) with its true date in the note; the 2022 level was constant through the whole panel.
"""
import datetime as dt
import pandas as pd

P = "data/tariff_events.csv"
U_NEW = "https://www.gujaratsamachar.com/news/baroda/state-government-announces-new-rates-for-autorickshaw-fares-47273163234"


def fare(first, per200, km=3.0):
    return first + round((km - 1.2) / 0.2) * per200


OLD, NEW = fare(20, 3), fare(25, 4)
assert (OLD, NEW) == (47, 61)
ROWS = [
    ("T004", "", "2025-01-01", float(OLD), "verified",
     "statutory tariff (2022 notification via PTI/Goodreturns 8 Jun 2022; confirmed in force until 7 Aug 2026 by the 2026 notification coverage)",
     U_NEW, "3 km trip = Rs20 min (1.2 km) + 9 slabs x Rs3 (Rs15/km). True start Jun 2022; dated at the base month. Legal maximum, not an observed paid fare."),
    ("T004", "", "2026-08-07", float(NEW), "verified",
     "Gujarat Ports & Transport Dept notification (MV Act s.67) quoted by Gujarat Samachar 7 Aug 2026, ABP Asmita 8 Aug, GSTV 8 Aug, News18 Gujarati 8 Aug 2026",
     U_NEW, "3 km trip = Rs25 min (1.2 km) + 9 slabs x Rs4 (Rs20/km); cancels the 2022 notification. Day tariff only. Legal maximum, not an observed paid fare."),
]
ev = pd.read_csv(P)
have = set(zip(ev.item_id, ev.series.fillna(""), ev.effective_from.astype(str)))
new = [dict(item_id=i, series=s, effective_from=d, price=p, status=st, source_class=c, source_url=u,
            retrieved=dt.date.today().isoformat(), note=n) for i, s, d, p, st, c, u, n in ROWS if (i, s, d) not in have]
if new:
    pd.concat([ev, pd.DataFrame(new)], ignore_index=True).to_csv(P, index=False)
print(f"autorickshaw register: +{len(new)} event(s)")
