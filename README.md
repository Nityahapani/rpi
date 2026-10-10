# Rajkot Price Index (RPI)

An independent, auto-updating, open-method consumer price index for Rajkot city, built to be checked against the official MoSPI CPI (Gujarat urban) rather than copied from it. Everything the index uses is in this repo: collectors, a warehouse, the index engine, validation gates, health monitoring, a static site (`docs/`, GitHub Pages), an econometrics module (`econ/`) and tests.

**Status: experimental.** The headline mixes observed prices, gated proxies, one modelled series (rent), and official stand-ins. Read "Current status" and "Independence and known limits" before quoting a number.

```bash
pip install -r requirements.txt
python3 -m pytest -q                # 289 passed, 2 skipped (skips need pdfplumber)
python3 -m rpi refresh              # collect every source -> gate -> build -> audit -> publish (docs/)
python3 -m rpi refresh --offline    # rebuild from data already in the repo (no network)
python3 -m rpi demo                 # synthetic run -> docs_demo/index.html (watermarked DEMO)
python3 -m rpi probe                # which data hosts answer from this machine
python3 -m econ report              # econometrics module: fit, backtest, breaks (writes econ/outputs/)
python3 -m econ log                 # prospective test: log forecasts for unreleased months
python3 -m econ score               # prospective test: score logged forecasts once MoSPI publishes
```

## Architecture
```
collectors (API / HTTP / tariff events / CSV / model)
   -> raw snapshots (content-addressed, immutable)  -> SQLite warehouse (products, observations)
   -> panel (monthly geometric-mean price per quote = SKU x pincode, on UNIT prices)
   -> elementary: matched-model Jevons (+ GEKS-Jevons and regular-price variants as robustness)
   -> missing item relatives imputed from a seasonal-trend prior (11 years of official data); flagged; fixed-weight aggregation
   -> validation vs official series (gates), nowcast scoring -> static site / CSV / JSON / bulletin
```

## Design decisions worth defending
- **Unit prices** (per kg / L / piece): pack-size changes surface as price changes (shrinkflation).
- **Matched-model Jevons** on quotes seen in both months: robust to SKU churn and stock-outs.
- **Relatives, not levels, are imputed**, so missing data never causes jumps in the chain.
- **Every non-official series is gated** against the matching official item index (see "The gate"). A series with fewer than six overlapping months is `pending`: counted, but labelled unvalidated.
- **Three honest buckets.** Observed (direct tariffs, spot prices, DoCA Rajkot quotes), proxies (wholesale, national retail, one-venue diaries, regulated ceilings, web-shop feeds; these are not Rajkot shelf prices) and **modelled** (rent). They are reported separately, never merged into one "independent" claim.
- **Official stand-ins are never hidden.** Items with no independent source carry the MoSPI item index and are flagged `official_link`; they are cut off where an independent feed starts.
- **Coverage is a first-class output**: shares of weight by source class are published every refresh (`docs/data/status.json`).
- **Immutable vintages**, polite scraping (robots.txt, rate limits, honest User-Agent, no evasion), and a demo guard that cannot publish synthetic data without a red watermark.
- **Staleness alarms** on hand-curated registers (electricity FPPAS, milk, LPG, PNG, ...): a refresh errors visibly if the newest entry is older than its normal revision cycle.

## Current status (2026-10-10)

**Headline (2025-01 = 100):**

| Month | Index | MoM | YoY | Basis |
|---|---|---|---|---|
| 2026-08 | 107.32 | 1.36% | 5.44% | last month with full official coverage |
| 2026-09 | 108.20 | 0.83% | 6.47% | nowcast |
| 2026-10 | 108.37 | 0.16% | 6.80% | nowcast; back-tested band 106.9 to 109.9 |

For comparison, MoSPI's Gujarat-urban general inflation for August 2026 was 4.68% (CPI-IW Rajkot 3.54%). MoSPI lags about 12 days after month end, so September and October are nowcasts. Weights are **approximate**, recovered from the official index tree, because MoSPI publishes no Gujarat item weights.

**Where the weight comes from (67 items, plan weights, after the web-shop switch):**

