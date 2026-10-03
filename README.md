# Rajkot Price Index (RPI) - foundations v0.1

An independent, auto-updating, open-method city price index. This repo is the **foundation**:
warehouse, collectors framework, index engine, validation, health monitoring, static publishing, tests.

```bash
pip install -r requirements.txt
python -m pytest -q          # 20 tests, incl. an end-to-end "does it recover the true index?" test
python -m rpi demo           # synthetic end-to-end run -> docs_demo/index.html (watermarked DEMO)
python -m rpi init           # real DB: load basket + weights + official series
python -m rpi daily          # collect -> build -> health -> publish
```

## Architecture
```
collectors (API / HTTP / tariff events / CSV)
   -> raw snapshots (content-addressed, immutable)  -> SQLite warehouse (products, observations)
   -> panel (monthly geometric-mean price per quote = SKU x pincode, on UNIT prices)
   -> elementary: matched-model Jevons (+ GEKS-Jevons, regular-price variants as robustness)
   -> impute missing item RELATIVES from the item's own 12-month mean drift (`impute = "own_trend"`; division peers only when an item has <3 observed months), flagged, Young fixed-weight aggregation
   -> bootstrap CI over quotes -> immutable index vintages
   -> validation vs official series, nowcast scoring -> static site / CSV / JSON / bulletin
```

## Design decisions worth defending
- **Unit prices** (per kg / L / piece): pack-size changes surface as price changes (shrinkflation).
- **Matched-model Jevons** on quotes observed in both months: robust to SKU churn and stock-outs.
- **Relatives, not levels, are imputed**, so missing data never causes jumps in the chain.
- **Per-tier minimum quotes**: administered prices (tier C) legitimately have a single quote.
  (A test caught this: with a global minimum of 2, every tariff item was silently imputed.)
- **Coverage is a first-class output**: share of CPI weight directly observed is published every month.
- **Demo guard**: demo weights / synthetic sources cannot be published without an explicit `--demo` flag
  and a red watermark.
- **Immutable vintages**: every build stores a new run_id; nothing is overwritten.
- **Polite scraping**: robots.txt, rate limits, honest User-Agent; no evasion of bot protection.

## Status honesty (read this) - updated 2026-10-02

**One command updates everything:** `python -m rpi refresh` (daily via GitHub Actions cron 10:30 IST, or `scripts/cron_example.txt`).
Each source step is isolated, logged to `data/refresh_log.csv` and `docs/data/status.json`; `--offline` rebuilds from local data.

