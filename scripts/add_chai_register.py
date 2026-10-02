"""D002 - Rajkot cutting chai (half cup), Rs, the Rajkot District Tea Hotel Association rate card.

New level: from 1 Sep 2026 half cup Rs15 / full cup Rs30.  Reported identically by Divya Bhaskar (1 Sep 2026, association decision), CNBC TV18
(3 Sep), News18 / News18 Gujarati (23 Aug, 1-2 Sep), ABP Asmita (23 Aug), Gujarat Samachar (25 Aug); about 2,500-3,000 stalls.
Prior level is DISPUTED between outlets: half cup 13 (Divya Bhaskar: 13 -> 15, full 26 -> 30; the association's own rate since 11 Mar 2022, Amreli City
12 Mar 2022: half 12 -> 13, full 24 -> 25), 10 (News18, CNBC TV18, ABP: 10 -> 15, full 20 -> 30), 10-12 (ABP).
DECISION (user: "do the chai"): wire the CONSERVATIVE end, the association's own prior rate Rs13 -> Rs15 = +15.4% (full cup 26 -> 30 gives the same
+15.4%).  The +50% reading (10 -> 15) is not used.  So the series is a lower bound on the step, never an overstatement.
Assumed flat at 13 from Jan 2025 to Aug 2026 (the association's rate card did not change between Mar 2022 and Sep 2026 on the Divya Bhaskar baseline);
individual stalls charged more (a News18 Gujarati story of 21 May 2026 quotes one stall at Rs18) - a rate card is not an observed average paid price,
so D002 is counted in the PROXY share (like the NPPA ceiling and the auto fare).  The official 'Tea: cups' Gujarat-urban move Aug -> Sep 2026 (due mid-Oct)
is checked against it in data/official/event_checks.csv; if the official response is muted the item is downgraded.
"""
import datetime as dt
import pandas as pd

P = "data/tariff_events.csv"
U = "https://www.divyabhaskar.co.in/local/gujarat/rajkot/news/rajkot-tea-price-hike-hotel-association-update-138896403.html"
U22 = "https://www.amrelicity.com/expensive-news-for-tea-lovers-in-rajkot/"
ROWS = [
    ("D002", "", "2025-01-01", 13.0, "derived",
     "press: association rate card (Divya Bhaskar 1 Sep 2026 'from Rs13'; Mar 2022 step 12 -> 13 per Amreli City 12 Mar 2022)", U22,
     "Half cup Rs13 = association rate since 11 Mar 2022 (dated at base month). Prior level disputed by other outlets (10 / 12); conservative end used. Rate card, not an observed paid price."),
    ("D002", "", "2026-09-01", 15.0, "verified",
     "Rajkot District Tea Hotel Association decision, Divya Bhaskar 1 Sep 2026; CNBC TV18, News18, News18 Gujarati, ABP Asmita, Gujarat Samachar (23 Aug - 3 Sep 2026)", U,
     "Half cup Rs15 (full cup Rs30) from 1 Sep 2026; about 2,500-3,000 stalls. Rate card, not an observed paid price."),
]
ev = pd.read_csv(P)
have = set(zip(ev.item_id, ev.series.fillna(""), ev.effective_from.astype(str)))
new = [dict(item_id=i, series=s, effective_from=d, price=p, status=st, source_class=c, source_url=u,
            retrieved=dt.date.today().isoformat(), note=n) for i, s, d, p, st, c, u, n in ROWS if (i, s, d) not in have]
if new:
    pd.concat([ev, pd.DataFrame(new)], ignore_index=True).to_csv(P, index=False)
print(f"chai register: +{len(new)} event(s)")