| Bucket | Weight | What it is |
|---|---|---|
| Direct, observed | 22.1% | administered tariffs and spot prices: petrol, diesel, LPG, PNG, electricity, water, milk, telecom, OTT, gold, silver, other registers |
| Retail quotes | 6.8% | DoCA retail reports at the Rajkot centre (groundnut oil, sugar, gur), plus four items switched to Rajkot web shops from November 2026 |
| **Modelled** | **19.0%** | **R001 rent**, from Labour Bureau CPI-IW housing data (see below) |
| Proxy | 41.2% | wholesale mandi / NECC, DoCA all-India and Gujarat retail panels, DMart Ahmedabad shelf, Vishal Mega Mart diary, FRC school fees, cinema and salon diaries, regulated ceilings |
| Official stand-in | 10.8% | doctor, hospital, bus, tyres, smartphone, broadband, newspaper, tuition, photocopy, veg thali, street snack plate; no reachable independent source |

**Independent plan share: 89.2%** = 70.2% observed or proxy + 19.0% modelled rent. This is a plan figure. Realised independent weight was 60.2% in August 2026 and rises as diaries accumulate; see `SOURCE_SHARES.md`, which has the full breakdown.

**Gate status:** 13 gated series pass (34.4% of weight, including rent and school fees), 28 are pending (28.2% of weight, mostly forward diaries that need six months of overlap), 0 fail. About 27% of weight is administered or spot series where no gate applies. Pending is not validated: expect some (the mandi items, for instance) to fail when their gates mature.

**Known problems from the last refresh (2026-10-10, run `20261010T111152`):**
- **Web-shop feeds returned no quotes.** Green Force and Hathi Masala were rate-limited (HTTP 429), and Rani Oil returned HTTP 403. The four items switched to shop prices (F001, F004, F007, F016, 4.8% of weight) carry no new shop observations from this run.
- **DMart Ahmedabad was blocked** (HTTP 403). Its 16 items (12.2% of weight) did not refresh.
- **DoCA mirror unreachable**, so DoCA-fed items did not refresh.
- **Labour Bureau refused**: robots.txt could not be fetched, so the CPI-IW benchmark steps failed. This is the polite-client rule working, not a bypass. The rent model runs on Labour Bureau data already in the repo.
- **R003 (LPG) register is stale**: last change 2026-06-07, 125 days ago, against a 120-day review cycle.

The refresh logs these and keeps the last good data. None of them should be fixed by evading the blocks.

## Independence and known limits

**The 2025–26 history is largely back-filled from the official index.** This matters more than any other point in this README. In 1,254 item-months where both an rpi item index and its official counterpart exist, 842 (67%) are identical to the official value to floating-point precision. Forty of the 66 matched items are identical in every month. The rpi item history for those items was carried from the official series, so agreement between the index and MoSPI over 2025–26 is largely circular.

What genuinely tests the index is the **independent** item-months: where the rpi value differs from the official one. There are 412 of them, across 26 items. Any validation of the index, or of the `econ/` models, has to be restricted to those, and the forward-looking tests in `econ/` and `rpi/prereg.py` are the only clean out-of-sample evidence available.

Other limits:
- 10.8% of weight is the official index fed back in; agreement with official on those items is circular.
- Proxies are not Rajkot prices (national panels, Ahmedabad shelf, one-venue diaries). Their trade-offs are written per item in `data/source_plan.csv`.
- Months beyond the last official month are nowcasts; the back-tested band is in the published CSV.
- Rejected on purpose: scrapers for BigBasket, Blinkit and Zepto-type apps (terms of service), aggregator FPPAS figures (Rs 2.70 / 3.30), unverified fuel quotes, and rent-portal scraping (asking prices, terms of service).
- No primary data collection (rent survey, own surveys, data.gov.in key) is assumed in the current design; items that would need it are listed in the inventory.

## Pre-registered live scoring (`rpi/prereg.py`)
Each refresh date-stamps every gated item's forecast of the next official change before the official figure is seen, then scores it when MoSPI publishes. A per-item CUSUM flag is raised but does not demote the item automatically (`[prereg] auto_demote` is off). First scores: MoSPI September 2026, mid-October.