| Component | State | Evidence |
|---|---|---|
| Engine, DB, publishing, tests | works end-to-end | 52 tests pass; synthetic demo recovers truth to <0.75 pts |
| **MoSPI CPI-2024 Gujarat urban** (official benchmark) | **real, auto-refreshed** (checks `totalRecords`, re-fetches only on change) | `data/official/mospi_cpi2024_gujarat_urban.csv` |
| **Labour Bureau CPI-IW Rajkot** | **real, auto-discovered monthly letter** (benchmark only) | Jul 146.0, Aug 146.2 |
| **Petrol, diesel (T001/T002)** | **real daily, auto-refreshed**, one aggregator feed (goodreturns = India Today feed) with outlier screening; cross-checked vs official index | `data/tariff_events.csv` rows with status `scraped` |
| **LPG (R003)** | real monthly (858 -> 918 -> 947), auto-refreshed | goodreturns table + press-reported steps |
| **Gold 22K, silver (P005/P006)** | real daily (Rs/g), auto-refreshed from Sep 2026 | goodreturns; secondary |
| **Potato, onion, tomato, banana, brinjal (F021-F025)** | real wholesale modal price, Gondal veg market (Rajkot district, not Rajkot city), ~7-day lag | commodityonline (Agmarknet republication); secondary |
| **Electricity (R002)** | **independent, modelled**: GERC slabs + a curated FPPAS register (govt release + 2+ outlets) -> 200 kWh bill; 3.35 -> 2.85 -> 2.45 -> 2.30 (Jul 2025) -> 2.45 + 3.99% variable (Jul 2026) | `data/fppas_schedule.csv`, `rpi/electricity.py`. Aggregators' Rs2.70 / Rs3.30 were **rejected**. Model agrees with the official index on the Jul 2025 cut (-2.4% vs -0.5%); the Jul 2026 hike (+6.5%) is **not yet in the official series** |
| **Milk (F009)** | independent: Amul Gold 500ml Gujarat steps 33 -> 34 (1 May 2025) -> 35 (14 May 2026) | tracks official Milk:liquid index (106.1 vs 106.3 by Aug 2026) |
| **PNG (R005)** | independent, monthly (49.02 Dec 2025-Aug 2026, 53.22 from 3 Sep 2026 via `data/png_events.csv` overlay); earlier months imputed | goodreturns (lags) + 5-outlet press-verified revision |
| **Eggs (F020)** | NECC wholesale, Ahmedabad zone, daily (30-day window; official item back-fills before) | eggratelab; not a Rajkot price |
| **Official-linked stand-ins** (52 items = 80.0% of weight, plus back-fill of 8 items before their feeds began) | **NOT independent** - the MoSPI item index is fed in as the item's price relative | `data/source_plan.csv`; flagged `official_link` |
| Weights | **APPROXIMATE, official-derived**, then price-updated to the base month | MoSPI publishes no Gujarat item weights |
| Water, bus, auto, telecom, broadband, OTT, school/tuition fees, rent, staple grains/pulses/oils, packaged goods | no independent source reachable | official-linked. Mandi grain pages are behind Cloudflare; RMC water hike (Rs1,500 -> 2,400) was only proposed; no telecom revision found after Jul 2024 |
| 1.6% of weight (T005) | no data at all | imputed from division peers |
| **Index headline** | **experimental hybrid** | ~32.7% of weight independent (see sweep sections), ~66% official-linked. Months after the last official month are a **nowcast** driven by ~12% of weight. Bootstrap CI is **not shown** (single-quote items have no sampling variance) |

Agreement with official is **partly circular** (84% of the basket is the official data). The honest independent test is how the independently collected items (fuel, LPG, metals, mandi) behave against their official counterparts; see `data/official/audit_report.md`.

Known gap: RPI reference month (Aug 2026) reads ~+0.6pp above the official Gujarat-urban figure in level terms (YoY 5.3% vs 4.7%), consistent with the basket/weight error measured by the audit (RMSE 0.47).

Curated registers (electricity FPPAS, milk, LPG) are not scraped, so every refresh runs a **staleness alarm** (`rpi/registry.py`): if the newest entry is older than its normal revision cycle the refresh step errors visibly.

Rejected data: billcalculator-type FPPAS figures (Rs2.70/3.30); mypetrolprice petrol Rs115.01 (official index and other sources contradict it). Unverified: diesel Rs100.10.
Not written on purpose: BigBasket/Blinkit/Zepto-type scrapers (ToS/robots risk).

## Next steps (suggested order)
1. **You, from your own network:** `python -m rpi probe`, then register a free data.gov.in key (`DATA_GOV_API_KEY`) and run `ingest agmarknet`; fix field/commodity-name mismatches. This unlocks Tier A/B produce (~25% of basket weight).
2. Source a primary FPPPA + electricity-duty notice (GUVNL/PGVCL) -> electricity; RMC water bill; GSRTC/RMC bus fare; telecom tariff pages; school fee committee order.
3. **Rent (19.7% of weight):** MoSPI rent index is the only official proxy; build a listings-based hedonic index (ToS review first) or use HCES-calibrated rent from the official item index as an explicit, flagged stand-in.
4. Automate monthly refresh of the MoSPI series (`make official`) and Labour Bureau Rajkot CPI-IW; load older Labour Bureau letters.
5. Tighten weights: HCES 2023-24 unit-level data to replace the equal split within groups.
6. First retail adapter (ToS-reviewed) with parser contract tests + canary alerts; SKU matching queue; offline calibration panel.

