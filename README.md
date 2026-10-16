# Rajkot Price Index (RPI)

An independent, auto-updating, open-method consumer price index for Rajkot city, built to be checked against the official MoSPI CPI (Gujarat urban) rather than copied from it. Everything the index uses is in this repo: collectors, a warehouse, the index engine, validation gates, health monitoring, a static site (`docs/`, GitHub Pages), an econometrics module (`econ/`) and tests.

**Status: experimental.** The headline mixes observed prices, gated proxies, one modelled series (rent), and official stand-ins. Read "Current status" and "Independence and known limits" before quoting a number.

```bash
pip install -r requirements.txt
python3 -m pytest -q                # 336 passed, 2 skipped
python3 -m rpi refresh              # collect every source -> gate -> build -> audit -> publish (docs/)
python3 -m rpi refresh --offline    # rebuild from data already in the repo (no network)
python3 -m rpi demo                 # synthetic run -> docs_demo/index.html (watermarked DEMO)
python3 -m rpi probe                # which data hosts answer from this machine
python3 -m econ report              # econometrics module: fit, backtest, breaks (writes econ/outputs/)
python3 -m econ log                 # prospective test: log forecasts for unreleased months
python3 -m econ score               # prospective test: score logged forecasts once MoSPI publishes
python3 -m shadowreport report     # shadow-vs-actual report for every shadow feed (writes shadowreport/outputs/)
python3 -m shadowreport check      # same, exit 1 if any feed is fail, out_of_band or stale
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
- **Every non-official series is gated** against the matching official item index (see "The gate"). A/B/C are reported independently; the long-horizon comparator is spliced back to 2014, while the index base remains 2025-01.
- **Three honest buckets.** Observed (direct tariffs, spot prices, DoCA Rajkot quotes), proxies (wholesale, national retail, one-venue diaries, regulated ceilings, web-shop feeds; these are not Rajkot shelf prices) and **modelled** (rent). They are reported separately, never merged into one "independent" claim.
- **Official stand-ins are never hidden.** Items with no independent source carry the MoSPI item index and are flagged `official_link`; they are cut off where an independent feed starts.
- **Coverage is a first-class output**: shares of weight by source class are published every refresh (`docs/data/status.json`).
- **Immutable vintages**, polite scraping (robots.txt, rate limits, honest User-Agent, no evasion), and a demo guard that cannot publish synthetic data without a red watermark.
- **Staleness alarms** on hand-curated registers (electricity FPPAS, milk, LPG, PNG, ...): a refresh errors visibly if the newest entry is older than its normal revision cycle.

## Current status (offline rebuild 2026-10-16; source snapshot 2026-10-16)

The input is the latest daily-bot refresh on `Nityahapani/rpi` main: commit `e9bd9455cce702747c2701b6b6992dce65d47ec4`, bot run `20261016T094753877494Z`. Its database had 344 products, 9,187 observations and 1,836 raw snapshots. The offline integration run is `20261016T115235171390Z`; `data/source_snapshot.json` and `docs/data/status.json` retain the bot commit/run ID and input checksums. No daily source collector ran during the rebuild; a one-off public DoCA panel-screen diagnostic was refreshed separately. Only verified `doca_rajkot` history/products were merged from the pre-refresh integration database, keeping target rows on collisions. After the merge the offline rebuild trimmed 40 superseded official-link observations; final database counts are 355 products, 62,910 observations and 1,836 raw snapshots. All other non-DoCA source counts match the bot snapshot; the pre-rebuild non-DoCA content checksum is recorded in the manifest. The prospective first-seen ledger remains in the 2025+ index era and does not treat the 2014–2024 splice as newly released official data.

**Headline (2025-01 = 100):**

| Month | Index | MoM | YoY | Basis |
|---|---:|---:|---:|---|
| 2026-09 | 108.09 | 1.36% | 6.94% | latest official/reference month |
| 2026-10 | 108.33 | 0.22% | 7.17% | nowcast; 90% band 107.45–109.22 |

MoSPI Gujarat-urban General CPI was up **4.67% YoY in September 2026**. The RPI's October estimate is a nowcast, not an official release. Weights remain approximate because MoSPI publishes no Gujarat item weights. The October quote-bootstrap 95% interval is **107.69–109.06**; the separate 90% nowcast band is **107.44–109.21**. Neither interval includes item-selection or weight error. Against a clean offline rebuild of the Oct 16 bot snapshot with the pre-promotion source plan, the new source choice changes Sep from 108.309 to 108.095 (−0.214) and Oct from 108.462 to 108.324 (−0.138); the largest absolute level difference is 0.950 in Jul 2026.

**Where the weight comes from (67-item basket, plan shares):**

| Bucket | Weight | What it is |
|---|---:|---|
| Direct | 22.1% | administered tariffs, spot prices and PNG |
| Rajkot retail | 15.5% | DoCA Rajkot-centre retail quotes plus Rajkot web shops |
| **Modelled** | **19.0%** | **R001 rent**, a Labour Bureau CPI-IW housing-group model, not observed rent |
| Proxy | 32.7% | wholesale feeds, DoCA national panel, DMart Ahmedabad, diaries and regulated ceilings |
| Official stand-in | 10.7% | MoSPI item indices where no independent source is currently assigned |
| None | <0.01% | T005; no source |

**Independent plan share: 89.30849%.** Direct plus Rajkot-retail weight is **37.59469%**, up **8.64676 points** from the pre-promotion plan (28.94793%). This is progress toward the roughly 50% local-source aspiration, not the target itself. Primary data collection remains deferred; no API-key source was used.

**Long-history DoCA gate:** the comparator is `data/official/official_item_spliced.csv` (9,897 rows, 66 items, 2014-01..2026-09), built from CPI2012 item history and spliced to CPI2024 movements. Rajkot-centre DoCA history begins 2014-01; balanced Gujarat/all-India panels remain at `PANEL_START=2025-01-01`; the published index still starts at 2025-01. The seven Rajkot promotions are:

| Item | Overlap | Passing legs | Key diagnostics |
|---|---:|---|---|
| F002 rice | 150 | C | R² .534; slope 1.118; recent drift .018 |
| F003 tur dal | 150 | B+C | 12m corr .90; R² .845; slope 1.084; drift .071 |
| F005 chana dal | 150 | B+C | 12m corr .91; R² .921; slope 1.337; drift .021 |
| F008 edible oils | 150 | B+C | 12m corr .87; R² .961; slope 1.315; drift .032 |
| F021 potato | 150 | B+C | 12m corr .81; R² .723; slope .993; drift .079 |
| F022 onion | 150 | B+C | 12m corr .82; R² .714; slope 1.083; drift .013 |
| F023 tomato | 150 | B+C | 12m corr .64; R² .639; slope .956; drift .034 |

For these seven new promotions monthly leg A fails; a constant level offset is allowed, while the long-horizon legs do the work. F008 is a matched-SKU panel: DoCA commodity IDs 17/18/19/20/21 jointly feed the index item, not five separate substitute items. F025 remains on Gondal; the Amul milk tariff (F009) and Rajkot-local shop feeds still accruing (F001/F004/F007/F016) are not displaced. Per-leg pass/fail/pending status for **all 42** active validator rows is in [`docs/data/proxy_validation.csv`](docs/data/proxy_validation.csv) and `docs/data/status.json`.

The DoCA panel screen covers 34 commodity-level rows (17 Rajkot, 7 Gujarat, 4 India, 6 with no passing panel); those counts include five diagnostic F008 components (IDs 17–21). Each is tagged `combined_pool_component`: the active F008 validator is one item-level matched-SKU chain across all five IDs, shown as a single F008 row in `docs/data/proxy_validation.csv`. The screen's `wire_to` is only a commodity-level diagnostic, not an instruction to create five index items. Only the seven user-approved Rajkot-centre promotions were wired in this change. The report is `data/official/doca_panel_screen.csv`.

**F022/F023 official-link diagnosis:** their `official_link` product rows exist but have zero observations because the overlap cutoff is 2014-01, the first month of their DoCA Rajkot history. The database has 3,943 and 3,946 DoCA observations respectively, with 150 comparator months for each. This is intentional trimming, not lost CPI history; no official-link backfill was added.

**Gate verdicts:** 14 pass, 27 pending, 1 fail (R001's separate trend gate) out of 42 active series. Within the 89.3% independent plan weight, 17.91 points pass, 25.81 are pending, 19.00 fail, and 26.60 are not gate-applicable. B is evaluated once at least three paired calendar-aligned 12-month changes exist; unlike C it has no separate 24-level minimum. C requires n ≥ 24. The complete A/B/C diagnostics, including empty `legs` for non-passing rows and `leg_status` for all three legs, are machine-readable in the CSV above.

**Offline-rebuild warnings and source status (16 Oct):**
- The offline integration intentionally skipped network collectors, so these are not new live-source failures. It surfaced the existing LPG register staleness warning: R003 last changed 2026-06-07 (131 days against a 120-day review cycle); the last good register series was retained.
- `validate:proxies` continues to report R001 failed under its separate rent-trend gate. All seven newly promoted DoCA Rajkot items pass their long-window gate: F002 C; F003/F005/F008/F021/F022/F023 B+C.
- The prospective ledger flagged F013 and F026 for CUSUM review; automatic demotion is off, so neither source was changed by that diagnostic.
- Rajkot shops had 20 stored quotes (11 candidate items; latest quote 2026-10-10), all still pending; no blocked endpoint was retried or bypassed.
- The separately refreshed public DoCA screen contains 34 commodity-level rows (as of 2026-10-16). Its five F008 rows remain tagged as pooled-item components; the active gate is one pooled F008 row.

The Oct 16 daily-bot snapshot was not rolled back. Only DoCA Rajkot history was merged, the explicit source manifest is committed, and the generated results were rebuilt offline. The source-by-source counts and provenance are in `data/source_snapshot.json` and `docs/data/status.json`.

## Independence and known limits

**The 2025–26 history is largely back-filled from the official index.** This matters more than any other point in this README. Across the 1,386 mapped item-months from Jan 2025 through Sep 2026 (66 items × 21 official months), 824 (59.5%) remain identical to the rebased official item within floating-point tolerance; 32 of the 66 items are identical in every month. The base month is necessarily rebased to 100. This is not independent evidence: official-link rows match by construction, while some independently sourced rows may also coincide with the official series.

The other 562 item-months, across 34 items, differ from the official relative. They are not automatically clean independent evidence either: they include administered prices, proxies and modelled rent as well as independent retail feeds. Validation claims must be restricted to genuinely observed, independent observations; the forward-looking tests in `econ/` and `rpi/prereg.py` are the cleaner out-of-sample evidence available.

Other limits:
- 10.7% of weight is the official index fed back in; agreement with official on those items is circular.
- Proxies are not Rajkot prices (national panels, Ahmedabad shelf, one-venue diaries). Their trade-offs are written per item in `data/source_plan.csv`.
- Months beyond the last official month are nowcasts; the back-tested band is in the published CSV.
- Rejected on purpose: scrapers for BigBasket, Blinkit and Zepto-type apps (terms of service), aggregator FPPAS figures (Rs 2.70 / 3.30), unverified fuel quotes, and rent-portal scraping (asking prices, terms of service).
- No primary data collection (rent survey, own surveys, data.gov.in key) is assumed in the current design; items that would need it are listed in the inventory.

## Pre-registered live scoring (`rpi/prereg.py`)
Each refresh date-stamps every gated item's forecast of the next official change before the official figure is seen, then scores it when MoSPI publishes. A per-item CUSUM flag is raised but does not demote the item automatically (`[prereg] auto_demote` is off). First scores: MoSPI September 2026, mid-October.

## Econometrics module (`econ/`, shadow only)

Nothing in `econ/` feeds the published index. It has three parts.

1. **Analysis commands.** `fit` estimates a one-factor dynamic model by maximum likelihood, with a Kalman filter written in numpy and scipy (no new dependency), plus a bridge to the official monthly change. `compare` runs a rolling-origin backtest of several candidates against the official general index. `breaks` runs a CUSUM check on each division. The first backtest found no candidate that beat the fixed-weight benchmark with an interval clear of zero. That backtest was contaminated by the back-fill described above, so its numbers are not evidence.

2. **Item-level calibration** (`econ/items.py`, `econ/items_model.py`). Rpi item changes are matched to official item changes and calibrated pooled across items. In the archived calibration run (the then-current 371 independent item-months), out-of-sample RMSE is 2.19 for the raw rpi change, 2.06 for ordinary least-squares calibration, and 1.93 for Huber (outlier-robust) calibration. The Huber choice was made on a development window, but the 2026 holdout was already visible when it was chosen, so this figure is optimistic; the Oct 15 DoCA integration did not retrain this model. A nested test, which picks the Huber threshold inside each training window, gives 2.18 against 2.49 for raw, with a gap of −0.31 and a 95% interval of −0.66 to +0.005. That is a suggestive improvement, not a demonstrated one. The nested test is in the working tree and is not committed.

3. **Prospective ledger** (`econ/ledger.py`, `econ/ledger/`). The 10 Oct candidate (the calibrated item model, frozen on its 412 independent item-month development set through 2026-08) remains logged before each official release; the Oct 15 DoCA gate integration did not retrain it. The ledger is append-only, and each row records when it was issued and fingerprints of its inputs. Logged so far: September 2026 candidate +0.47% against baseline +0.64%, and October 2026 candidate +0.23% against baseline +0.25%. Both were issued 2026-10-10, before any official figure existed. The pre-registered decision rule needs 12 scored months: adopt the candidate only if its RMSE is lower than the baseline's and the 95% month-bootstrap interval of the gap lies entirely below zero. Until then, the status is "not decided" or "not established". The ledger is in git, so its timestamps can be checked.

## Shadow report (`shadowreport/`, shadow only)

Compares every shadow feed with its actual reference, where one exists, and gives each feed one status. Read-only over the repo data; it writes `shadowreport/outputs/shadow_report.{json,md}` (git-ignored) and changes nothing that feeds the index, a switch or a gate.

Six feeds: 1mg Calpol (M001, against the NPPA tariff in `data/tariff_events.csv`), Hathway K003, Apple K002, Green Mercado, the Rajkot web shops (per-item gate verdicts from `data/official/shadow_sources.json`), and the rent listings panel (R001, median asking rent against the official house-rent series, judged with the same trend gate as R001 after 6 overlap months).

Statuses, worst first: `fail`, `out_of_band`, `stale`, `no_quotes`, `pending`, `tracking`, `pass`. `inactive` marks a known-closed source (Green Mercado) and does not count toward the overall status. Price feeds are `out_of_band` when the latest gap to the reference is over 10%; that band is a report threshold, not a gate.

## Rent: a modelled series (`rpi/rentsignal.py`, `rpi/collectors/rent_signal.py`)
Inputs are public Labour Bureau CPI-IW housing-group indices: all-India half-yearly 2020H2 to 2026H2, and a 78-centre panel 2020H2 to 2023H1 (`data/labour_bureau/`). No MoSPI value enters the signal. Rajkot's half-year step is the mean of two models, chosen by a rule fixed on panel forecast error before comparison with MoSPI: an empirically shrunk additive deviation from the all-India step, and a pooled-parameter Kalman time-varying ratio. Monthly timing within a half is a flat run-rate. The signal is never extrapolated: a new Labour Bureau row is needed each January and July. Derivation and caveats: `data/labour_bureau/RENT_SIGNAL_NOTES.md`. This is a model of rent, not observed rents, and housing includes owner-occupied and rent-free homes.

**Rent gate exception.** Rent (R001) is gated on trend, not correlation, by explicit owner decision. Official monthly rent changes are close to noise, so no series can pass a correlation test. The trend gate (`rentsignal.trend_gate`) is post hoc, chosen after the correlation gate failed, and its power is only for trend errors above about 1 point over 19 months. If it fails on a refresh, R001 reverts to `official_link`.

## The gate
`rpi/proxy_check.py` reports three independent legs over the active source's overlap with the spliced Gujarat-urban item comparator:
- **A — monthly tracking:** at least 6 overlapping months, correlation of month-on-month log changes ≥ 0.5, and absolute cumulative log-change drift over the full overlap ≤ 0.10.
- **B — annual tracking:** correlation of calendar-aligned 12-month log changes ≥ 0.5, evaluated when at least three paired annual changes are available. B has no separate 24-level minimum.
- **C — level fit:** at least 24 overlapping levels; R² of `log(proxy) ~ log(official)` ≥ 0.5; slope in [0.5, 1.5]; and absolute cumulative log-change drift over the latest 24 calendar months ≤ 0.10. The exact level at the month 24 months before the end is required; if missing, C remains pending.

A fixed proportional level offset is admissible because the published item relatives are chain-rebased. A series passes if any leg passes. If none passes, the overall verdict stays `pending` while any applicable leg is unevaluable; it is `fail` only when A, B and C have all been evaluated and failed. The result includes the passing `legs` and `leg_status` for A, B and C. Modelled rent R001 uses its separately approved trend gate. The CPI2012/CPI2024 splice is rebuilt on every refresh, and validation fails closed if it is missing.

## Repo map
- `rpi/`: engine, collectors (`rpi/collectors/`), gates (`proxy_check.py`), nowcast (`nowcast_eval.py`), rent model (`rentsignal.py`), electricity model, registers and staleness (`registry.py`), publishing.
- `rpi/panel_eval.py`: the deep replay, ten nowcast rules over 76 to 80 origins per horizon (2018-01 to 2025-11, untouched test window from 2023-01) on the 2014–2025 official item panel, with Diebold-Mariano (HLN), Mincer-Zarnowitz and Clark-West tests and walk-forward calibration (`make eval`). `rpi/evalstats.py` and `rpi/tsdiag.py` are the statistics layer; `rpi/index/uncertainty.py` bootstraps quotes, item availability and weights separately (`make uncertainty`).
- `econ/`: the econometrics module described above.
- `rpi/fusion.py`, `scripts/fusion_backtest.py`: fused best-estimate series (`docs/data/rpi_fused.csv`) with an 80% band. It is a nowcast of the official basis, not independent. In a 14-origin backtest it beats the seasonal prior (RMSE 0.33 vs 0.47 percentage points) but not the plain beta = 1 rule (0.30); its value is the band.
- Negative results recorded: cross-state partial pooling does not beat beta = 1; weather, festival-timing and AR drivers do not beat the seasonal prior for potato, onion, tomato or brinjal.
- Rajkot-local prices, SHADOW mode (`rpi shadow`, `make shadow`): `rpi/collectors/rajkot_shops.py` prices a fixed 40-SKU pool at three Rajkot sellers' own web shops; `rpi/shadow.py` gates them against the official item index. A shadow source reaches the index only after the item's `primary_source` is switched in `data/source_plan.csv` and its configured switch month begins.
- Rent listings: `rpi/collectors/rent_listings.py` crawls Rajkot residential listings (rotating list-URL set, `data/rent_list_urls.csv`); `rpi/rentlistings.py` builds a hedonic new-lease index and a stock-rent candidate for R001 (`data/official/rent_listings_index.json`). R001 stays on the modelled signal until the candidate qualifies.
- `data/source_plan.csv`: one row per item, with source, class and the written reason. `data/official/`: MoSPI series, audits, screens, back-tests and the dated source inventory. `data/official/source_inventory_2026-10-02.md` lists every source looked at, with credibility ratings (sections A to AJ).
- `SOURCE_SHARES.md`: current source-by-source weight, A/B/C gate status, risk concentration and the 2026-10-10/15/16 change log.
- `scripts/`: one-off builders and back-tests. `docs/`: the published site (`index.html`, `data/*.csv|json`, monthly bulletin). `CHANGELOG.md`: the archived sweep-by-sweep log.

## Deployment (GitHub Actions)
- `daily.yml` refreshes every source and commits `data/` and `docs/` daily (10:30 IST) or on demand. `ci.yml` runs the tests on code changes. `probe.yml` and `probe_datagov.yml` are manual host probes.
- **Network caveat (measured 2026-10-02):** the DoCA mirror returns 403 to GitHub-hosted runners, and the Labour Bureau and MoSPI APIs do not answer there. DoCA-fed items and the CPI-IW benchmark therefore do not refresh on the hosted runner. The run logs the error and keeps the last good data. Fix: register a self-hosted runner on a machine with an Indian IP and set the repository variable `RPI_RUNNER=self-hosted`.
- Raw HTTP snapshots are git-ignored. Everything the index needs is in `data/` and `docs/`. Generated econ outputs (`econ/outputs/`) are git-ignored too.

## Open items
1. **Shop and shadow feeds:** continue checking approved sources without evading rate limits or access controls. Latest stored diagnostics show 11 Rajkot-shop candidate items, all pending (last quote 2026-10-10); Apple Store, Hathway and 1mg shadow candidates are also pending. Do not retry or bypass blocked endpoints; consider only a slower schedule, an approved source or a self-hosted runner from an allowed network.
2. MoSPI September 2026 data is already loaded; continue scoring the prospective ledger and rerun the monthly audits on the next refresh.
3. **Pending sources** mature over 2026–27. F001/F004/F007/F016 are on Rajkot shop feeds awaiting their gate; F025 remains on Gondal (F022/F023 now pass on DoCA Rajkot). DMart and diary sources remain pending.
4. **Rent (R001)** currently fails its separate trend gate; primary data collection remains deferred.
5. **R003 (LPG)** register needs review after the 16 Oct offline-refresh staleness alert (last change 2026-06-07; 131 days against a 120-day review cycle).
6. The ~50% direct-plus-Rajkot-retail aspiration is still unmet at 37.59%; primary collection is a later phase. The official-backfill caveat remains important when interpreting 2025–26 agreement.
7. **Econometrics:** the nested Huber test is uncommitted. Adding Huber to the prospective ledger as a second candidate needs your decision.