## Econometrics module (`econ/`, shadow only)

Nothing in `econ/` feeds the published index. It has three parts.

1. **Analysis commands.** `fit` estimates a one-factor dynamic model by maximum likelihood, with a Kalman filter written in numpy and scipy (no new dependency), plus a bridge to the official monthly change. `compare` runs a rolling-origin backtest of several candidates against the official general index. `breaks` runs a CUSUM check on each division. The first backtest found no candidate that beat the fixed-weight benchmark with an interval clear of zero. That backtest was contaminated by the back-fill described above, so its numbers are not evidence.

2. **Item-level calibration** (`econ/items.py`, `econ/items_model.py`). Rpi item changes are matched to official item changes and calibrated pooled across items. On the 371 independent item-months, out-of-sample RMSE is 2.19 for the raw rpi change, 2.06 for ordinary least-squares calibration, and 1.93 for Huber (outlier-robust) calibration. The Huber choice was made on a development window, but the 2026 holdout was already visible when it was chosen, so this figure is optimistic. A nested test, which picks the Huber threshold inside each training window, gives 2.18 against 2.49 for raw, with a gap of −0.31 and a 95% interval of −0.66 to +0.005. That is a suggestive improvement, not a demonstrated one. The nested test is in the working tree and is not committed.

3. **Prospective ledger** (`econ/ledger.py`, `econ/ledger/`). A candidate (the calibrated item model, frozen on the 412 independent item-months through 2026-08) is logged before each official release. The ledger is append-only, and each row records when it was issued and fingerprints of its inputs. Logged so far: September 2026 candidate +0.47% against baseline +0.64%, and October 2026 candidate +0.23% against baseline +0.25%. Both were issued 2026-10-10, before any official figure existed. The pre-registered decision rule needs 12 scored months: adopt the candidate only if its RMSE is lower than the baseline's and the 95% month-bootstrap interval of the gap lies entirely below zero. Until then, the status is "not decided" or "not established". The ledger is in git, so its timestamps can be checked.

## Rent: a modelled series (`rpi/rentsignal.py`, `rpi/collectors/rent_signal.py`)
Inputs are public Labour Bureau CPI-IW housing-group indices: all-India half-yearly 2020H2 to 2026H2, and a 78-centre panel 2020H2 to 2023H1 (`data/labour_bureau/`). No MoSPI value enters the signal. Rajkot's half-year step is the mean of two models, chosen by a rule fixed on panel forecast error before comparison with MoSPI: an empirically shrunk additive deviation from the all-India step, and a pooled-parameter Kalman time-varying ratio. Monthly timing within a half is a flat run-rate. The signal is never extrapolated: a new Labour Bureau row is needed each January and July. Derivation and caveats: `data/labour_bureau/RENT_SIGNAL_NOTES.md`. This is a model of rent, not observed rents, and housing includes owner-occupied and rent-free homes.

**Rent gate exception.** Rent (R001) is gated on trend, not correlation, by explicit owner decision. Official monthly rent changes are close to noise, so no series can pass a correlation test. The trend gate (`rentsignal.trend_gate`) is post hoc, chosen after the correlation gate failed, and its power is only for trend errors above about 1 point over 19 months. If it fails on a refresh, R001 reverts to `official_link`.

## The gate
`rpi/proxy_check.py`. For each gated item, over the months it overlaps the official Gujarat-urban item index:
- `corr`: correlation of month-on-month log changes, must be at least 0.5;
- `drift`: |cumulative change (series) minus cumulative change (official)|, must be at most 0.10;
- fewer than 6 overlapping months: `pending`; anything else that fails: `fail` (surfaced as a refresh error). An item that starts passing is reported, never auto-promoted.