## Why independent weight is 18.4% (and not 40%)
See `data/official/coverage_ceiling.md` (generated by `scripts/coverage_ceiling.py`). Every non-independent item is mapped to the concrete blocker
found when probing. No automatable, permitted, real feed remains for any block >2%; 40% needs self-collected data (rent survey alone: ~38%).
- 2026-10-02 sweep: see data/official/source_inventory_2026-10-02.md

## Independent share after the 2026-10-02 wiring: 23.5% (was 18.4%)
- New feeds: `mandi_rajkot_apmc` (wheat/arhar/moong/chana -> F001/F003/F004/F005) and `mandi_rajkot_veg` (potato/onion/tomato/brinjal, second quote).
  Both are AgMarkNet republished by acrop.app (robots allow), wholesale proxies, validated against the official item index once 6 months overlap
  (`rpi/proxy_check.py`; status in `docs/data/status.json -> proxy_validation`; currently 10 items pending).
- Plan share 23.5% = direct 10.7% (tariffs, spot metals, PNG) + proxy 12.8% (mandi, NECC). Share actually observed in the Aug-2026 reference
  month is still 9.4%, because the new feeds only start in Sep 2026; it grows as history accumulates.
- Rules added: official stand-ins are cut off where an independent feed starts; daily feeds need >=5 days in a month to count (`[index.min_days_by_source]`).
- Run `python3 scripts/coverage_ceiling.py` for what still blocks the rest.


## Independent share after the second sweep: 25.7%

Plan weight now: **independent 25.7%** (direct administered/spot 12.9, proxy 12.8), linked 72.7%, none 1.6%. Added: RMC water (R004), Jio+Airtel prepaid (K001),
JioHotstar+Prime (S002) as registers in `data/tariff_events.csv` (new optional `series` column = parallel SKUs per item; script `scripts/add_admin_registers.py`),
and a named-variety chana series from the Rajkot yard board (F005). `rpi/crosscheck.py` cross-checks acrop against that board on every refresh.
Rejected: commoditiescontrol (ToS forbids scraping), NCDEX (bot-challenge). Details: `data/official/source_inventory_2026-10-02.md` section F.
Caveat: the audit shows K001 (+5.1% vs official +1.6%) and S002 (+8.3% vs +2.0%) running above the thin-sample official item indices; they are list-price changes seen by new subscribers.


## Third sweep: more yards, more cross-checks (independent share unchanged at 25.7%)

No new weight was added: this sweep improved *accuracy* of existing independent items. Staples (F001/F003/F004/F005) now average four Rajkot-district yards
(Rajkot, Gondal, Jetpur, Jasdan; `mandi_rajkot_district`), and every refresh cross-checks the Rajkot and Gondal modals against the yards' own boards
(`rpi/crosscheck.py`). Not adopted, with reasons: BankBazaar (same upstream as goodreturns / glitchy fuel), Gujarati-news oil boards (event-driven),
Apple India (launch-cycle price cuts). Details: `data/official/source_inventory_2026-10-02.md` section G.


## Fourth sweep: IBJA gold/silver cross-check (independent share unchanged at 25.7%)

A new refresh step, `crosscheck:ibja`, compares goodreturns Rajkot gold 22K (P005) and silver (P006) with the IBJA benchmark published at ibjarates.com. It is a different publisher, so agreement is real corroboration, but IBJA is national and ex-GST, so the check uses pre-set bands (gold +/-3%, silver +/-10%, weak) and never feeds the index. Three further leads (Gujarat FRC school-fee orders, Amul butter/ghee MRP, the Sep 2026 Gujarat Gas PNG hike) are documented in `data/official/source_inventory_2026-10-02.md` section H with the exact reason each is not wired yet.


## Sixth sweep: a stale source caught, a nowcast flaw fixed (independent share unchanged at 25.7%)

* **PNG (R005) was stale.** Gujarat Gas raised domestic PNG on 3 Sep 2026 to Rs 53.22/SCM (tax-incl.), but goodreturns still showed 49.02 on 2 Oct. The
  outlets disagree on the size (+1.19 / +4.20 / +6.53); only +4.20 is consistent on a tax-inclusive basis (46.69 pre-tax x 1.05 = 49.02; 49.02 + 4.20 =
  53.22). `data/png_events.csv` now overlays the revision, but only while goodreturns still shows the pre-event price (`apply_png_events`), so the
  overlay retires itself when the aggregator catches up. A staleness alarm (`registry.review`, R005, 400 d) covers the register.
