"""M001 - Paracetamol 500 mg tablet: NPPA ceiling price including GST, Rs per tablet (Tier C regulated-ceiling proxy).

The National Pharmaceutical Pricing Authority fixes a ceiling for scheduled formulations under DPCO 2013 and revises it every
1 April by the annual WPI change. Paracetamol 500 mg tablet is a scheduled formulation. Ceilings are EXCLUSIVE of GST.

  ceiling (ex-GST)   w.e.f. 1.4.2025  Rs0.92  S.O. 1489(E) 27.03.2025, WPI +1.74028%  (Kerala drugs-control copy of the NPPA list, 30.01.2026)
                     w.e.f. 1.4.2026  Rs0.93  S.O. 1575(E) 25.03.2026, WPI +0.64956%  (NPPA list as on 27.05.2026; Green Cross; pcdpharmagujarat)
                     before 1.4.2025  Rs0.90  DERIVED: 0.90 x 1.0174028 = 0.9157 -> 0.92; the neighbours 0.89 / 0.91 would round to 0.91 / 0.93.
  GST on drugs       12% until 21 Sep 2025, 5% from 22 Sep 2025 (56th GST Council; NPPA OM of 12 Sep 2025 orders every MRP revised from 22 Sep:
                     Business Standard 12 Sep, India TV 14 Sep, EY 4 Sep 2025).
  retail cap         = ceiling x (1 + GST).

CAVEATS (printed in sources.csv): a ceiling is a CAP, brands may sell below it, so this is a proxy, not an observed shelf price.
It is therefore counted in the PROXY share of independent weight, not the direct share. Dated 2025-01-01 at the base month; the
true effective date of the 0.90 ceiling was 1.4.2024.
"""
import datetime as dt
import pandas as pd

P = "data/tariff_events.csv"
U1 = "https://dc.kerala.gov.in/wp-content/uploads/2026/02/NPPA_UPDATED_PRICE-LIST_AS_ON_30012026.pdf"
U2 = "https://dc.kerala.gov.in/wp-content/uploads/2026/06/NPPA-UPDATED-PRICE-LIST-AS-ON-27-05-2026.pdf"
U3 = "https://www.business-standard.com/industry/news/nppa-asks-pharma-medtech-cos-to-reduce-cost-pass-on-benefits-to-consumers-125091201606_1.html"
ROWS = [
    ("M001", "", "2025-01-01", round(0.90 * 1.12, 4), "derived", "NPPA ceiling (derived from the 1.4.2025 list and WPI 1.74028%) x GST 12%", U1,
     "Ceiling Rs0.90 ex-GST (derived) x 1.12. True effective date 1.4.2024; dated at the index base month. Cap, not observed price."),
    ("M001", "", "2025-04-01", round(0.92 * 1.12, 4), "verified", "NPPA S.O. 1489(E) 27.03.2025 (Kerala drugs control copy of the list)", U1,
     "Ceiling Rs0.92 ex-GST (WPI +1.74028%) x GST 12%."),
    ("M001", "", "2025-09-22", round(0.92 * 1.05, 4), "verified", "NPPA OM (Business Standard 12 Sep 2025; India TV; EY) + GST Council 56th meeting", U3,
     "GST on drugs 12% -> 5%; NPPA ordered all MRPs revised from 22 Sep 2025 (old stock need not be re-stickered, so shelf prices may lag for weeks)."),
    ("M001", "", "2026-04-01", round(0.93 * 1.05, 4), "verified", "NPPA S.O. 1575(E) 25.03.2026 (NPPA list as on 27.05.2026)", U2,
     "Ceiling Rs0.93 ex-GST (WPI +0.64956%) x GST 5%."),
]
ev = pd.read_csv(P)
if "series" not in ev.columns:
    ev.insert(1, "series", "")
ev["series"] = ev["series"].fillna("")
have = set(zip(ev.item_id, ev.series, ev.effective_from.astype(str)))
new = [dict(item_id=i, series=s, effective_from=d, price=p, status=st, source_class=c, source_url=u,
            retrieved=dt.date.today().isoformat(), note=n) for i, s, d, p, st, c, u, n in ROWS if (i, s, d) not in have]
if new:
    pd.concat([ev, pd.DataFrame(new)], ignore_index=True).to_csv(P, index=False)
print(f"nppa register: +{len(new)} event(s)")