## Repo map
- `rpi/`: engine, collectors (`rpi/collectors/`), gates (`proxy_check.py`), nowcast (`nowcast_eval.py`), rent model (`rentsignal.py`), electricity model, registers and staleness (`registry.py`), publishing.
- `rpi/panel_eval.py`: the deep replay, ten nowcast rules over 76 to 80 origins per horizon (2018-01 to 2025-11, untouched test window from 2023-01) on the 2014–2025 official item panel, with Diebold-Mariano (HLN), Mincer-Zarnowitz and Clark-West tests and walk-forward calibration (`make eval`). `rpi/evalstats.py` and `rpi/tsdiag.py` are the statistics layer; `rpi/index/uncertainty.py` bootstraps quotes, item availability and weights separately (`make uncertainty`).
- `econ/`: the econometrics module described above.
- `rpi/fusion.py`, `scripts/fusion_backtest.py`: fused best-estimate series (`docs/data/rpi_fused.csv`) with an 80% band. It is a nowcast of the official basis, not independent. In a 14-origin backtest it beats the seasonal prior (RMSE 0.33 vs 0.47 percentage points) but not the plain beta = 1 rule (0.30); its value is the band.
- Negative results recorded: cross-state partial pooling does not beat beta = 1; weather, festival-timing and AR drivers do not beat the seasonal prior for potato, onion, tomato or brinjal.
- Rajkot-local prices, SHADOW mode (`rpi shadow`, `make shadow`): `rpi/collectors/rajkot_shops.py` prices a fixed 40-SKU pool at three Rajkot sellers' own web shops; `rpi/shadow.py` gates them against the official item index. A shadow source reaches the index only after the item's `primary_source` is switched in `data/source_plan.csv`.
- Rent listings: `rpi/collectors/rent_listings.py` crawls Rajkot residential listings (rotating list-URL set, `data/rent_list_urls.csv`); `rpi/rentlistings.py` builds a hedonic new-lease index and a stock-rent candidate for R001 (`data/official/rent_listings_index.json`). R001 stays on the modelled signal until the candidate qualifies.
- `data/source_plan.csv`: one row per item, with source, class and the written reason. `data/official/`: MoSPI series, audits, screens, back-tests and the dated source inventory. `data/official/source_inventory_2026-10-02.md` lists every source looked at, with credibility ratings (sections A to AJ).
- `SOURCE_SHARES.md`: consolidated source-by-source weight, gate status, risk concentration, and the 2026-10-10 change log.
- `scripts/`: one-off builders and back-tests. `docs/`: the published site (`index.html`, `data/*.csv|json`, monthly bulletin). `CHANGELOG.md`: the archived sweep-by-sweep log.

## Deployment (GitHub Actions)
- `daily.yml` refreshes every source and commits `data/` and `docs/` daily (10:30 IST) or on demand. `ci.yml` runs the tests on code changes. `probe.yml` and `probe_datagov.yml` are manual host probes.
- **Network caveat (measured 2026-10-02):** the DoCA mirror returns 403 to GitHub-hosted runners, and the Labour Bureau and MoSPI APIs do not answer there. DoCA-fed items and the CPI-IW benchmark therefore do not refresh on the hosted runner. The run logs the error and keeps the last good data. Fix: register a self-hosted runner on a machine with an Indian IP and set the repository variable `RPI_RUNNER=self-hosted`.
- Raw HTTP snapshots are git-ignored. Everything the index needs is in `data/` and `docs/`. Generated econ outputs (`econ/outputs/`) are git-ignored too.

## Open items
1. **Shop and DMart feeds:** resolve the HTTP 429, 403 and blocking failures without evading them. Options are a slower schedule, an approved data source, or a self-hosted runner from an allowed network.
2. **Refresh when MoSPI's September 2026 data lands:** the rent trend gate gains a 21st month, the prospective ledger is scored for the first time, and the mandi, cost-push and event checks re-run.
3. **Pending proxies** mature over 2026–27. The five pending mandi items (F001, F004, F022, F023, F025; 4.9% of weight) are expected to fail their gates.
4. **Rent** needs a Labour Bureau housing row each half-year (next: January 2027).
5. **R003 (LPG)** register is past its 120-day staleness limit and needs review.
6. **Back-fill:** decide how the published history should be labelled, and whether the 2025–26 numbers need a caveat in the bulletin.
7. **Econometrics:** the nested Huber test is uncommitted. Adding Huber to the prospective ledger as a second candidate needs your decision.