* **Nowcast flaw found by that change.** Months with no official index (Sep, Oct) imputed unobserved items from division peers, so a single PNG step
  leaked into rent and moved the total by about +0.9 pt. Imputation is now the item's own 12-month mean drift. Back-test on the 20 months of official
  Gujarat-urban item indices (one-month-ahead): total RMSE 0.63 pp (own 12-month mean) vs 0.74 pp (zero change) vs 0.74 pp (3-month median); short
  trend windows are worse at item level (4.5 vs 3.6 pp). Set `impute = "division"` in `config/settings.toml` to reproduce the old behaviour.
* **Wired as a proxy: Rajkot cutting chai (D002).** The Rajkot District Tea Hotel Association's rate card moved half Rs 13 -> Rs 15 (full Rs 26 -> Rs 30) on 1 Sep 2026,
  reported by five outlets. Press disagrees on the prior level (10 / 12 / 13), so only the association's own quoted figure (13 -> 15, **+15.4%**) is used, a lower bound.
  A +50% reading (10 -> 15) is *not* used; it would add about 0.6 index points at 2026-09. It is a trade-association rate card, not an observed paid price, so it sits in the
  PROXY bucket with an event check against MoSPI "Tea: cups" for Sep 2026 (due mid-Oct). See `scripts/add_chai_register.py`, `data/tariff_events.csv`, inventory section Q.
* **Thirteenth look: four more national-panel items (F003 tur dal, F005 chana dal, F020 eggs, F024 banana).** They already counted as independent, but via short local
  wholesale feeds (Rajkot/Gondal yards, NECC, about 1 month of history) that could not be gated (proxy_validation said `pending`). The DoCA all-India retail panel has 22 months and
  passes the gate (corr 0.91 / 0.86 / 0.89 / 0.59, drift <= 0.06), so it is now the primary series (PROXY bucket). The local feeds keep accruing as diagnostics but are excluded from the
  index, the gate and the cut-offs (`rpi/superseded.py`). Plan share is unchanged at 38.5%; the *observed* independent weight in the Aug 2026 reference month rose 24.4% -> 29.6%
  and gated proxies went from 6 to 10 passes. The panel is national retail, not Rajkot wholesale; that trade-off is stated in `data/source_plan.csv`.
* **Fifteenth look: new official, retailer and association sources.** WPI (latest file June 2026, older than the CPI we hold), DMart Ready (does not serve Rajkot), JioMart (Akamai), e-NAM (needs a session) and others were probed; none can be wired. Telecom and OTT already carry the 2026 revisions. Details: section S of the inventory.
* **Sugar flag.** The official Gujarat-urban sugar index rose +17.3% in Aug 2026; Rajkot press reports a larger retail move (48->68 or 50->75 per kg
  over about three months). Disputed, recorded, not adjusted.

## Seventh sweep: a bug in the robustness variant, a regulated series, an official local benchmark, a back-tested nowcast band (independent share 25.7% -> 27.3%)

* **Bug found and fixed (GEKS).** The published `geks_jevons` total (103.99 for 2026-10) was an artefact, not a drift signal. Register events dated before
  the base month stretched the panel; period 0 then held only electricity quotes, so `geks_rel` returned NaN for most items and nearly everything was
  imputed. `geks_rel` now starts at the first period with any quote, the engine clips pre-base quotes, and a regression test covers it. After the fix
  GEKS-Jevons (108.56) matches the chain (108.57) as theory says it must for single-SKU items. Headline is unaffected.
* **M001 (paracetamol 500 mg) wired from the NPPA ceiling price** (ex-GST 0.92 from 1.4.2025, 0.93 from 1.4.2026; GST 12% -> 5% on 22 Sep 2025).
  A ceiling is a cap, not a shelf price, so it is counted in the PROXY bucket of the independent share, not the direct one
  (`PROXY_ITEMS`). Independent share is now **27.3%** (direct 12.9%, proxy 14.5%). It moves the Aug 2026 reference index from 107.60 to **107.46**:
  the official Medicine index rose while the regulated ceiling fell with the GST cut.
