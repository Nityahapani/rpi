# New-source sweep, 2026-10-02 (nothing below is wired into the index yet)

Independent weight today: **18.4%**. Credibility key: **P** = primary/official origin, **S** = secondary mirror or press, **A** = aggregator.

## A. Usable now (reachable, robots allow, real, Rajkot-specific)
| # | Source | Origin | Cls | Basket items | Weight pts | Verdict and caveats |
|---|---|---|---|---|---|---|
| 1 | **acrop.app Rajkot APMC** `/mandi/gujarat/rajkot/rajkot/<crop>` | AgMarkNet via data.gov.in (stated on page) | S, P origin | F001 wheat, F003 arhar, F004 moong, F005 chana (+F006 groundnut *seed* as a weak oil proxy) | +5.1 (+1.3 weak) | ADOPT as Tier-B proxy. Server-rendered HTML, daily modal/min/max/arrivals, robots `*` allow, fetched 200 from sandbox. Caveats: wholesale raw grain, not packaged retail; the modal price mixes varieties (mix shifts add noise); only 30 days of history (earlier months stay official-linked, spliced like gold/eggs); a third-party mirror that could change layout. Gate: promote to independent only if it tracks the official item index (rolling correlation) once about 6 months have accumulated. |
| 2 | **NDTV fuel, Rajkot** | OMC pump prices | A | T001/T002 | 0 (cross-check) | USE as a second look at fuel. Petrol 102.03 and diesel 98.16 (2 Oct) against our goodreturns 102.16 and 98.29: agree within 0.13 (about 0.13%). parkplus/Rozkabhav ₹115.01, ₹101.56 etc. stay rejected. |

## B. New facts that change existing data (need your call)
| Finding | Evidence | Effect |
|---|---|---|
| **PNG hike effective 3 Sep 2026**: ₹49.03 to ₹50.22/SCM pre-tax (+₹1.19, +2.4%; ₹53.22 with tax), "Gujarat Energy"/Gujarat Gas | TOI Surat 4 Sep 2026; Construction World 8 Sep 2026; Gujarat Mitra 4 Sep 2026 | Our R005 shows ₹49.02 flat to 1 Oct (goodreturns), which equals the *old pre-tax* rate, so the Rajkot figure is probably stale since 3 Sep. The press covers Surat and South Gujarat; a Rajkot-specific confirmation is still missing. Do not edit until Rajkot is confirmed. R005 is small. |
| **Ahmedabad auto fare hike, Jun 2026**: min ₹20 to ₹25, per km ₹15 to ₹20 | DeshGujarat 22 Jun 2026 (Transport Commissioner meeting; Ahmedabad) | NOT applied to Rajkot. The official Gujarat-urban auto index rose only about 3% by Aug 2026, so there was no statewide step. Rajkot revision unconfirmed. Rapido cut its Rajkot per-km rate ₹15 to ₹12 (May 2026, app fare, not a regulated fare). |
| Telecom: Airtel 84-day plan ₹859 to ₹899, Vi plan removals, Jio data-pack validity cut (Apr 2026, ABP) | ABP 22 Apr 2026 | Plan-level and circle-specific. Needs a *named fixed plan* to register. Official K001 shows only +1.6% by Aug. Not adoptable as-is. |

## C. Probed and not adoptable (reasons)
| Source | Finding |
|---|---|
| Rent: Magicbricks / Housing / 99acres / SquareYards | Asking-price listings and sale rates per sq ft; "average rent" is a broad range per locality. No time series of rents, not CPI-style. 99acres property-rate pages have NA quarters. |
| RMC city bus (RMTS/BRTS) | Only an unofficial third-party fare calculator (₹15 for 6 km) and a Reddit pass price (₹330 a month). No official fare notification found. |
| GSRTC | 25% hike on 31 Jul 2023 (80/85/77 paise per km); nothing since. Statewide intercity, not the city index item (T003). |
| School fees | Saurashtra FRC had no chairman from 31 Jan 2025 (650 fee files pending, Bhaskar Jul 2025). No fee series; statutory caps from 2017 are unchanged. |
| IndiaMART Rajkot oil (singtel tin ₹2,650 to ₹3,400) | Seller *list prices* for different brands and tin sizes, not transactions; page already returns 429. NCDEX groundnut-oil ₹155/kg is a futures reference. Rejected. |
| NHB / todaypricerates veg retail | Vegetables are already covered by Gondal APMC; todaypricerates is an unaccountable aggregator ("on-ground agents"). |
| DoCA retail monitor | 555 centres, 22 commodities, CAPTCHA-gated; the all-India average on the home page cannot proxy Rajkot. data.gov.in catalog entries stop in 2015. |
| Milk | Amul/Mother Dairy +₹2/L on 14 May 2026 (already in F009). Nothing Rajkot-specific beyond that. |

