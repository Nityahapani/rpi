"""Administered / list-price registers added in the 2026-10-02 second sweep (Tier C, idempotent).

R004  RMC residential water charge, Rs per year (flat Rs1,500 since FY2023-24).
      Indian Express 9 Feb 2023: standing committee set residential water at Rs1,500 (from Rs840).
      TOI 4 Feb 2026: FY26-27 draft proposed Rs1,500 -> Rs2,400 (confirms Rs1,500 was in force).
      DeshGujarat 11 Feb 2026: standing committee approved the revised budget 'scrapping the Rs95-crore tax hike'
      (TOI ties the Rs95 cr to garbage + water). The General Board's final vote was NOT separately confirmed -> 'corroborated'.
K001  Prepaid mobile, two operator series (Jevons mean):
      jio_299_1p5gb          Jio Rs299, 28 d, 1.5 GB/day (fixed spec). Rs299 since the 3 Jul 2024 revision (Bajaj Finserv, Gadgets360);
                             still listed 21 Aug 2026 (dailydigihelp, NDTV Profit 18 Aug 2026, Financial Express 21 Aug 2026).
      airtel_entry_unlimited Airtel cheapest unlimited daily-data 28-d plan (a PRICE-POINT series, not a fixed spec):
                             Rs299 until 11 Aug 2026; Rs349 from 12 Aug 2026 (India Today, Moneycontrol, Trak, Financial Express).
                             Caveat: Rs349 carries more data (2 GB/day) - no quality adjustment is applied.
S002  OTT list prices for NEW subscribers (existing auto-renewals keep old price):
      jiohotstar_super_annual  Rs899 -> Rs1,099 from 28 Jan 2026 (Variety, Business Standard, Techloy). Rs899 before = derived
                               (Disney+ Hotstar Super annual carried into JioHotstar).
      prime_annual             Amazon Prime India Rs1,499/yr: unchanged Apr 2023 (Inc42) ... 17/31 Aug 2026 (amazon.in via Zoutons).
Rows dated like 'confirmed on' are re-confirmations of an unchanged price: they reset the staleness alarm (rpi/registry.py).
Note: no event is dated before the index base month 2025-01 (an earlier date would extend the panel with months in which only these
registers exist). True earlier effective dates are in each row's note.
"""
import datetime as dt
import pandas as pd

P = "data/tariff_events.csv"
IE = "https://indianexpress.com/article/cities/rajkot/rajkot-civic-body-standing-committee-78-hike-water-charges-13-increase-property-tax-8434484/"
TOI = "https://timesofindia.indiatimes.com/city/rajkot/rmc-proposes-hike-in-charges-to-mop-up-rs-95cr/articleshow/127917174.cms"
DG = "https://deshgujarat.com/2026/02/11/rajkot-civic-body-presents-%E2%82%B93604-90-crore-budget-with-interest-waiver-scheme/"
IT = "https://www.indiatoday.in/business/story/airtel-removes-rs-299-rs-579-rs-619-rs-649-plans-heres-what-customers-pay-now-2969538-2026-08-12"
FE = "https://www.financialexpress.com/business/industry-airtel-axes-rs-299-plan-jio-revives-rs-300-prime-plan-is-a-telecom-tariff-hike-coming-4322319/"
BF = "https://www.bajajfinserv.in/jio-recharge-plans"
G360 = "https://www.gadgets360.com/telecom/features/airtel-vs-reliance-jio-new-prepaid-plans-compared-2024-5988533"
KS = "https://www.greaterkashmir.com/business/jio-remains-cheapest-option-continues-to-offer-more-data-than-other-telecos/"
VAR = "https://variety.com/2026/tv/news/indian-streaming-giant-jiohotstar-raises-prices-monthly-plans-1236634622/"
BS = "https://www.business-standard.com/companies/news/jiohotstar-premium-plan-price-hike-january-2026-subscription-details-126011900746_1.html"
INC = "https://inc42.com/buzz/amazon-prime-to-cost-more-than-netflix-in-india-now/"
ZO = "https://zoutons.com/news/amazon-prime-membership-price-india-2026"

# item, series, effective_from, price, status, source_class, source_url, note
ROWS = [
    ("R004", "", "2025-01-01", 1500.0, "corroborated", "press (Indian Express; TOI)", IE, "Residential water Rs/yr: 1,500 since the Feb 2023 RMC standing-committee decision (from 840; FY23-24). Dated at the index base month so the panel does not start earlier than the other series"),
    ("R004", "", "2026-04-01", 1500.0, "corroborated", "press (TOI + DeshGujarat)", DG, "Re-confirmation: FY26-27 draft hike to 2,400 (TOI 4 Feb 2026) scrapped by standing committee (DeshGujarat 11 Feb 2026); General Board vote not separately confirmed"),
    ("K001", "jio_299_1p5gb", "2025-01-01", 299.0, "verified", "press + operator listing (2+ outlets)", BF, "Jio 28-day 1.5GB/day plan Rs299 since the 3 Jul 2024 revision (Rs239 before); dated at the index base month"),
    ("K001", "jio_299_1p5gb", "2026-08-21", 299.0, "verified", "press (NDTV Profit, FE, dailydigihelp)", FE, "Re-confirmation: Jio still lists Rs299 (Aug 2026)"),
    ("K001", "airtel_entry_unlimited", "2025-01-01", 299.0, "corroborated", "press (Gadgets360; Greater Kashmir Aug 2025)", G360, "Airtel entry 28-day daily-data plan Rs299 since the July 2024 revision; dated at the index base month"),
    ("K001", "airtel_entry_unlimited", "2026-08-12", 349.0, "verified", "press (India Today, Moneycontrol, Trak, FE)", IT, "Airtel withdrew Rs299 on 12 Aug 2026; cheapest unlimited daily plan now Rs349 (2GB/day; no quality adjustment)"),
    ("S002", "jiohotstar_super_annual", "2025-01-01", 899.0, "derived", "press (Variety: 'from 899')", VAR, "Super annual Rs899 before the Jan 2026 hike; Disney+ Hotstar Super annual carried into JioHotstar (pre-2025 price inferred)"),
    ("S002", "jiohotstar_super_annual", "2026-01-28", 1099.0, "verified", "press (Variety, Business Standard, Techloy)", VAR, "JioHotstar Super annual Rs899 -> Rs1,099 for new subscribers from 28 Jan 2026"),
    ("S002", "prime_annual", "2025-01-01", 1499.0, "corroborated", "press (Inc42 2023; Rooter Dec 2025)", INC, "Prime annual Rs1,499 unchanged since the Apr 2023 monthly/quarterly revision"),
    ("S002", "prime_annual", "2026-08-31", 1499.0, "verified", "amazon.in listing quoted by Zoutons", ZO, "Re-confirmation: amazon.in/amazonprime listed Rs1,499/yr on 17 and 31 Aug 2026"),
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
elif "series" not in pd.read_csv(P).columns:
    ev.to_csv(P, index=False)
print(f"admin registers: +{len(new)} event(s)")