* **CPI-IW centre table (benchmark only).** The Labour Bureau home page lists the last two months for every Gujarat centre. Daily refreshes now accrue
  `data/official/cpi_iw_gujarat_centres.csv` (back-filled 2025-05..2026-08 from Wayback). `status.json:benchmarks` reports that Rajkot CPI-IW YoY is
  +3.54% (Aug 2026) vs RPI +5.34% vs MoSPI Gujarat-urban +4.68%; Rajkot rose least of the five centres. Month-on-month correlation of the RPI with
  CPI-IW Rajkot is only 0.16 (n = 13; MoSPI Gujarat vs CPI-IW 0.51), because the RPI carries gold/silver and other series CPI-IW dampens. It never feeds the index.
* **Event checks** (`data/official/event_checks.csv`): the official-linked Butter, Ghee and Medicine indices fell only 46% / 46% / 13% as much as the verified
  Amul and NPPA cuts of 22 Sep 2025. Diagnostic: official stand-ins can under-react when one dominant brand moves.
* **Nowcast evaluation** (`rpi/nowcast_eval.py`, step `evaluate:nowcast`, output `data/official/nowcast_backtest.json`): rolling-origin back-test on 66
  official item series. One-step total RMSE: own-trend 0.65 pp, zero-change 0.77, old division peer-fill 0.78-1.15 (the gap narrows as more items are observed). With independent items observed exactly
  the floor is 0.24 pp (optimistic). A distribution-free **split-conformal 90% band** from the conservative rule is published as `nowcast_lo/nowcast_hi`
  (+/-1.23% at one month, +/-2.09% at two; n = 11 and 10) and a **vintage log** (`data/nowcast_vintages.csv`) scores every nowcast against the official
  release when it arrives, replacing the back-test with a real-time record over time.
* **Tried and rejected:** cross-sectional peer deviation (beta 0.25-1.0), division bridges, seasonal-naive blend (n = 7), all worse or unsupported in the back-test.

## Eighth sweep: government retail quotes for Rajkot (independent share 27.3% -> 31.2%)

* **New source: DoCA daily retail prices at the Rajkot centre** (`rpi/collectors/doca.py`). The Department of Consumer Affairs collects daily retail prices of ~40
  essentials in 555+ centres; Rajkot is one. DoCA's own site only serves centre data behind a CAPTCHA (not bypassed), but a civic project, cpi.reclaimchennai.city,
  republishes the same feed through an open API with history back to 2009. Because it is a third party, **every refresh first proves it faithful**: all 41
  all-India averages must equal the ones DoCA prints on its own home page for the same date (they do, 41/41), otherwise the DoCA feed is skipped for that run.
* **Gate, not trust.** The quotes are whole-rupee reports of a standard local variety, unchanged on 70-99% of days. Each item is gated against its official
  Gujarat-urban item index (correlation of monthly changes >= 0.5 and cumulative drift <= 10 points, the same rule as the mandi proxies, 20 overlapping months):
  **groundnut oil (F006), sugar (F013) and gur (F026) pass and are wired** (3.8% of weight, shown as a separate "retail quotes" bucket). The other 17 fail and
  are only screened every run (`status.json:doca_screen`; an item that starts passing is reported as eligible, never auto-promoted): atta +24.7% vs official +1.4%,
  tur -27% vs -14%, sunflower oil +33% vs +15%, potato, tomato, brinjal and the flat items (salt, tea, turmeric, ghee, butter, rice) mostly fail on correlation.
* **Effect.** Sugar is the one that matters: Rajkot's retail sugar went from 42 (Jun 2026) to 58.7 (Sep 2026), so the nowcast now carries a +13.7% sugar move for
  Sep (official data end in Aug) instead of the item's own trend. Aug 2026 reference 107.46 -> 107.34, Sep 108.07 -> 108.15, Oct 108.58 -> 108.67.
