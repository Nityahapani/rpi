"""Generate data/tariff_events.csv for Rajkot from the evidence gathered on 2026-10-02.

Every row carries status + provenance. Status vocabulary (see rpi/collectors/tariff_events.py):
  verified      dated event from a primary/news-of-record source AND magnitude agrees with another source
  corroborated  level/timing confirmed by the OFFICIAL MoSPI Gujarat-urban item index (carry-back etc.)
  derived       estimated from verified anchors (documented in `note`); used but flagged
  unverified    seen, but not confirmed -> NEVER used by the index
  rejected      contradicted by better evidence -> NEVER used
"""
import csv, datetime as dt
from pathlib import Path

R = "2026-10-02"
IT_P = "https://www.indiatoday.in/fuel-price/petrol-price-in-rajkot-today"
IT_D = "https://www.indiatoday.in/fuel-price/diesel-price-in-rajkot-today"
HIKES = "https://www.telegraphindia.com/business/petrol-price-raised-by-87-paise-diesel-by-91-paise-third-fuel-hike-in-10-days/cid/2161954"
HINDU25 = "https://www.thehindu.com/business/Economy/petrol-diesel-prices-hiked-for-fourth-time-in-10-days-may-25-2026/article71019671.ece"
rows = []
def add(item, date, price, status, cls, url, note): rows.append([item, date, f"{price:.2f}", status, cls, url, R, note])

# ---- fuel: Delhi dated national steps (PTI/The Hindu/ET); Rajkot anchors from India Today (+ Goodreturns title agrees)
def fuel(item, base, end_may, steps, monthly, url):
    scale = (end_may - base) / sum(steps)
    add(item, "2026-01-01", base, "corroborated", "secondary+official", url,
        "Level 1-Apr-2026 per aggregator; official Gujarat-urban item index flat Jan-Apr 2026 so carried back to Jan")
    cum, dates = base, ["2026-05-15", "2026-05-19", "2026-05-23", "2026-05-25"]
    for d, s in zip(dates, steps):
        cum += s * scale
        last = d == dates[-1]
        add(item, d, end_may if last else cum, "verified" if last else "derived", "news+secondary", url + " | " + HIKES,
            f"Dated national OMC hike (Delhi step {s}); Rajkot step = Delhi step x {scale:.4f} so the path ends at the "
            f"observed 31-May Rajkot price {end_may}" + ("" if last else " (intermediate level estimated)"))
    for d, v in monthly:
        add(item, d, v, "derived", "secondary", url, "Monthly mean estimated as (first-of-month + last-of-month price)/2 from aggregator history; daily prices wobble +-0.3-0.9")

fuel("T001", 94.67, 101.57, [3.00, 0.87, 0.87, 2.61],
     [("2026-06-01", 101.91), ("2026-07-01", 102.29), ("2026-08-01", 101.91), ("2026-09-01", 101.71), ("2026-10-01", 101.87)], IT_P)
fuel("T002", 90.40, 97.71, [3.00, 0.91, 0.91, 2.71],
     [("2026-06-01", 98.05), ("2026-07-01", 98.42), ("2026-08-01", 98.03), ("2026-09-01", 97.85), ("2026-10-01", 98.00)], IT_D)

# ---- LPG 14.2 kg: Rajkot = Delhi + 5 at every verified step (853->913->942 Delhi; 858->918->947 Rajkot)
LPG25 = "https://www.bankbazaar.com/gas-connection/lpg-price-today.html"
LPG26 = "https://www.newsx.com/india/lpg-price-hike-2026-households-to-pay-29-more-for-142kg-domestic-gas-cylinder-231229/"
add("R003", "2025-01-01", 808, "corroborated", "secondary", "https://www.goodreturns.in/lpg-price-in-rajkot.html",
    "Pre-hike price; consistent with Delhi 803 + 5. Official LPG+PNG index flat Jan-Mar 2025")
add("R003", "2025-04-08", 858, "corroborated", "secondary+official", "https://www.goodreturns.in/lpg-price-in-rajkot.html",
    "National +Rs50 hike (recalled; not re-fetched this session); official LPG+PNG item +2.21% in Apr 2025")
add("R003", "2026-03-07", 918, "verified", "news+official", LPG25, "National +Rs60 on 7-Mar-2026 (Delhi 853->913); Rajkot 858->918; official item +3.53% in Mar 2026")
add("R003", "2026-06-07", 947, "verified", "news+official", LPG26, "National +Rs29 on 7-Jun-2026 (Delhi 913->942); Rajkot 918->947; official item +1.73% in Jun 2026")

# ---- seen but NOT usable
add("T001", "2026-10-01", 115.01, "rejected", "secondary", "https://www.mypetrolprice.com/", "mypetrolprice claim; official petrol index (+7.7% since Apr) and two other sources imply ~102")
add("T002", "2026-10-01", 100.10, "unverified", "secondary", "https://www.mypetrolprice.com/", "single aggregator; India Today/Goodreturns and official index imply ~97.7-98.3")

hdr = ["item_id", "effective_from", "price", "status", "source_class", "source_url", "retrieved", "note"]
out = Path(__file__).resolve().parents[1] / "data" / "tariff_events.csv"
with open(out, "w", newline="") as f:
    w = csv.writer(f); w.writerow(hdr); w.writerows(sorted(rows, key=lambda r: (r[0], r[1])))
print(len(rows), "events ->", out)