## D. Net result
Adopting #1 would move independent weight from 18.4% to about 23.5% (about 24.8% with the weak groundnut-seed proxy). It does not reach 40%. Rent (19.7 points) stays the one block big enough, and no public Rajkot rent series exists.

## E. Status after wiring (same day)
- WIRED: `mandi_rajkot_apmc` (F001, F003, F004, F005) and `mandi_rajkot_veg` (F021, F022, F023, F025 as a second quote beside Gondal). F006 groundnut seed was NOT used (weak proxy for an oil).
- NOT WIRED: NDTV (Akamai 403 from the sandbox, no evasion); PNG +Rs1.19 (Rajkot unconfirmed); Ahmedabad auto fare (not statewide); telecom (no named plan).
- Independent plan weight: 18.4% -> **23.5%** (direct 10.7% + proxy 12.8%). All 10 proxy items are `pending` validation (0 months overlap with the official index so far; judged after 6).
- Two engine fixes made on the way: (1) official stand-in months are cut off where an independent series starts (no double quotes once MoSPI publishes Sep); (2) volatile daily feeds need >=5 observation days in a month, otherwise a 1-2 day partial month swung the Oct nowcast +1.9%.

## F. Second sweep (2026-10-02, later the same day)

**Wired in (all independent of the official index):**

| Item | Series | Evidence | Status |
|---|---|---|---|
| R004 water (w 0.37) | RMC residential water Rs1,500/yr, flat since FY23-24 | IE 9 Feb 2023 (set at 1,500); TOI 4 Feb 2026 (draft 1,500->2,400); DeshGujarat 11 Feb 2026 (committee scrapped the Rs95 cr hike) | corroborated; General Board vote not separately confirmed |
| K001 mobile (w 0.90) | Jevons of Jio Rs299 fixed plan (flat since 3 Jul 2024) and Airtel entry unlimited plan (Rs299 -> Rs349 on 12 Aug 2026) | Airtel change: India Today, Moneycontrol, Trak, Financial Express. Jio: Bajaj Finserv, NDTV Profit, dailydigihelp | verified; no quality adjustment (Rs349 has 2 GB/day) |
| S002 OTT (w 0.90) | Jevons of JioHotstar Super annual (899 -> 1,099 on 28 Jan 2026) and Amazon Prime annual (1,499 flat) | Variety, Business Standard, Techloy; Inc42 2023, amazon.in listing via Zoutons | verified / corroborated; new-subscriber list prices |
| F005 chana (w 1.28) | Rajkot yard board, NAMED variety chana-yellow, midpoint of low/high | agrobhai.com (robots allow) | replaces acrop chana, which pools yellow and kabuli varieties |

**New cross-check:** `rpi/crosscheck.py` compares the acrop modal for wheat, tur and moong against the yard board's low-high band every refresh (all agree on 1 Oct 2026). Its first run found the F005 problem: acrop chana modal Rs8,649/q sits outside the yellow-chana band (Rs5,900-7,105/q); acrop's own min-max for chana spans 5,900-10,780.

**Rejected / blocked in this sweep:**
- commoditiescontrol.com edible-oil spot: Terms of Use prohibit automated scraping and bulk download. Not scraped.
- NCDEX spot (Groundnut Oil Rajkot): serves a JS fingerprint bot-challenge; not evaded. CEIC mirror is paywalled.
- RMTS bus fare (T003): only a Scribd upload of an unknown date; no official fare table found. Not adopted.
- Gujarat Gas site: no machine-readable tariff page found; the PNG hike (3 Sep 2026) is documented for Surat only. Rajkot's pre-hike goodreturns price (49.02) is within 1 paisa of Surat's (49.03), which suggests one statewide domestic rate, but it is still not confirmed, so R005 is unchanged and flagged.
- acrop `/prices/jaggery/...`: 404; acrop rice/gujarat lists a single mandi (Dahod). No usable Rajkot-region rice or jaggery quote.

## G. Third sweep (2026-10-02): more yards, more cross-checks

**Wired in:** `mandi_rajkot_district` = Gondal, Jetpur, Jasdan yards (acrop, AgMarkNet origin) as extra quotes for wheat (F001), tur (F003), moong (F004) and desi chana (F005 at Gondal and Jetpur), averaged with the Rajkot yard (equal-weight Jevons). Why: one yard's modal is mostly arrival-mix noise. On 30 Sep-1 Oct the tur modal was Rs6,750 at Jasdan, Rs7,250 at Rajkot, Rs8,150 at Jetpur and Rs8,250 at Gondal. Equal weights are a choice, not a finding: the Rajkot yard is 1 of 4 quotes.
Excluded: Jasdan chana (modal jumped 4,750 -> 6,250 in a day = pooled varieties), Upleta and Dhoraji (moong has no rows; thin elsewhere).

