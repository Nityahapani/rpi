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

## T. Sixteenth look (2026-10-02): Amul MRP register re-tested (rejected); NECC egg archive found (corroboration only)

| Lead | Finding | Result |
|---|---|---|
| Amul / GCMMF butter and ghee administered-MRP register (F011, F012, maybe F010) | The 22 Sep 2025 GST cut is verified by about ten outlets (butter 100 g 62 -> 58, ghee 1 L carton 650 -> 610, butter 500 g 305 -> 285, ghee 5 L tin 3,275 -> 3,075). The dates on which butter reached Rs62 and ghee Rs650 were not found, and no butter or ghee change after Sep 2025 was found (only milk +Rs2/L on 14 May 2026). Retail listings mix tin, carton and tetra packs and cannot confirm an MRP. | **Not wired.** A single dated step is not a path. The two cuts stay in `event_checks.csv` as event tests (pass-through 0.46, official_muted). Official butter and ghee indices rose about 3.5% after Oct 2025, so a flat register after the cut would be wrong. |
| NECC egg price archive (eggs.reclaimchennai.city/data/egg_prices_daily.csv, publisher e2necc.com) | Primary NECC "Suggested" and "Prevailing" daily rates for about 34 zones. Ahmedabad: 6,480 daily rows, 2009-01-01 to 2026-10-01. Reachable from the sandbox. | **Corroboration only.** NECC Ahmedabad is wholesale and one zone. `scripts/crosscheck_eggs_necc.py` writes `data/official/egg_crosscheck.csv`. |

F020 eggs cross-check (monthly means, 20 overlapping months, Jan 2025 - Aug 2026):

| Series | Compared with | corr (m/m) | drift | Verdict |
|---|---|---|---|---|
| DoCA all-India retail (wired) | Official Gujarat-urban eggs | 0.89 | 0.025 | pass |
| NECC Ahmedabad wholesale (not wired) | Official Gujarat-urban eggs | 0.55 | 0.017 | pass |
| DoCA national vs NECC Ahmedabad | each other | 0.60 | 0.008 | pass |

Reading: two separately sourced series agree with each other and with the official index on level and seasonality (December peak, March-April trough). That supports keeping DoCA national as the F020 feed, and it removes the worry that F020 rests on one civic mirror. DoCA stays primary because its correlation with the official index is higher and it is retail. No weight or plan change. The same archive's retail.json covers six metros only (not Rajkot) and BigBasket/Zepto scrapes there are failing.

## U. Sixteenth look, part 2 (2026-10-02): other categories swept (transport, civic, education, food-away, health, rent, handsets)

| Area | What was found | Result |
|---|---|---|
| RMC water (R004) and garbage | Draft FY26-27 hike (water Rs1,500 -> 2,400; garbage Rs365 -> 800) was scrapped by the standing committee (TOI 10 Feb 2026, DeshGujarat 11 Feb 2026) | Already wired as a flat register (R004). Re-confirmed, no change. |
| GSRTC fares | +25% 1 Aug 2023, +10% 29 Mar 2025, +3% 1 Jan 2026 (no rise up to 9 km, +Rs1 for 10-60 km). The official Gujarat-urban bus-fare index moved +2.7% (Mar -> Apr 2025) and +1.2% (Dec 2025 -> Jan 2026), so the official series tracks the effective rise, not the 10% / 3% headline | Not an input: statewide intercity tariff, not the city bus item (T003). A nominal-tariff register would overstate by about 4x. |
| School fees (E001) | Gujarat FRC caps (Rs15,000 / 25,000 / 27,000, science 30,000) were set in 2017-18 and have not moved; most Rajkot private schools charge above the caps and are approved school by school | No cap path to register. School pages already held as corroboration only. |
| Thali (D001) | Only Ahmedabad (Rajwadu, Rs518 sale / 575 list). No Rajkot restaurant with a dated price history | Unwired. |
| Hospital ward (M004), two-wheeler service (T005) | Aggregator ranges (Rs3,000-6,000 per day; labour Rs350-500) with no dates | Unwired. |
| Cinema (S001) | Rajkot has Cinepolis, PVR, INOX and Cosmoplex, but prices come only from live booking pages | Unwired. |
| Packaged tea (F014) | Wagh Bakri and Tata price-hike stories are 2012-2024; nothing for 2025-26 | Unwired. |
| Rent (R001) | Magicbricks and 99acres "rates and trends" pages are JavaScript shells (empty table) or sale prices per sq ft; rent history is not published. Their terms bar scraping. | Unwired. `rent_listings.csv` stays a diagnostic. |
| Handsets (K002) | Large dated MRP rises in 2026 from the memory-chip shortage: Samsung A56 +Rs2,000 (5 Jan), A36 +Rs1,500 (5 Jan), then +Rs3,000 (24 Sep); A17/A27/F17/A07 (2 Sep); iPhone 16 128 GB Rs69,900 -> 89,900 (10 Sep, Apple repriced the whole older line-up after the iPhone 18 launch). Samsung quotes mix MRP, "list", "offer" and with/without-charger prices. | **No register.** A single-model Apple path (79,900 -> 69,900 on 9 Sep 2025 -> 89,900 on 10 Sep 2026) fails the gate against the official handset index: corr 0.43, drift 0.161 over 20 months. The official index is quality-adjusted, so a fixed-model list price is a different quantity. Three events added to `event_checks.csv` instead (`scripts/add_k002_events.py`). |

