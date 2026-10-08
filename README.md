# Rajkot Price Index (RPI)

An independent, auto-updating, open-method consumer price index for Rajkot city, built to be checked against the official MoSPI CPI (Gujarat urban) rather than copied from it.
Everything the index uses is in this repo: collectors, a warehouse, the index engine, validation gates, health monitoring, a static site (`docs/`, GitHub Pages) and tests.

**Status: experimental.** The headline mixes observed prices, gated proxies and one modelled series (rent). Read "Current status" below before quoting a number.

```bash
pip install -r requirements.txt
python -m pytest -q            # 207 tests (one skips without pdfplumber), incl. an end-to-end "does it recover the true index?" test
python -m rpi refresh          # collect every source -> gate -> build -> audit -> publish (docs/)
python -m rpi refresh --offline   # rebuild from data already in the repo (no network)
python -m rpi demo             # synthetic run -> docs_demo/index.html (watermarked DEMO)
python -m rpi probe            # which data hosts answer from this machine
```

## Architecture
```
collectors (API / HTTP / tariff events / CSV / model)
   -> raw snapshots (content-addressed, immutable)  -> SQLite warehouse (products, observations)
   -> panel (monthly geometric-mean price per quote = SKU x pincode, on UNIT prices)
   -> elementary: matched-model Jevons (+ GEKS-Jevons and regular-price variants as robustness)
   -> missing item relatives imputed from a seasonal-trend prior (11 years of official data); flagged; Young fixed-weight aggregation
   -> validation vs official series (gates), nowcast scoring -> static site / CSV / JSON / bulletin
```

## Design decisions worth defending
- **Unit prices** (per kg / L / piece): pack-size changes surface as price changes (shrinkflation).
- **Matched-model Jevons** on quotes seen in both months: robust to SKU churn and stock-outs.
- **Relatives, not levels, are imputed**, so missing data never causes jumps in the chain.
- **Every non-official series is gated** against the matching official item index (see "The gate"). A series that has not yet got six overlapping months is `pending`: counted, but labelled unvalidated.
- **Three honest buckets.** Observed (direct tariffs, spot prices, DoCA Rajkot quotes), proxies (wholesale, national retail, one-venue diaries, regulated ceilings; they are not Rajkot shelf prices) and **modelled** (rent). They are reported separately, never merged into one "independent" claim.
- **Official stand-ins are never hidden**: items with no independent source carry the MoSPI item index and are flagged `official_link`; they are cut off where an independent feed starts.
- **Coverage is a first-class output**: shares of weight by source class are published every refresh (`docs/data/status.json`).
- **Immutable vintages**, polite scraping (robots.txt, rate limits, honest User-Agent, no evasion), a demo guard that cannot publish synthetic data without a red watermark.
- **Staleness alarms** on hand-curated registers (electricity FPPAS, milk, LPG, PNG, ...): a refresh errors visibly if the newest entry is older than its normal revision cycle.

## Current status (2026-10-08)

**Headline (2025-01 = 100):** Oct 2026 **108.38** (MoM 0.16%, YoY 6.80%); last fully official-covered month Aug 2026 **107.32** (YoY 5.44% vs MoSPI Gujarat-urban general 4.68%, CPI-IW Rajkot 3.54%).
Sep and Oct 2026 are partly a **nowcast** (MoSPI lags about 12 days after month end); nowcast months carry a back-tested 90% band. Weights are **approximate**, recovered from the official index tree (MoSPI publishes no Gujarat item weights).

**Where the weight comes from (67 items, plan weights):**

| Bucket | Weight | What it is |
|---|---|---|
| Direct, observed | 22.1% | administered tariffs and spot prices: petrol, diesel, LPG, PNG, electricity, water, milk, telecom, OTT, gold, silver, other registers |
| Retail quotes | 2.1% | DoCA retail reports at the Rajkot centre (groundnut oil, sugar, gur); gated, pass |
| **Modelled** | **19.0%** | **R001 rent**, from Labour Bureau CPI-IW housing data (see below) |
| Proxy | 46.0% | wholesale mandi / NECC, DoCA all-India and Gujarat retail panels, DMart Ahmedabad shelf, Vishal Mega Mart diary, FRC school fees, cinema and salon diaries, regulated ceilings. Not Rajkot shelf prices |
| Official stand-in | 10.8% | doctor, hospital, bus, tyres, smartphone, broadband, newspaper, tuition, photocopy, veg thali, street snack plate; no reachable independent source |

**Gate status:** 13 gated series pass (34.4% of weight, including rent and school fees), 28 are pending (28.2% of weight, mostly forward diaries that need six months of overlap), 0 fail. About 27% of weight is administered or spot series where the price is the price and no gate applies. Pending is not validated: expect some of these (the mandi items, for instance) to fail when their gate matures, and treat the 89% below as a ceiling on what is independent, not a measure of accuracy.

**Independent plan share: 89.2%** = 70.2% observed or proxy + 19.0% modelled rent. It was 18.4% at the first sweep and 70.2% before rent was modelled.

## Methods round, 2026-10-07 (inventory section AK)
- **Pre-registered live scoring** (`rpi/prereg.py`, refresh step `log:prereg`): each refresh date-stamps every gated item's forecast of the next official change before the official figure is seen, then scores it when MoSPI publishes; per-item CUSUM flag (does not demote automatically; `[prereg] auto_demote` is off). First scores: MoSPI Sep 2026, mid-Oct.
- **Fused best-estimate series** (`docs/data/rpi_fused.csv`, `rpi/fusion.py`, `scripts/fusion_backtest.py`): seasonal prior + calibrated proxy, with an 80% band. A nowcast of the **official basis**, not independent, not counted in any share. In a 14-origin backtest it beats the seasonal prior (index RMSE 0.33 vs 0.47 pp) but is **not better than the plain beta = 1 rule (0.30 pp)**; its value is the band.
- **Negative results:** cross-state partial pooling of the national proxy's pass-through does not beat beta = 1 (loss ratio 1.00-1.02); the national panel is only 5-16% better than predicting zero for chana, banana and tur, and no better for rice. Weather, festival-timing and AR drivers do not beat the seasonal prior for potato, onion, tomato, brinjal.