**Cross-check extended:** the Gondal board (agrobhai.com/gondal-apmc) now checks Gondal wheat, tur, moong and chana against the acrop modal (acrop may lag by up to 2 days). All agree on 1 Oct 2026. Caveat: tur and moong bands are wide (e.g. tur 901-1,841 per 20 kg), so "agree" is a weak test there; wheat and chana (narrow bands) are the sharp ones.

**Considered and not adopted:**
| Source | Why not |
|---|---|
| BankBazaar fuel / gold / silver | Fuel shows Rs115.01 with Rs40.07 / Rs100.10 glitches. Gold and silver sit at a constant offset above goodreturns (+Rs99/g, +Rs5/g) with identical daily moves: the same upstream feed, so no independent corroboration. |
| Edible-oil boards in Gujarati news | Real Rajkot yard 15 kg-tin prices exist, but publication is event-driven, there is no index page, and dates in slugs can be wrong. Biased toward big-move days. |
| Apple India store (K002) | Single-model series is dominated by launch-cycle price cuts; not the hedonic basket item. |
| NPPA paracetamol ceiling (M001) | Official and real (Rs0.92 Apr 2025 -> Rs0.93 Apr 2026, WPI +0.64956%), but rounded to the paisa (a 1.1% step) and one controlled drug is a poor stand-in for "medicines". Stays a corroboration-only check. |
| Broadband (K003) | Entry plans reported as Jio Rs399 / Airtel Rs499, but only by blog sites; no dated change history from operators or reputable press yet. |
| Rajkot auto fare (T004) | No Rajkot fare notification found (only Maharashtra's tariff card); app fares (Rapido Rs15 -> Rs12/km, May 2026) are not regulated tariffs. |

**What the index gets from this, and when:** nothing visible today. A staple enters the chained index only once it has two consecutive months of at least 5 daily readings; the Rajkot/Gondal/Jetpur/Jasdan quotes all have September, so the first matched pair appears when October reaches 5 days (about 6 Oct 2026).

## H. Fourth sweep (2026-10-02): one new cross-check wired, three strong leads documented

**Wired in (cross-check only, never feeds the index):** `crosscheck:ibja` compares goodreturns Rajkot gold 22K (P005) and silver (P006) with the IBJA daily AM/PM benchmark (ibjarates.com), a different publisher. Bands were fixed before looking at the data: gold within +/-3% of IBJA 916, silver within +/-10% (weak, because retail silver carries a wide premium). Observed premium over IBJA on 28 Sep-1 Oct 2026: gold +0.7% to +1.6%, silver +6.2% to +8.4% (silver drifts a lot, so only gold is a sharp test). National benchmark, not Rajkot-specific; it checks the Rajkot feed's *level and direction*, not local spreads. The page holds only 4 days, so the check runs every refresh on whatever days overlap.

**Strong leads that could NOT be wired honestly (and why):**
| Lead | What we know | Blocker |
|---|---|---|
| Gujarat FRC approved-fee orders (frcgujarat.org) for E001 school fees (weight ~2.5) | Official, per-school, per-class, per-year 2017-18 to 2026-27; 15,428 entries; Rajkot zone has its own committee | Not reachable from the sandbox; the fee view is a POST/JS page and the per-school links could not be recovered. Needs a browser-capable fetch or a hand-curated 3-5 school register. |
| Amul butter/ghee MRP (F011/F012) | Sep 2025 GST cut verified by 6+ outlets (butter 100 g 62->58, ghee 1 L 650->610, effective 22 Sep 2025); no later change found | Jan-Aug 2025 level unverified (one list says ghee 630), so no verified base-month price. |
| Gujarat Gas domestic PNG hike, 3 Sep 2026 (R005) | New tax-inclusive rate Rs53.22/SCM agrees in four outlets incl. two Gujarati ones describing a state-wide rise | Hike size disagrees (+1.19 / +4.20 / +6.53) and the goodreturns base is not stated as pre- or post-tax. Series stays flat at 49.02 and flagged stale. |

**Also checked, not adopted:** PPAC (metro cities only, no Gujarat city), ChiniMandi sugar (national/mill news, no Rajkot quote), eNAM web (no usable open Rajkot price table found in this pass).

## I. Fourth sweep, second pass: everything else that was checked

Re-ran the hunt for anything wirable. Result: **nothing new passed the accuracy bar**, but the evidence is now logged in `data/official/local_corroboration.csv` (dated, sourced, with a status and an explicit "use" column) so it can be wired the moment the missing piece appears.

| Target | What was found | Why it is not in the index |
|---|---|---|
| E001 school fees (w 2.50) | Three Rajkot schools publish FRC-approved fees: Rajkumar College (2025-26 and 2026-27, +8.24% for Classes 1-6 after the FRC order of 21 Jan 2026), Nirmala Convent CBSE (2025-26), Delhi World Public School (2025-26) | No school has two verified years plus a Jan 2025 base. Rajkumar's 2024-25 PDFs are not archived; the DWPS fee page is an image banner. One elite boarding school cannot represent 2.5% of the index. |
| F006/F007 oils (w 1.28 each) | Dated Rajkot tin levels in Gujarati news (groundnut 2,900 on 8 Aug, 2,925 on 11 Aug, 3,050 on 10 Sep 2026; cottonseed 2,795 / 2,825 / 2,850). Direction matches the official Gujarat-urban groundnut-oil index (+2.4% Jul to Aug 2026) | News reports cluster on big-move days and there is no Jan 2025 base. Official-linked stays; the levels are corroboration. |
| F011/F012 Amul butter, ghee | Sep 2025 step verified; Jan-Aug 2025 level still unverified; no later change | No verified base-month price. |
| R005 PNG | Tax-inclusive Rs53.22/SCM agrees in four outlets; hike size disputed (+1.19 / +4.20 / +6.53) | Level change cannot be applied without guessing. gujaratgas.com has no tariff table. |
| T003 city bus, T004 auto, S003 newspaper, F009 second dairy | RMTS fare matrix only as a Scribd upload; Gujarat auto fares last officially revised in 2022 (min Rs20, Rs15/km, TOI/PTI 8 Jun 2022) with no Rajkot notification since; no newspaper cover-price or Rajkot private-dairy retail price found | No dated, mainstream source with a base month. |
| agrobhai other yards | Botad, Junagadh, Jamnagar, Amreli, Unjha, Deesa boards exist (same format) | Same staples already covered by the Rajkot, Gondal, Jetpur and Jasdan yards. No oils, jaggery, rice, sugar or turmeric. |


## J. Sixth sweep (2026-10-02): PNG overlay wired, tea register not

| Item | Finding | Decision |
|---|---|---|
| R005 PNG | Gujarat Gas +Rs 4.20 (49.02 -> 53.22 incl. 5% VAT) from 3 Sep 2026; goodreturns still 49.02 on 2 Oct | **WIRED** as `data/png_events.csv` overlay, self-retiring, with staleness alarm and 3 tests |
| D002 chai | Association (about 2,500-3,000 stalls) new level 15 / 30 from 1 Sep 2026, five outlets; prior level 10 / 12 / 13 (half) and 20 / 24 / 26 (full); only earlier hike found is Mar 2022 (13 / 25, one outlet) | Later wired as PROXY (section Q): +15.4% lower bound |
| F013 sugar | Official Gujarat-urban sugar +17.3% in Aug 2026; press retail 48->68 or 50->75 per kg | Disputed; linked item already carries the official move |
| commoditymarketlive.com | Bot-verification interstitial on every page | Not scraped (no bypass) |
| Nowcast imputation | Peer imputation leaked a PNG step into rent | Replaced by own-trend (back-tested), setting `impute` |


## K. Seventh sweep (2026-10-02): one regulated series wired, one official benchmark accrued, one bug found

| Target | Finding | Decision |
|---|---|---|
| Labour Bureau CPI-IW, Gujarat centres | The home page carries a server-rendered popover per state with the last two months for every centre. Wayback captures recovered 2025-05..2026-08 for Ahmedabad, Bhavnagar, Rajkot, Surat, Vadodara (general index only). | **WIRED as a benchmark** (`data/official/cpi_iw_gujarat_centres.csv`, step `official:cpi_iw_centres`, `rpi/benchmark.py`); never an index input (industrial-worker weights, different population). Rajkot CPI-IW YoY Aug 2026 +3.54% vs RPI +5.34% vs MoSPI Gujarat-urban +4.68%; Rajkot grew the least of five Gujarat centres. |
| M001 paracetamol 500 mg | NPPA ceiling ex-GST: 0.92 (1.4.2025, S.O. 1489(E)), 0.93 (1.4.2026, S.O. 1575(E)); 0.90 before (derived). GST on drugs 12 -> 5% from 22 Sep 2025. | **WIRED** as a four-event register, counted in the PROXY share (a cap is not a shelf price). Independent share 25.7% -> 27.3%. Moves the Aug 2026 reference index by about -0.14 pt (107.60 -> 107.46) because the official Medicine index rose while the ceiling fell with GST. |
| Official-index pass-through diagnostics | After the 22 Sep 2025 GST cut, the official Gujarat-urban Butter fell -2.9% (Amul MRP -6.45%), Ghee -2.85% (Amul -6.15%), Medicine -0.8% (full pass-through -6.25%). | Logged in `data/official/event_checks.csv` -> `status.json:event_checks`. Diagnostic only: official-linked items can understate administered cuts that hit one dominant brand. |
| Amul F011/F012 | Same blocker as before: Jan-Aug 2025 baseline unverified. | Not wired. |
| HUL Dove/Lifebuoy MRP cuts | Single outlet (Livemint blog). | Not used. |
| Rent (19.67% weight), school fees, oils, tea | No new authentic dated series. | Unchanged (deferred / lead only). |
| Nowcast methods | Rolling-origin back-test on 66 official item series (19 months, 11 one-step origins): own-trend 0.65 pp RMSE vs zero-change 0.77 vs old division peer-fill 1.03-1.15. | Own-trend retained; split-conformal 90% band added (+/-1.23% at h=1, +/-2.09% at h=2) and a real-time vintage log (`data/nowcast_vintages.csv`). |
| GEKS-Jevons variant | Published 103.99 was an artefact: pre-base register events stretched the panel, the first period held one SKU and `geks_rel` returned NaN for most items. | **FIXED** (`rpi/index/geks.py`, engine clips pre-base quotes, regression test). GEKS now 108.56 vs chain 108.57. |


## L. Eighth sweep (2026-10-02): DoCA Rajkot retail quotes

Found by asking "who publishes RETAIL prices for Rajkot itself": the Department of Consumer Affairs Price Monitoring System (centre 454 = Rajkot). The official portal needs a CAPTCHA, so the data is read from an open third-party API that republishes the DoCA feed; its fidelity is re-proved on every run against DoCA's own home page (41/41 identical on 2026-10-01).

| DoCA commodity -> item | Official item | Months | corr | drift (pp) | DoCA vs official change since Jan 2025 | Verdict |
|---|---|---|---|---|---|---|
| Groundnut oil -> F006 | Groundnut oil | 20 | 0.56 | 0.7 | +8.0% vs +8.7% | **WIRED** |
| Sugar -> F013 | Sugar | 20 | 0.89 | 4.2 | +21% vs +26% | **WIRED** |
| Gur -> F026 | Jaggery | 20 | 0.53 | 1.6 | +11% vs +13% | **WIRED** |
| Atta -> F001 | Wheat atta | 20 | 0.33 | 20.6 | +25% vs +1% | fail (retail quote 34 -> 40 is a sticky step series; official nearly flat) |
| Tur dal -> F003 | Arhar, tur | 20 | 0.32 | 25.7 | -27% vs -14% | fail |
| Moong dal -> F004 | Moong | 20 | -0.03 | 2.5 | +4% vs +0.5% | fail (flat) |
| Gram dal -> F005 | Gram: split | 20 | 0.43 | 4.2 | -8% vs -8% | fail (corr 0.43) |
| Sunflower oil -> F008 | Refined oil | 20 | 0.38 | 16.5 | +33% vs +15% | fail (official item is a broader refined-oil class) |
| Butter -> F011, Ghee -> F012 | Butter, Ghee | 20 | 0.33 / 0.06 | 4.3 / 2.3 | +7.5% / +1% vs +3% / +3% | fail (flat; DoCA shows no Sep-2025 GST cut either) |
| Tea -> F014, Salt -> F015, Turmeric -> F016 | Tea leaf, Salt, Turmeric | 20 | -0.12 / -0.22 / -0.02 | 3-8 | flat vs +3% / +7% / +8% | fail (flat) |
| Potato, Onion, Tomato, Banana, Brinjal -> F021-F025 | same | 20 | 0.44 / 0.45 / 0.53 / -0.54 / -0.23 | 16 / 0.7 / 32 / 2 / 60 | disagree strongly | fail |
| Eggs -> F020, Rice -> F002 | Eggs, Rice | 20 | 0.28 / -0.07 | 6.8 / 6.5 | | fail (rice is not basmati) |

Not adopted: the verdict is not that DoCA is wrong and the official index right; it is that a one-reporter, whole-rupee, sticky series does not track the thin-sample official index closely enough to carry weight. They stay on the existing proxies or official stand-ins and are re-screened daily.

Also tried: shop.amul.com (robots allows crawling but the product API returns Unauthorized without a session handshake; not pursued), JioMart/DMart (retail-platform terms; not scraped), data.gov.in (HTTP 500 from the public sample key).


## M. Ninth sweep (2026-10-02): Gujarat statutory auto-rickshaw tariff

| Lead | Evidence | Verdict |
|---|---|---|
| Gujarat auto-rickshaw fare notification, effective 7 Aug 2026 (MV Act s.67) | Gujarat Samachar 7 Aug 2026 quotes the notification; ABP Asmita, GSTV, News18 Gujarati (8 Aug); 22 Jun 2026 Gandhinagar meeting reports. Min Rs20 -> 25 (1.2 km), Rs15 -> 20/km, night +50%, waiting Rs1/min after 5 min | **WIRED as T004** (fixed 3 km trip Rs47 -> Rs61), counted as PROXY (legal maximum) |
| 2022 tariff baseline | PTI/Goodreturns 8 Jun 2022 (Rs18 -> 20, Rs13 -> 15/km); 2026 articles: ~3 years without a hike; 2026 notification cancels the 2022 one | verified baseline |
| Official Gujarat-urban auto index | 99.89 (Jan 2025) -> 102.73 (Jul) -> 102.91 (Aug 2026): +0.2% Jul-Aug | does not yet show the step; event check will compare Sep 2026 |
| Airtel Xstream entry broadband (Rs499 + GST, 40 Mbps) | airtel.in rendered page (manual, 2 Oct 2026); launch Sep 2023 (The News Minute) | not wired: client-rendered, no archived price, not collectable at run time |
| JioFiber Rs399 | blogs only; jio.com plan URL is 404 / JS | not wired |
| Rajkot city bus (RMTS/BRTS) fares | rmts.somee.com (unofficial), Scribd copy, Play-store app listing | not wired: no primary notification found |
| Rajkot APMC via eNAM / commodityonline | already covered by acrop.app | no new information |


## N. Ninth sweep, part 2 (2026-10-02): clothing and rent

| Lead | Evidence | Verdict |
|---|---|---|
| Jockey India men's apparel list prices (C001/C002) | jockey.in/products.json (robots allow); Wayback snapshots Nov 2024-Sep 2025; 115 candidates, ~40-55 SKUs processed | gate FAIL (corr -0.45 / 0.20); official clothing +5-6% vs Jockey flat; quarantine + daily screen |
| Footwear brand web stores (Paragon, Walkaroo, Campus) | Shopify feeds reachable; prices variant-specific and discount-driven (e.g. Paragon 599 vs 416 same product) | not attempted |
| Spykar, Levi's, Wrogn, Snitch (jeans) | feeds reachable but products re-created (no pre-Nov-2024 product ids), Wayback pages absent | not usable |
| MagicBricks Rajkot rent list pages | 5 pages x 30-50 JSON-LD RentAction records with listing dates; Wayback: 2 list-page captures + 62 detail captures (Feb/May 2026 only) | diagnostic only; noise +-12% vs 0.2%/month signal |
| 99acres / Housing.com / Square Yards / NoBroker / Makaan | HTTP 403/406/410 | blocked, not bypassed |
| Locality "price trends" (99acres, MagicBricks) | sale prices per sq ft, not rents | rejected |
| Labour Bureau CPI-IW Housing group | all-India group index only on the pages reached (140.6); centre housing index is revised half-yearly (Jan/Jul) | not wired (official, benchmark-grade at best) |


## O. Eleventh sweep (2026-10-02): FMCG brand stores, a Gujarat-wide DoCA panel, schools, restaurants, CPI-IW housing

| Lead | Evidence | Verdict |
|---|---|---|
| DoCA all-India balanced panel (also a Gujarat panel and the Rajkot centre), same `judge` gate, most-local-panel-that-passes rule | /api/mapseries with limit=1200 (the default 400-day window truncates and an earlier draft of this row was wrong because of it) | **WIRED as proxy**: F002 rice (corr 0.69, drift 0.014), F008 sunflower oil (0.75, 0.037), F011 butter (0.66, 0.008); Rajkot centre and Gujarat panel fail for all three. Also passing nationally but already independent via mandi/NECC: F003, F005, F020, F024 (not switched). Fail: F001, F004, F012, F014, F015, F016, F022, F023, F025. `scripts/screen_doca_panels.py`, `data/official/doca_panel_screen.csv` |
| Crompton 9 W Dynaray LED bulb (H003) | Shopify feed, price = list price (no compare_at); archived Aug/Oct 2025 pages Rs150 = live Rs150; Feb/Jul 2025 captures are JS shells | diagnostic accrual `data/mrp_diary.csv`; no verified Jan-2025 baseline and flat |
| Orient Electric LED | list vs compare_at gap 40-70% (discount-driven) | rejected |
| Himalaya Wellness (shampoo, toothpaste, soap) | Shopify feed; pack prices inconsistent with shelf MRPs (e.g. 340 ml shampoo Rs311-399 across products, baby shampoo 400 ml Rs1090) | rejected |
| Milton, Balaji, Organic India, Vahdam, Teabox | Shopify feeds reachable, but products are not basket specs | not used |
| Prestige, Hawkins, Borosil, Pigeon, Syska, Wipro, Navneet, Classmate, Nestle, Parle, Britannia, Tata Consumer, Patanjali, Amul | no public products.json (404) or JS-rendered pages | not scrapable |
| School fees (E001) | frcgujarat.org per-school lookup is form-driven and unreachable from the sandbox; aggregator pages (careers360, getschoolsinfo) are UDISE+ derived and undated | not wired |
| Veg thali / chai (D001-D003) | Justdial price-for-two bands, restaurant listings without dated menus | not wired |
| Labour Bureau CPI-IW Monthly Index Letter (Aug 2026, PDF) | centre-wise GENERAL index only (Rajkot 146.2); centre housing group index is on paywalled CEIC | no Rajkot housing series |

| amul.com product info pages (F011/F012 baseline) | Wayback has Apr 2025 and Jan 2026 captures of the ghee page, but amul.com info pages carry no prices | no baseline; dead end |
| AIIMS Rajkot OPD fee (M003) | Citizen charter: Rs10 registration, unchanged; subsidised government rate, not the private GP fee the item measures | not used |
| Newspaper subscriptions (S003) | TOI subscription page is dynamic and national; Gujarati dailies publish no rate card | not wired |


## P. Twelfth look (2026-10-02): more brand stores, price trackers, chai re-check

| Lead | Evidence | Verdict |
|---|---|---|
| Bajaj Electricals (H003/H004) | Shopify feed, 0 of 718 products carry compare_at (list prices); 3 L pressure cookers and 9 W LED present; Wayback captures of product pages only from Apr 2025 | accruing diagnostic (`data/mrp_diary.csv`); weights 0.24 / 0.09, no Jan-2025 baseline |
| Relaxo, Campus, Wonderchef, Killer Jeans, Van Heusen, Zudio, Westside | feeds reachable; 60-99% of products carry compare_at above price (discount-driven) | rejected for C001-C003 / H004 |
| Epigamia, Bikanervala, Tata Simply Better, Sleepycat | feeds reachable, products not basket specs | not used |
| Open Food Facts Prices (crowd-sourced receipts) | 320k prices, mostly France; 7,436 locations, none in Rajkot | no Indian coverage |
| Rajkot cutting chai (D002), re-checked | 5 outlets on the new 15 / 30 level from 1 Sep 2026; prior level still disputed (10 / 12 / 13), only a Mar 2022 step before it | wired later as PROXY, see section Q |
| GSRTC fares +3% from 1 Jan 2026 (+10% Mar 2025) | state intercity buses, not the city bus item T003 | not an input |
| RMC water / garbage charges | 2026-27 hike only proposed (Rs1,500 -> 2,400), political approval doubtful | no change registered |
| Sumul milk hike 19 May 2026 | Surat dairy, not Rajkot | not used |

## Q. Thirteenth look (2026-10-02): chai wired as a proxy

| Item | What was done | Status |
|---|---|---|
| D002 Rajkot cutting chai | Tariff register: 2025-01-01 half cup Rs 13.0 (`derived`, association's own quoted prior level per Divya Bhaskar), 2026-09-01 Rs 15.0 (`verified`, five outlets). Step **+15.38%**. Basket tier D -> C. | **PROXY** (association rate card, not a paid price) |
| Sensitivity | Press prior level 10 / 12 / 13. The +50% reading (10 -> 15) is not used; it would put about +0.6 pt more on the 2026-09 index. | lower bound used |
| Check | `data/official/event_checks.csv`: compare MoSPI "Tea: cups" Gujarat-urban 2026-08 vs 2026-09 once released (mid-Oct). | pending |

Other Rajkot price news checked for item fit in this look (none wired):

| Lead | Finding | Verdict |
|---|---|---|
| Rajkot School Van Association, +10% from 8 Jun 2026 | Association decision, ~4,500 vehicles; two outlets, figures differ (TV9 +Rs150 on Rs1,200; Jagran Rs1,000 -> 1,150) | No school-transport item in the basket; logged in `local_corroboration.csv` only |
| Farsan / thali, Gujarat Samachar 1 Apr 2026 | +Rs20-40/kg farsan, thali "also up", traders quoted informally | Unverified, no baseline, D001/D003 stay unwired |
| Rajkot Dairy retail circular, 14 May 2026 | Same +Rs2/L round as Amul; F009 already uses the Amul Gold 500 ml register | Already covered |
| RMTS / Janmarg city bus fare (T003) | Only an unofficial fare page and a Scribd matrix (Rs5 up to 2 km ... Rs30 over 36 km); no dated revision | Unwired: a flat fare with no found revision is not proof of none |
| Salon / haircut (P004) | Maharashtra Barbers' Association +20% (Jun 2026); no Rajkot or Gujarat association notice found | Unwired |
| Doctor / lab fees (M002-M004) | Practo / myupchar / medifee list prices, no dated history | Unwired |

## R. Fourteenth look (2026-10-02): F003, F005, F020, F024 moved to the gated national panel

| Item | Before | After |
|---|---|---|
| F003 tur dal | Rajkot APMC + Gondal/Jetpur/Jasdan yard quotes, about 1 month, ungated | DoCA all-India retail panel (commodity 11), corr 0.91, drift 0.044 |
| F005 chana dal | Rajkot yard board + Gondal/Jetpur chana, about 1 month, ungated | DoCA commodity 10, corr 0.86, drift 0.030 |
| F020 eggs | NECC Ahmedabad wholesale, about 1 month, ungated | DoCA commodity 36 (per dozen, converted to per egg), corr 0.89, drift 0.025 |
| F024 banana | Gondal veg market, 10 days, ungated | DoCA commodity 41, corr 0.59, drift 0.060 |

Local feeds still ingest but are filtered out of the index by `rpi/superseded.py`. F011 butter's unit label is corrected to Rs per 100 g (relatives unchanged).

## S. Fifteenth look (2026-10-02): new official, retailer and association sources probed

| Source | What it is | Result |
|---|---|---|
| OEA Wholesale Price Index (eaindustry.nic.in, base 2011-12) | Official, DPIIT, monthly xls with item-level wholesale indices (clothing, packaged food, soap, etc.) | Reachable, but the newest file is **June 2026** (`monthly_index_202606.xls`; 202607-202609 return 404). That is older than the official CPI we already hold (Aug 2026), so it cannot supply a fresher or independent signal for the months that matter. National wholesale. Not wired. |
| DMart Ready (digital.dmart.in JSON search API) | Branded grocery with `price_MRP` and `price_SALE` per SKU | Works anonymously, but Rajkot pincodes 360001-360023 all return `isHDEnabled=false, isPUPEnabled=false`; only Ahmedabad (380001) is served. Default prices are not Rajkot. Not wired. |
| JioMart | Serves Rajkot, pincode-priced | Search API behind Akamai (Access Denied). Not bypassed. |
| BigBasket 403, Zepto 202 empty, Blinkit/Instamart app-only | Quick commerce | Not reachable. |
| e-NAM (enam.gov.in) | Official mandi trade data incl. Gujarat APMCs | Trade-data endpoint needs an interactive session; plain POST returns the home page. Not bypassed. A second mandi feed would only cross-check F021-F025, not add independent weight. |
| NCDEX spot, MCX | Exchange spot prices | NCDEX page is a fingerprint-JS shell; MCX 403. |
| Jan Aushadhi (janaushadhi.gov.in) | Generic medicine price list | Reachable, static product list without dated history (M001 is already on the NPPA ceiling). |
| RBI HPI / NHB Residex | House price indices | Cities covered are metros plus Ahmedabad, not Rajkot; not rent. |
| BSNL, GSSTB (textbook prices), CEA, NCCF | Government | Not reachable from the sandbox. |
| Telecom (K001) | Re-checked: Airtel withdrew Rs299 and four other plans on 12 Aug 2026; Jio kept Rs299 and added Jio Prime (Rs300/yr) | Already in `tariff_events.csv` (Airtel Rs299 -> 349 on 2026-08-12; Jio Rs299 re-confirmed 2026-08-21). Analysts expect a headline hike Oct-Dec 2026; none announced yet. |
| OTT (S002) | JioHotstar hike of 28 Jan 2026 and Prime Rs1,499 re-confirmed | Already in `tariff_events.csv`. Netflix India Rs149-649 unchanged. |
| cpi.reclaimchennai.city OpenAPI | Checked `/api/openapi.json` for undocumented datasets | Only the 10 endpoints already used. |