K002 event checks (diagnostic only):

| Event | Expected | Official handset index | Ratio | Verdict |
|---|---|---|---|---|
| iPhone 16 128 GB 79,900 -> 69,900, 9 Sep 2025 | -12.52% | -1.76% (Aug -> Oct 2025) | 0.14 | official_muted |
| Galaxy A56 8/128 38,999 -> 40,999, 5 Jan 2026 | +5.13% | +0.27% (Dec 2025 -> Feb 2026) | 0.05 | official_muted |
| iPhone 16 128 GB 69,900 -> 89,900, 10 Sep 2026 | +28.61% | not yet published (Oct 2026 index due mid-Nov) | n/a | pending |

Reading: the official handset index barely moves when fixed-model list prices move. That is expected for a hedonic index, but it means K002 (weight 0.80) rests on a stand-in that may understate the 2026 handset rise. This is flagged, not adjusted. Sep and Oct 2026 handset prices in the nowcast carry upside risk (Samsung 2 and 24 Sep, Apple 10 Sep).

## V. Historical reference datasets — seasonal back-test of the nowcast (sweep 16c)

**Datasets ingested as reference only (not index inputs; `data/reference/`, fetched by `scripts/fetch_reference_history.py`):**
- WFP/HDX "India – Food Prices", Rajkot + Ahmedabad retail rows (`wfp_gujarat_retail.csv`). Rajkot 2010-04 → 2023-07 (Gujarat reporting stops upstream). Cannot feed 2025+.
- NECC Ahmedabad daily "Suggested" egg rate 2009-01 → 2026-10, reduced to monthly means (`necc_ahmedabad_monthly.csv`). Same data as the F020 cross-check (section T).

**Question:** does a calendar-month seasonal term learned from this history improve the `own_trend` fill used for nowcast months?
Rule: `forecast = mean(last 12 log relatives) + s_m`, with `s_m` = mean historical own_trend error for that calendar month.
Pre-registered adoption rule: out-of-sample RMSE gain ≥ 10% on the reference test (2018–2023, expanding window), AND no worsening on the official Gujarat-urban item indices (2025-02 → 2026-08, `s_m` learned on reference years only). Result in `data/reference/seasonal_backtest.csv`; script `scripts/seasonal_backtest.py`.

**Result: negative. No item adopted; the nowcast stays `own_trend`.** 14 mapped items (wheat flour, rice, moong, groundnut oil, sunflower oil, milk, sugar, tea, salt, potato, onion, tomato, jaggery, eggs):
- Reference test: seasonal term helped only potato (+3.9%, below the 10% bar), eggs (+18.9%), milk/salt (≈ +0.5–0.8%). It hurt 9 of 14 items (sugar −28%, onion −21%, jaggery −18%, moong −13%).
- Official overlap: it worsened 13 of 14 items; only potato (+21%) and onion (+8%) improved. Eggs, which passed the reference test, worsened 2.2× on the official data.
- Reading: after the 12-month own-trend, month-of-year residuals in WFP data are mostly noise (single-market monthly quotes, reporting jumps), so a learned seasonal term adds variance. The apparent aggregate improvement (0.650 → 0.602 pp, potato-only, 1.3% weight, n = 11) is not credible and was not adopted.
- Caveats: WFP "Rice", "Wheat flour", "Oil (groundnut)" are generic grades, not the basket specs; WFP has no matching ghee, banana, brinjal or tur/chana dal series, so F003/F005/F007/F012/F024/F025 were not tested.