* **Bug caught on the way.** A new primary source missing from `SINGLE_SERIES_SOURCES` makes tier-A items need two quotes, so one-quote items were silently imputed
  (sugar and groundnut oil read identically as a division mean). A test now fails if any planned source is missing from that list.

## Ninth sweep: the Gujarat auto-rickshaw tariff (independent share 31.2% -> 32.7%)

* **What was found.** The Gujarat Ports & Transport Dept notified new auto-rickshaw fares under Motor Vehicles Act s.67, effective **7 Aug 2026**, cancelling the
  June-2022 notification (Gujarat Samachar 7 Aug; ABP Asmita, GSTV, News18 Gujarati 8 Aug). Urban day tariff: minimum Rs20 -> Rs25 for the first 1.2 km, then Rs15 -> Rs20/km
  (Rs3 -> Rs4 per 200 m). The 2022 level is a verified baseline: PTI/Goodreturns 8 Jun 2022, and every 2026 article says about three years without a hike.
* **How it is wired (T004, weight 1.51).** A register (`scripts/add_autorickshaw_register.py` -> `data/tariff_events.csv`) of a FIXED 3 km trip: Rs47 -> Rs61 (+29.8%).
  The trip length barely matters (2 km +28.1%, 5 km +31.2%). Night surcharge, waiting and out-of-city fares are not modelled. Registry alarm 900 days.
* **It is counted as PROXY, not direct,** because a notified fare is a legal maximum, not an observed paid fare (many Rajkot autos are unmetered and bargain).
* **Effect on the index (honest).** August is a blend (6 old days, 25 new days), so T004 is 124.0 in Aug and 129.8 from Sep. The total moves +0.36 (Aug), +0.47 (Sep) and
  +0.46 (Oct) points: Aug 107.34 -> 107.70, Sep 108.15 -> 108.61, Oct 108.67 -> 109.13. Jan-Jul fall by 0.02-0.07 because the official stand-in had crept +3% (probably
  informal fare rises after the May-2026 fuel hikes) while the tariff was flat.
* **The open risk.** The official Gujarat-urban auto index rose only +0.2% Jul -> Aug 2026. If actual Rajkot fares move less than the legal tariff, T004 overstates the
  step. `check:regulatory_events` now carries a T004 row that compares the official Sep-2026 index (published mid-Oct) with the +29.8% tariff step. If the result is
  `official_muted`, downgrade T004 back to official-linked (one line in `source_plan.csv`) or add a pass-through assumption; do not leave it unexamined.
* **Also looked at and NOT wired:** Airtel's own page (fetched rendered, 2 Oct 2026) shows the entry Xstream plan at Rs499 + GST, 40 Mbps, matching the Sep-2023 launch,
  but the page is client-rendered, has no archived price, and cannot be collected at run time, so K003 stays official-linked. The Rajkot city-bus fare has no primary
  source (only a third-party calculator and a Scribd copy), so T003 stays official-linked. The daily workflow now commits every `data/*.csv` (it previously missed `nowcast_vintages.csv`).

## Ninth sweep, part 2: clothing and rent (independent share unchanged at 32.7%)

* **Clothing (C001, C002) - screened, NOT wired.** Pool: every men's T-shirt/polo/track-pant/short on jockey.in that existed before Nov 2024 and has an Internet Archive snapshot
  in Nov 2024-Mar 2025 (115 candidates, size M; prices are one all-India list price). Jan-2025 prices come from dated Wayback snapshots (`scripts/build_mrp_history.py`),
  today's from the live product JSON, change dates at the midpoint of the bracket between observations (status `derived`). Gate (same rule as mandi/DoCA proxies) on the partial
  pool processed so far (25 / 13 SKUs): C001 corr -0.45, drift 4.2 pp; C002 corr 0.20, drift 7.1 pp = **fail**. Jockey list prices moved +0.4% / -1.4% since Jan 2025 while the official
  Gujarat-urban men's clothing indices rose ~5-6%: the official index tracks mostly unbranded garments, a branded list price does not represent it. The daily refresh keeps screening it
  (`screen:jockey_mrp`) and appends exact-dated price changes to the quarantine file `data/mrp/jockey_events.csv`; promotion into the index is manual (`build_mrp_register.py --promote`) and refused unless the gate passes.
  Footwear (C003) was not attempted: the brand web stores show discount-driven, variant-specific prices.
