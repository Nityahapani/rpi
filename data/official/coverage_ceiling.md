# Coverage ceiling (generated 2026-10-08; blocker notes from the 2026-10-02 probe)

Independent weight: **89.2%** (55 of 67 items). Remaining non-independent weight: **10.8%** (12 items).

The 40% milestone this file was written around (2026-10-02, independent share then 38.5%) has been passed; the live question is now what still blocks the remainder. Item lists and weights below are read live from data/source_plan.csv.

| Blocker | Items (still blocked) | Weight % | What the probe found |
|---|---|---|---|
| Brand MRP, history incomplete (not safe to register) | 2 (T006, K002) | 0.8 | Packaged goods: only isolated documented steps exist (e.g. Amul butter 62->58, ghee 650->610 on 22 Sep 2025, GST cut). Official butter/ghee indices rose ~3.5% after Oct 2025, so a flat register would be wrong. ToS blocks e-commerce scraping. |
| No machine-readable source: fares/fees/services | 8 (M003, M004, T003, S003, E002, E004, D001, D003) | 9.9 | Bus/auto fares (latest press is 2022), school/tuition fees, doctor/hospital, haircut, cinema, street food, newspaper, RMC water (increase only proposed). |
| No revision found / unverifiable | 1 (K003) | 0.1 | Telecom/broadband/OTT: last verified hike Jul 2024; no later revision found, which is not proof of none. |
| Genuinely no data | 1 (T005) | 0.0 | No official item and no independent source. |

Sum of blocked weight: 10.8% (= 100 - 89.2).

Wired since the probe (no longer blockers): 38 items, 40.6% of weight - F001, F002, F003, F004, F005, F006, F007, F008, F010, F011, F012, F013, F014, F015, F016, F017, F018, F019, F026, C001, C002, C003, R004, H001, H002, H003, H004, M001, M002, K001, S001, S002, E001, E003, P001, P002, P003, P004.

Rent (R001, 19.0%): Rent. No public Rajkot rent series: the Magicbricks Rental Index is listing-based, national/metro only (+14% y/y Q1 2026), not CPI-style rent, so a survey or licensed data is needed. NOTE: R001 is no longer blocked - it was wired on 2026-10-06 as an independent MODELLED series (Labour Bureau CPI-IW housing, trend-gated, 19.0% of weight).

## What is left to unlock (largest remaining blocks first)
| Unlock | + points | Independent % after |
|---|---|---|
| Own survey / licensed feed for: No machine-readable source: fares/fees/services | +9.9 | 99.1 |
| Own survey / licensed feed for: Brand MRP, history incomplete (not safe to register) | +0.8 | 99.9 |
| Own survey / licensed feed for: No revision found / unverifiable | +0.1 | 100.0 |
| Own survey / licensed feed for: Genuinely no data | +0.0 | 100.0 |

Reading: no *automatable, permitted, real* feed remains for any large block; the weight still on official stand-ins sits in No machine-readable source: fares/fees/services (9.9%), Brand MRP, history incomplete (not safe to register) (0.8%), No revision found / unverifiable (0.1%). Reaching 100% is possible only through data we collect ourselves (own surveys, licences or RTI), because every remaining block is blocked by a mechanism (captcha, bot challenge, ToS, or no publication at all) rather than by effort.