**Effect on the index:** none. Published Aug 107.666, Sep 108.885 (nowcast), Oct 109.413 (nowcast), independent share 38.5% — all unchanged.

## W. Seventeenth look (2026-10-02): DMart Ready Ahmedabad shelf prices WIRED for 17 packaged items

**Why it was missed before:** section S rejected DMart because Rajkot pincodes are not served (`isHDEnabled=false`) and the default store is Mumbai. The missing step was the pincode -> store lookup (`/v1/pincodes/search/380001` -> StoreId 10681 = Ahmedabad). Category listings for that store return every SKU with MRP and shelf price, so an Ahmedabad (Gujarat big-city) proxy is available, in the same class as NECC Ahmedabad eggs.

| Item | What was found |
|---|---|
| Endpoint | `https://digital.dmart.in/api/v3/plp/{categoryId}?page&size=40&channel=web&storeId=10681`; category ids from `/v1/categories/top?storeId=10681`. No robots.txt on the API host (404); www.dmart.in robots disallows only app/cart/pdp pages. |
| WAF | The *search* endpoint returned HTTP 403 after about 40 requests in a minute and stayed blocked for the rest of the session. Category listings were not blocked at 4 s spacing (24 requests). The collector uses 4 s spacing, about 25 requests per run, no retries, and stops on the first non-200. Nothing evades the WAF. |
| Pool | `data/dmart/pool.csv`: 66 mainstream SKUs, 2-5 per item, fixed on 2026-10-02 before any history existed (rules in `scripts/build_dmart_pool.py`). Price = shelf price (priceSALE); MRP kept as `regular_price`. |
| Items wired (plan weight 16.6%) | F007 cottonseed oil, F012 ghee, F014 tea, F015 salt, F016 turmeric, F017 biscuits, F018 noodles, F019 bread, H001 detergent, H002 dishwash, H003 LED bulb, H004 pressure cooker, M002 antiseptic liquid, E003 notebook, P001 soap, P002 shampoo, P003 toothpaste. |
| Not wired | F010 curd (only one in-stock curd SKU at selection). Clothing/footwear (DMart's range is private-label and not our fixed brand/style). |
| History | None exists: accrues forward from 2 Oct 2026. Earlier months keep the official stand-in; the splice month is imputed. So the Sep and Oct 2026 index levels are unchanged by this wiring (checked: 108.885 / 109.413). |
| Gate | Proxy gate (corr >= 0.5, drift <= 0.10 vs the official item index) applies after 6 overlapping months, so every DMart item is `pending` until about April 2027. Multi-SKU series are validated as a matched-model Jevons chain (`rpi/proxy_check.chain_series`). |
| Reachability | Sandbox: yes. GitHub-hosted runner: refused (HTTP 403, probe 2026-10-02), so the daily workflow logs `ingest:dmart_ahmedabad` as an error step and carries on; the series accrues when the pipeline is run from a network that can reach it. |
| Risks | (1) Ahmedabad is not Rajkot. (2) DMart's shelf price includes DMart's own discounting (e.g. LED bulb Rs45 against MRP Rs160), which is a real shelf price but moves independently of MRPs. (3) A WAF/ToS change can end the feed. The dmart.in terms of use were not reviewed in detail. (4) The official item indices are the yardstick and, for these items, the stand-in until the feed has history, so accuracy against MoSPI cannot be judged yet. |

**Independent share after this sweep (plan weight): 55.1%** = 18.0% direct (tariff/spot/PNG, not gated) + 12.8% gated and passing (DoCA, NECC, mandi) + 24.3% pending validation (DMart 16.6%, mandi 7.7%). Before: 38.5%. Observed-in-August share is unchanged at 29.6% because DMart starts in October.

Other leads probed this sweep and rejected: Open Prices (Open Food Facts price database): only 404 INR prices worldwide, none in Rajkot or Gujarat, and its country filter is ignored. Tyre makers' 2026 price rises: only blogs, no dated MRP list. JioFiber/Airtel broadband: blogs only (already in section K), no operator archive.

## X. Eighteenth look (2026-10-03): direct-source hunt; potato rewired to the Gujarat DoCA panel; delivery apps closed

**Wired.** F021 (potato) moved from two wholesale mandi quotes (Gondal, Rajkot Veg yard; short history, `pending`) to the DoCA **Gujarat-centres balanced panel** (`doca_gujarat`, `DocaGujaratCollector`). The rule was fixed before this sweep (geography hierarchy in `rpi/collectors/doca.py`: the most local panel that passes the gate wins) and `data/official/doca_panel_screen.csv` already said `wire_to=gujarat` for F021 (Rajkot centre fails; Gujarat panel corr 0.64, drift 0.035; all-India panel fails). Live gate result after the refresh: `validate:proxies` 11 pass, 22 pending, 0 fail. The 640 daily points start 2025-01-01, so the item is gated now rather than after six months of accrual. It is a Gujarat state retail panel, not a Rajkot price, so it stays in the proxy bucket. The old wholesale F021 feeds are kept as diagnostics (`rpi/superseded.py`). Weight moved: gated-and-passing 12.8 -> 14.1 points, pending 24.3 -> 23.0; plan independent share unchanged at 55.1%.

**Probed and closed (nothing wired).**
- Swiggy: the restaurant listing (`/dapi/restaurants/list/v5`) answers for Rajkot, but every menu endpoint returns an empty 202 or a 403 bot challenge. Menu prices (thali, snacks, tea) are therefore out of reach without evading the WAF, which this project does not do.
- Zomato: `robots.txt` says `Disallow: /` for all agents. Not used.
- PVR cinemas API (S001): 403 Access Denied.
- magicpin Rajkot: 404 on the city page; no menu data.
- Rajkot city bus (T003): only unofficial fare matrices (rmts.somee.com, a Scribd upload) and a 2023-09 BRTS hike; no dated 2025-26 revision, so there is no event to check and no series.
- Salon, photocopy, doctor-fee, thali and clothing price searches: no dated authoritative Rajkot series. Practo gives a current snapshot only.
- Gujarat DES retail prices (salt monthly, agricultural fortnightly): listed in MoSPI table 11.4, no reachable live feed found. CEIC mirrors of DoCA Rajkot atta, maida and sugar stop at March 2023.

**Conclusion.** The remaining uncovered weight (rent 19.67%, clothing about 7.35%, services such as haircuts, doctor fees, school fees and city bus fares) has no authentic direct dated source that can be scraped. The panel screen leaves F001, F004, F012, F014, F015, F016, F022, F023 and F025 failing all three DoCA panels.

## Y. Nineteenth look (2026-10-03): manufacturer e-store prices rebuilt from Wayback captures (CEAT tyres, T006) - near miss, not wired

**Idea.** Some manufacturers publish their own e-store prices as schema.org `Product` JSON-LD on public pages, and the Internet Archive holds dated captures of those pages. That gives a history without waiting months for accrual. CEAT (`ceat.com`, robots `Allow: /`, `llms.txt` allows crawlers) is the first such source found for T006 (two-wheeler tyre, official item "Tyres and tubes", weight 1.60%).

**What was built.** `scripts/ceat_cdx.py` lists captures (193 model pages, 620 captures, one per page per month, Jul 2025 - Sep 2026). `scripts/ceat_fetch.py` reads them from the Archive (4 parallel requests, about 3 minutes) and parses the JSON-LD. Result: 1,809 SKU-price rows, 141 distinct SKUs, 13.5% listed at price 0 (excluded). Captures before about Sep 2025 carry no JSON-LD prices, so history starts Sep 2025. Only 1.1% of SKU-months have conflicting prices inside a month. `scripts/ceat_screen.py` chains the SKUs (matched-model Jevons, `rpi.proxy_check.chain_series`) and applies the unchanged gate. Rules were fixed before the verdict was seen. Data: `data/ceat/`, result: `data/official/ceat_tyre_screen.csv`.

| Month | CEAT chain | Official tyres (rebased) |
|---|---|---|
| 2025-09 | 100.0 | 100.0 |
| 2025-11 | 96.6 | 99.5 |
| 2026-03 | 96.6 | 98.8 |
| 2026-05 | 99.4 | 99.7 |
| 2026-07 | 103.8 | 102.1 |
| 2026-08 | 103.8 | 102.7 |

**Verdict: FAIL (corr 0.46 against the 0.5 threshold, drift 0.011 against the 0.10 limit, 12 overlapping months).** The level agrees closely (drift 1.1%) and the shape is right: both show the September 2025 GST-cut dip and the 2026 rise. The correlation of monthly changes misses because the Archive captures are sparse, so CEAT's chain moves in a few steps while the official series moves a little every month. The threshold was not tuned and the series is not wired. T006 stays on the official stand-in.

**Why this is worth keeping.** (1) It shows the Wayback + JSON-LD route works for manufacturers that publish prices in markup. (2) A live CEAT feed, polled monthly, would remove the sparse-capture problem and could be re-gated after about six months. That would be a fixed-pool national e-store price, so it would sit in the proxy bucket, not a Rajkot price. It is not built yet.

**Probed and closed this sweep.** Urban Company (robots: "crawling prohibited unless express written permission"), TyrePlex (robots `Disallow: /*`), Swiggy menus (bot challenge), Zomato (robots disallow). MRF and Apollo Tyres allow crawling but were not checked for price markup.

## Z. Twentieth look (2026-10-03): CEAT live accrual built; footwear brands and Amul curd tested

**1. CEAT live accrual (built, diagnostic).** `rpi/collectors/ceat_tyres.py`, refresh step `screen:ceat_tyres`. A fixed pool (`data/ceat/pool.csv`, rule in `scripts/build_ceat_pool.py`: SKUs listed in at least 6 of the archive months) of 47 SKUs on 12 pages is read live at 2 s spacing (robots allow it) and appended to `data/ceat/live_prices.csv`. The gate then runs on archive history with live months replacing the archive quote for the same month. First live quote (2026-10-03): 47 of 47 SKUs. Matched SKUs are up about 2.8% on August and about 8.0% on June (official tyres index: roughly +1.7% from June to August), so the live feed shows the post-August rise that the archive could not. Gate today: **fail, corr 0.46, drift 0.011, 12 months** (unchanged: the live month is beyond the official index, which ends in August 2026). The step logs the verdict every run; it is not wired and T006 stays on the official stand-in. Re-gate when the September and October official indices arrive (mid-Oct and mid-Nov): the extra months will use live quotes.

**2. Other manufacturers on the same archive + JSON-LD route.** `scripts/brand_wayback.py` (rules fixed beforehand: men's footwear slugs, URLs with captures in at least 5 months, first 200 by months, one capture per URL-month, unchanged gate against "Footwear for men", C003).

| Source | Robots | Archive history | Verdict |
|---|---|---|---|
| Campus (`campusshoes.com`, Shopify) | allow | 71 men's product URLs, 363 captures, but 1-2 captures in Jan and Feb 2026 | **fail**: corr -0.07, drift 0.132, only 9 usable months. Selling prices drift up (+12% over the year, promotion-driven) while the official men's footwear index is down 1.7%. |
| Bata India (`bata.com/in`) | allow | only 5 men's URLs with 5+ months; JSON-LD price is a flat list price (Rs 1,499 in every capture) | **fail** (no variation; correlation undefined, drift 0.017). Uninformative. |
| Woodland | allow | not tested (large archive, JS-heavy pages) | open |
| Amul shop (`shop.amul.com`, F010 curd) | allow product pages | live product API answers 401 without a session token that the page script generates; only a handful of archived API responses | **closed**: using it would mean reproducing the site's token logic, which is evasion. No history to gate. |
| Mother Dairy | allow | 6 archive captures | closed |

Both footwear screens are saved as `data/official/campus_footwear_screen.csv` and `bata_footwear_screen.csv` (raw prices in `data/brands/`). C003 stays on the official stand-in.

**What this tells us.** The route works where a manufacturer lists a stable price in markup and the archive has monthly captures (CEAT). It fails for retailers whose price is a promotion-driven selling price (Campus) or a never-changing list price (Bata, Jockey earlier). Clothing and footwear remain without an authentic direct source.