* **Rent (R001, 19.67%) - no authentic independent series exists that I could reach; stays official-linked.** The Archive holds no rent-listing history (only Feb/May 2026 captures of detail pages and two
  captures of the list page), and 99acres/Housing/Square Yards/NoBroker are blocked. What IS reachable: MagicBricks' public list pages (robots.txt allows them) carry ~30-50 JSON-LD listings each, with the
  listing's own start date. `rpi/collectors/rent_listings.py` now reads five pages (flats, houses, 1/2/3 BHK) every refresh into `data/rent_listings.csv` and reports junk-screened monthly statistics.
  First harvest: 125 listings, posted Jul-Oct 2026. **Why it cannot carry weight:** Aug -> Sep median rent per sq ft 18.5 (90% bootstrap CI 16.6-21.0) -> 17.9 (15.0-20.6), 3 BHK median +17%, 2 BHK +1%:
  the sampling noise (+-12%) is ~50x the monthly movement of the official rent index (~0.2%); asking rents of still-unlet flats are a flow, not the tenancy stock the CPI measures; there is no history before Jul 2026
  and the official overlap is 2 months (gate needs 6). Kept as a diagnostic that accrues; it becomes screenable by ~Feb 2027. A primary rent survey remains the only route to an independent R001.


## Eleventh sweep: an all-India DoCA retail panel (independent share 32.7% -> 36.5%)

The Rajkot-centre DoCA quotes are one sticky reporter, and 17 of 20 failed the gate. The same DoCA feed has ~500 centres. The panel rule was fixed before looking at any verdict: take the centres with a quote on every day since 2025-01-01 (balanced panel, so entering/leaving centres cannot move the index) and form the daily Jevons mean. Wiring rule: the most local panel that passes the unchanged gate wins (Rajkot centre, then Gujarat centres, then all-India).

- **Wired (proxy bucket, not "direct"):** F002 rice (corr 0.69, drift 0.014), F008 sunflower oil (0.75, 0.037), F011 butter (0.66, 0.008). The Rajkot centre and the Gujarat panel fail the gate for all three. It is a national retail panel, not a Rajkot price and not our fixed brand, which is why it sits with the proxies. `validate:proxies` re-gates it every refresh (now 6 pass / 10 pending / 0 fail). Published index moved by +0.07 to +0.10 points (Aug 107.771, Sep 108.711, Oct 109.237).
- **Correction:** an earlier draft of this sweep reported that a Gujarat-wide panel passed only 2 of 20. That came from the mirror API's default 400-day window, which silently truncated the history. With `limit=1200` the picture is the table in `data/official/doca_panel_screen.csv`.
- **Screened and not wired:** F012 ghee, F014 tea, F015 salt, F016 turmeric (all-India panel fails; re-screened each refresh by `screen:doca_national`). F003, F005, F020, F024 also pass nationally but already have a mandi/NECC proxy, so they were not switched.
- **Crompton 9 W LED bulb (H003):** an accruing diagnostic only (`data/mrp_diary.csv`): Rs150 on archived pages in Aug and Oct 2025 and today, but no verifiable Jan-2025 baseline, and a flat series cannot pass the gate.
- **Rejected after inspection:** Orient Electric (list-vs-compare gaps of 40-70%), Himalaya (inconsistent pack prices), 14 other brand sites (no public feed or JS-only), amul.com info pages (no prices), AIIMS Rajkot fees (Rs10, subsidised). School-fee, thali and CPI-IW housing leads are in section O of `data/official/source_inventory_2026-10-02.md`.

### Twelfth look: nothing new passed (independent share unchanged at 36.5%)

A further sweep of brand stores, open price trackers and Rajkot administered-price news found no new series that clears the bar. The brand-store diary now also accrues Bajaj Electricals 9 W LED and 3 L pressure cookers (list prices, no discounts; diagnostic only because Wayback has nothing before Apr 2025). The Rajkot chai step (D002) was re-checked; it was later wired as a conservative proxy (+15.4%, see the thirteenth note). Details: section P of `data/official/source_inventory_2026-10-02.md`.


