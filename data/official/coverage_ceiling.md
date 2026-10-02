# Coverage ceiling (2026-10-02)

Independent weight today: **38.5%**. Target 40% needs **+1.5 points**.

| Blocker | Items | Weight % | What I found |
|---|---|---|---|
| No reachable source: rent | 1 (R001) | 19.7 | Rent. No public Rajkot rent series. Magicbricks Rental Index is listing-based, national/metro only (+14% y/y Q1 2026), not CPI-style rent. Needs own survey or licensed data. |
| Captcha-gated (DoCA retail price monitor) | 2 (F014, F015) | 3.3 | fcainfoweb.nic.in tracks exactly these staples, but the report form requires a CAPTCHA. Not automatable without circumvention. data.gov.in/Agmarknet needs a key and was unreachable from the sandbox. |
| Cloudflare-blocked (mandi grain pages) | 1 (F007) | 1.3 | commodityonline /mandiprices/* pages challenge non-browser clients; kisandeals 403; napanta 502. |
| Brand MRP, history incomplete (not safe to register) | 18 (F010, F012, F016, F017, F018, F019, C001, C002, C003, H001, H002, H003, H004, T006, K002, P001, P002, P003) | 21.2 | Packaged goods: only isolated documented steps exist (e.g. Amul butter 62->58, ghee 650->610 on 22 Sep 2025, GST cut). Official butter/ghee indices rose ~3.5% after Oct 2025, so a flat register would be wrong. ToS blocks e-commerce scraping. |
| No machine-readable source: fares/fees/services | 13 (M002, M003, M004, T003, S001, S003, E001, E002, E003, E004, D001, D003, P004) | 13.6 | Bus/auto fares (latest press is 2022), school/tuition fees, doctor/hospital, haircut, cinema, street food, newspaper, RMC water (increase only proposed). |
| Judged unrepresentative (kept official-linked on purpose) | 0 () | 0.0 | NPPA paracetamol ceiling is real but one controlled drug is a worse proxy for 'medicines' than the broad official index. |
| No revision found / unverifiable | 1 (K003) | 0.9 | Telecom/broadband/OTT: last verified hike Jul 2024; no later revision found, which is not proof of none. |
| Genuinely no data | 1 (T005) | 1.6 | No official item and no independent source. |

Sum of blocked weight: 61.5% (= 100 - 38.5).

## Best case per unlock (cumulative, from 38.5%)
| Unlock | + points | Independent % after |
|---|---|---|
| Own rent survey (R001) | +19.7 | 58.2 |
| + DoCA-class staples (own kirana survey or captcha-free feed) | +3.3 | 61.4 |
| + own packaged-goods price survey (fixed brand packs) | +21.2 | 82.6 |

Reading: no *automatable, permitted, real* feed remains for any block >2%. 40% is reachable only through data we collect ourselves (rent alone gets to ~58%; rent + staples to ~61%).