## The gate
`rpi/proxy_check.py`. For each gated item over the months it overlaps the official Gujarat-urban item index:
- `corr`: correlation of month-on-month log changes, must be >= 0.5;
- `drift`: |cumulative change (series) - cumulative change (official)|, must be <= 0.10;
- fewer than 6 overlapping months: `pending`; anything else: `fail` (surfaced as a refresh error). An item that starts passing is reported, never auto-promoted.

**The one exception is rent (R001), by explicit owner decision.** No half-yearly or otherwise independent series can pass the correlation test for rent: official monthly rent changes are close to noise (mean 0.203%, sd 0.071 pp, lag-1 autocorrelation 0.10) and even the official series' own best linear trend only correlates 0.24 with them (`rentsignal.gate_ceiling`). Rent is therefore gated on trend instead (`rentsignal.trend_gate`): the cumulative gap and the last-12-month gap must lie within 1.645 x sd x sqrt(n) of official (0.51 pp and 0.41 pp today). This rejects a flat signal, all-India housing as is, and the earlier v1; it accepts the wired v3 (gaps -0.26 and -0.25 pp). The test was chosen after the correlation gate failed, so it is post hoc; its power is only for trend errors above about 1 pp over 19 months. If it ever fails on a refresh, R001 reverts to `official_link`.

## Rent: a modelled series (`rpi/rentsignal.py`, `rpi/collectors/rent_signal.py`)
Inputs are public Labour Bureau CPI-IW housing-group indices: all-India half-yearly 2020H2-2026H2 and a 78-centre panel 2020H2-2023H1 (`data/labour_bureau/`). No MoSPI value enters the signal. Rajkot's half-year step is the mean of two models picked by a rule fixed on panel forecast error before comparison with MoSPI: an empirical-Bayes shrunk additive deviation from the all-India step and a pooled-parameter Kalman time-varying ratio. Monthly timing inside a half is a flat run-rate. It runs from 2025-01 to the end of the last housing half-year and is **never extrapolated**: a new Labour Bureau row is needed each January and July. Full derivation, alternatives tried and caveats: `data/labour_bureau/RENT_SIGNAL_NOTES.md` and inventory section AJ. This is a model of rent, not observed rents; housing also includes owner-occupied and rent-free homes.

## Not independent, and known limits
- 10.8% of weight is the official index fed back in; agreement with official on those items is circular. The independent test is how observed items (fuel, LPG, metals, DoCA) behave against their official counterparts: `data/official/audit_report.md`.
- Proxies are not Rajkot prices (national panels, Ahmedabad shelf, one-venue diaries). Their trade-offs are written per item in `data/source_plan.csv`.
- Months beyond the last official month are nowcast; the 90% band is in the published CSV.
- Rejected on purpose: scrapers for BigBasket/Blinkit/Zepto-type apps (ToS), aggregator FPPAS figures (Rs 2.70 / 3.30), unverified fuel quotes, rent portal scraping (asking prices, ToS).
- No primary data collection (rent survey, own surveys, data.gov.in key) is assumed in the current design; items that would need it are listed in the inventory.

## Repo map
- `rpi/` engine, collectors (`rpi/collectors/`), gates (`proxy_check.py`), nowcast (`nowcast_eval.py`), rent model (`rentsignal.py`), electricity model, registers/staleness (`registry.py`), publishing.
- `data/source_plan.csv` one row per item: source, class, and the written reason. `data/official/` MoSPI series, audits, screens, back-tests, and the dated source inventory.
- `data/official/source_inventory_2026-10-02.md` every source looked at, wired or not, with credibility ratings and evidence (sections A-AJ). `data/official/data_access_guide.md` for the data.gov.in key and RTI requests.
- `scripts/` one-off builders and back-tests (coverage ceiling, replay back-test, seasonal tests, pooled accuracy, CEDA/Agmarknet screens).
- `docs/` the published site (`index.html`, `data/*.csv|json`, monthly bulletin). `CHANGELOG.md` the archived sweep-by-sweep log.

## Deployment (GitHub Actions)
- `daily.yml` refreshes every source and commits `data/` and `docs/` daily (10:30 IST) or on demand; `ci.yml` runs the tests on code changes; `probe.yml` and `probe_datagov.yml` are manual host probes.
- **Network caveat (measured 2026-10-02):** the DoCA mirror returns 403 to GitHub-hosted runners (US IPs), and the Labour Bureau and MoSPI APIs do not answer there. DoCA-fed items and the CPI-IW benchmark therefore do not refresh on the hosted runner; the run logs the error and keeps the last good data. Fix: register a self-hosted runner on a machine with an Indian IP and set the repository variable `RPI_RUNNER=self-hosted`.
- Raw HTTP snapshots are git-ignored; everything the index needs is in `data/` and `docs/`.

## Open items
1. Refresh when MoSPI's Sep 2026 data lands (mid-October): the rent trend gate gains a 21st month, and the mandi, cost-push and event checks re-run.
2. Pending proxies mature over 2026-27; the five pending mandi items (F001, F004, F022, F023, F025; 4.9% of weight) are expected to fail (inventory AD).
3. Rent needs a Labour Bureau housing row each half-year (next: January 2027).
4. R003 (LPG) register is at its 120-day staleness limit and needs review.
5. Sources with no history-checkable independent series remain official-linked: see the table above and the inventory.