## Deployment (GitHub Actions)

* `daily.yml` refreshes every source and commits `data/` and `docs/` daily (10:30 IST) or on demand (Actions -> rpi-refresh -> Run workflow). `ci.yml` runs the tests on code changes.
  `probe.yml` (manual) prints which data hosts answer from the runner.
* **Network caveat, measured 2026-10-02 from a GitHub-hosted runner (Phoenix, US, Azure):** `cpi.reclaimchennai.city` (the DoCA mirror) returns **403**, and Labour Bureau and the
  MoSPI API do not answer. On the hosted runner the DoCA-fed items (F002, F003, F005, F006, F008, F011, F013, F020, F024, F026) and the CPI-IW benchmark therefore do not refresh; the run logs the error
  and keeps the last good data instead of faking it. PPAC, IBJA, acrop, goodreturns, Divya Bhaskar and fcainfoweb answer normally.
* **Fix:** register a self-hosted runner on a machine with an Indian IP (Settings -> Actions -> Runners -> New self-hosted runner), then set the repository variable
  `RPI_RUNNER` to `self-hosted` (Settings -> Secrets and variables -> Actions -> Variables). No code change needed.
* Raw HTTP snapshots (`data/sources_raw/`, `data/raw/`) are git-ignored; everything the index needs is in `data/` and `docs/`.

- **Historical reference back-test (sweep 16c):** WFP/HDX Rajkot retail (2010–2023) and NECC Ahmedabad eggs (2009–2026) are stored under `data/reference/` as reference-only data. A pre-registered test of a seasonal term for the nowcast (`scripts/seasonal_backtest.py`) found no item that met the bar, so nowcasts stay `own_trend`. See inventory section V.
- **Replay back-test (`python3 scripts/replay_backtest.py`):** reruns the production engine for past cut-offs with the official-linked data hidden after each one, then compares the nowcast with the index later published and with the MoSPI Gujarat-urban general index. Output: `data/official/replay_backtest.md` / `.csv`.
- **DMart Ahmedabad shelf prices (sweep 17, `rpi/collectors/dmart.py`):** 17 packaged items (tea, salt, ghee, biscuits, noodles, detergent, soap, shampoo, toothpaste, antiseptic and others) now have a fixed SKU pool priced from DMart Ready's Ahmedabad store, with MRP kept as the regular price. This is an Ahmedabad proxy, not Rajkot. It accrues forward only and stays `pending` against the proxy gate until 6 months overlap with the official index. Plan independent share 55.1%, of which 24.3 points are pending. See inventory section W.
- **Potato on the Gujarat DoCA panel (sweep 18, `DocaGujaratCollector`):** F021 now uses the balanced panel of DoCA retail quotes from the Gujarat centres, because the Rajkot centre fails the gate and the Gujarat panel passes it (corr 0.64, drift 0.035). It replaces two short wholesale feeds, is gated immediately (11 pass, 22 pending) and stays a Gujarat proxy, not a Rajkot price. Swiggy menus (WAF), Zomato (robots disallow) and PVR (403) were probed and closed. See inventory section X.
- **CEAT tyre prices from Wayback captures (sweep 19, `scripts/ceat_*.py`):** a history of 141 SKUs of CEAT's own e-store prices was rebuilt from archived JSON-LD (Sep 2025 - Aug 2026) and gated against the official tyres index. Verdict: fail on a near miss (corr 0.46, drift 0.011), so T006 stays on the official stand-in. Details: inventory section Y.
- **CEAT live accrual and footwear brands (sweep 20, `rpi/collectors/ceat_tyres.py`, `scripts/brand_wayback.py`):** every refresh now reads CEAT's 47-SKU pool live and re-gates the tyre series (T006: still fail, corr 0.46, drift 0.011, diagnostic only). Campus and Bata footwear histories rebuilt from the Internet Archive both fail the gate; Amul shop needs a session token and was closed. See inventory section Z.
