# Source shares and independent share — current as of 2026-10-16

This is the current basket-weight view, computed from `registry/items.csv` and checked against `data/source_plan.csv`, the MoSPI-derived weights and `docs/data/summary.json`. Gate verdicts are from `docs/data/proxy_validation.csv` / `docs/data/status.json`. Weights sum to 100.00000%; all percentages below are percentage points of the full basket unless noted.

The input is `Nityahapani/rpi` main at bot commit `e9bd9455cce702747c2701b6b6992dce65d47ec4`, run `20261016T094753877494Z`. The offline integration/rebuild is `20261016T115235171390Z`. It merged only verified DoCA Rajkot history from the pre-refresh integration DB, keeping the Oct 16 target row on conflicts; the source commit, run ID and checksums are recorded in `data/source_snapshot.json` and copied into `docs/data/status.json`. No daily source collector ran during the rebuild. The separately refreshed panel screen used the public DoCA mirror.

## 1. Headline source shares

| Plan class | Weight | Items | Meaning |
|---|---:|---:|---|
| **Independent** | **89.30849%** | 56 | a non-official primary source is assigned |
| Official-linked | 10.68808% | 10 | MoSPI Gujarat-urban item index used as a stand-in |
| None | 0.00343% | 1 (`T005`) | no source assigned |
| **Total** | **100.00000%** | **67** | |

### Independent plan split

| Bucket | Weight | Items | Components |
|---|---:|---:|---|
| Direct | **22.10460%** | 11 | administered tariff, spot metal and PNG prices; the tariff-rate-card overrides below are excluded from this bucket |
| Rajkot retail | **15.49009%** | 14 | DoCA Rajkot-centre retail plus Rajkot-local web shops |
| **Modelled** | **18.99646%** | 1 | R001 rent signal; a Labour Bureau CPI-IW housing-group model, not observed rent |
| Proxy | **32.71734%** | 30 | wholesale, national DoCA, Ahmedabad retail, diaries, rate cards and other non-Rajkot/one-venue feeds |
| **Independent total** | **89.30849%** | **56** | direct + retail + modelled + proxy |

Direct plus Rajkot-retail is **37.59469%**, up from **28.94793%** in the pre-promotion source plan (**+8.64676 points**). The roughly 50% direct-plus-Rajkot-local target remains **12.40531 points short**. No primary data collection was performed; sources requiring an API key were not used.

## 2. Current gate status

The validator reports **42** active non-official series: **14 pass, 27 pending, 1 fail**. The independent-series gate weights below sum to the 89.30849% independent plan share.

| Verdict | Weight | Items | Reading |
|---|---:|---:|---|
| Pass | **17.90929%** | 14 | at least one of A/B/C passes (R001 uses its separately approved trend gate) |
| Pending | **25.80761%** | 27 | no leg passes yet and at least one leg/source remains unevaluable |
| Fail | **18.99646%** | 1 | R001 fails its separate rent-trend gate |
| Not applicable | **26.59513%** | 14 | direct/administered or otherwise ungated source; not part of the 42 rows |
| **Total independent** | **89.30849%** | **56** | |

**Passing item legs:**

| Item | Active source | Passing legs |
|---|---|---|
| F002 rice | `doca_rajkot` | C |
| F003 tur dal | `doca_rajkot` | B+C |
| F005 chana dal | `doca_rajkot` | B+C |
| F006 edible oil | `doca_rajkot` | A+B+C |
| F008 edible oils | `doca_rajkot` | B+C |
| F011 butter | `doca_national` | A+B |
| F013 sugar | `doca_rajkot` | A+B+C |
| F020 eggs | `doca_national` | A |
| F021 potato | `doca_rajkot` | B+C |
| F022 onion | `doca_rajkot` | B+C |
| F023 tomato | `doca_rajkot` | B+C |
| F024 brinjal | `doca_national` | A |
| F026 ginger | `doca_rajkot` | C |
| E001 school fees | `frc_rajkot` | A |

The 27 pending rows are chiefly DMart Ahmedabad (12.22496 points), Vishal diary (6.95309), Rajkot shops (4.78633), and Gondal mandi (0.78931); Fresha salon, cinema and Hathway account for the balance. R001 (18.99646) is the sole fail. The full row-level A/B/C `legs` and `leg_status` are in `docs/data/proxy_validation.csv`; the same results and refresh metadata are in `docs/data/status.json`.

### Gate definition

- **A — monthly tracking:** at least 6 paired levels; correlation of month-on-month log changes ≥ 0.5 and full-overlap cumulative log-change drift ≤ 0.10.
- **B — annual tracking:** correlation of calendar-aligned 12-month log changes ≥ 0.5, once at least 3 paired annual changes exist. B has **no separate n ≥ 24 level floor**.
- **C — level fit:** at least 24 paired levels; R² of `log(proxy) ~ log(official)` ≥ 0.5; slope in [0.5, 1.5]; and last-24-calendar-month cumulative log-change drift ≤ 0.10. The exact month 24 months before the end must be available to compute this drift; otherwise C remains pending, not a fail.
- Any passing leg makes the series pass. With no passing leg, the overall verdict remains pending while any applicable leg is still unevaluable; it fails only once A, B and C have all been evaluated and failed. A missing exact month-24 anchor therefore keeps C pending and the overall result pending when neither A nor B passes. A fixed proportional level offset is admissible because index relatives are chain-rebased.
- R001 rent is a separate exception: a trend gate is used because monthly correlation is not meaningful for the official rent series.

The comparator is `data/official/official_item_spliced.csv`: **9,897 rows, 66 items, 2014-01..2026-09**. It carries CPI2012 item history through the 2025 overlap, rescaled onto CPI2024 movements. Rajkot-centre DoCA history starts 2014-01-01; balanced Gujarat/all-India panels retain `PANEL_START=2025-01-01`; the published index base remains 2025-01.

## 3. Source-by-source weight

| Primary source | Weight | Items | Description |
|---|---:|---:|---|
| `tariff` | 25.12899% | 11 | administered registers and tariff/price events; three ceiling/rate-card items are bucketed as proxies rather than direct prices |
| `rent_signal` | 18.99646% | 1 | modelled Labour Bureau CPI-IW rent signal (R001) |
| `dmart_ahmedabad` | 12.22496% | 16 | fixed packaged-goods pool at DMart Ready, Ahmedabad (proxy) |
| `doca_rajkot` | 10.70376% | 10 | DoCA retail quotes from the Rajkot centre |
| `official_link` | 10.68808% | 10 | MoSPI official item-index stand-in; not independent |
| `vishal_diary` | 6.95309% | 3 | Vishal Mega Mart online diary; not a Rajkot shop-price panel |
| `rajkot_shops` | 4.78633% | 4 | Rajkot retailers' own web shops; configured as index input from Nov 2026 |
| `frc_rajkot` | 3.62177% | 1 | Gujarat FRC-approved Rajkot school fees |
| `doca_national` | 3.58376% | 3 | DoCA all-India balanced retail panel |
| `mandi_gondal` | 0.78931% | 1 | Gondal mandi wholesale; retained for F025 |
| `gr_metals` | 0.78707% | 2 | Rajkot gold/silver spot prices |
| `fresha_salon` | 0.69451% | 1 | Fresha menu price, one venue |
| `gr_png` | 0.67907% | 1 | goodreturns Rajkot PNG series |
| `district_cinema` | 0.23579% | 1 | Rajkot cinema price diary |
| `hathway_broadband` | 0.12362% | 1 | Hathway broadband plans |
| `none` | 0.00343% | 1 | T005, genuinely no source |
| **Total** | **100.00000%** | **67** | |

## 4. Coverage: plan share versus usable quotes

These are distinct measures and should not be collapsed into one “observed share”:

- The plan table assigns **89.30849%** to independent sources, including items whose feed is still accruing or awaiting a gate.
- `docs/data/summary.json` reports **65.5%** latest-month usable quote-weight coverage for 2026-10, after index source switches and quote/freshness filters; the remaining weight is imputed for that month.
- The companion `coverage_split` diagnostic reports 65.9% independent weight in the 2026-09 reference month and 89.3% for the 2026-10 source snapshot; its 2026-09 overall observed weight is 99.2%. This is a source-row coverage diagnostic, not the same as the index engine's usable-quote share.

The increase in plan share is not a claim that every item has a long, current Rajkot quote history. In particular, web-shop source switches begin in Nov 2026; DoCA national/other proxy feeds remain visibly distinct from Rajkot-centre retail.

## 5. Current local-source and source-selection exceptions

- **F002/F003/F005/F008/F021/F022/F023** use `doca_rajkot` from the 2025-01 index base after passing the long-history Rajkot-centre gate. A passing DoCA-centre retail source may replace a proxy; it may not displace a tariff or an accruing Rajkot-local feed.
- **F008 multi-SKU rule:** commodity IDs **17/18/19/20/21** jointly form one item-level matched-SKU chain for edible oils. The component-level geography screen has five rows, each labelled `combined_pool_component`; these are diagnostic rows, not five separate index items or five separate active gate verdicts. The actual `proxy_validation.csv` contains a single pooled F008 result (150 overlaps, B+C pass; R² .961, slope 1.315, recent drift .032).
- **F025** remains on `mandi_gondal`; no DoCA Rajkot switch replaced it.
- **F009** remains on the Amul milk tariff. Rajkot-shop feeds for **F001/F004/F007/F016** remain assigned and accruing; their configured source switch begins Nov 2026, so they were not displaced by the DoCA changes.
- The 34-row `data/official/doca_panel_screen.csv` reports individual commodity diagnostics (17 Rajkot, 7 Gujarat, 4 India, 6 with no passing panel). Its `wire_to` field is a screen-level geographic candidate, not the active source-plan assignment; F008 component rows are explicitly scoped as a combined-pool diagnostic.

### F022/F023 official-link rows

F022 and F023 retain `official_link` products in the database schema but have **zero official-link observations** after overlap trimming. Their independent DoCA Rajkot cutoffs are 2014-01, the first month of the CPI splice. Their active DoCA histories contain 3,943 and 3,946 observations respectively; each has 150 comparator-overlap months and passes B+C. This is intentional overlap removal, not lost official history; no official-history backfill was added or needed for the gate/index period.

## 6. Index impact of the DoCA source choice

The counterfactual compares two offline rebuilds of the same Oct 16 bot snapshot: one with the pre-promotion source plan from commit `e9bd945`, and one with the integrated DoCA Rajkot plan/history. This is not a comparison with the older Oct 15 local index or an unrelated published vintage.

| Month | Pre-promotion plan | Current plan | Change |
|---|---:|---:|---:|
| 2026-09 | 108.309 | 108.095 | −0.214 |
| 2026-10 | 108.462 | 108.324 | −0.138 |

The largest absolute monthly index-level difference is **0.950 points in Jul 2026**. The Oct 16 bot's original published October index (108.462) is the pre-promotion baseline; the old Oct 15 value **109.007** was from a different snapshot and also includes the superseded-feed-filter correction, so it is not used here.

Current published headline (`2025-01 = 100`): Oct 2026 **108.32**, MoM **+0.21%**, YoY **+7.17%**; its 90% nowcast band is **107.44–109.21**. Sep 2026 is **108.09**, YoY **+6.94%**.

## 7. Independent weight by division

| Division | Basket weight | Independent weight | Independent share of division |
|---|---:|---:|---:|
| 01 Food & non-alcoholic beverages | 31.11756% | 31.11756% | 100.0% |
| 03 Clothing & footwear | 6.95309% | 6.95309% | 100.0% |
| 04 Housing, water, electricity, fuels | 24.21911% | 24.21911% | 100.0% |
| 05 Household goods & services | 2.00304% | 2.00304% | 100.0% |
| 06 Health | 5.05378% | 3.04214% | 60.2% |
| 07 Transport | 10.34980% | 9.64065% | 93.1% |
| 08 Information & communication | 3.33984% | 2.75055% | 82.4% |
| 09 Recreation & culture | 1.24000% | 0.88385% | 71.3% |
| 10 Education | 4.89470% | 3.62177% | 74.0% |
| 11 Restaurants & accommodation | 6.64580% | 0.89345% | 13.4% |
| 13 Personal care & misc. | 4.18328% | 4.18328% | 100.0% |

## 8. Bucket overrides and superseded local feeds

Three regulated ceilings/rate cards are counted in the **proxy** bucket, not as a direct price actually paid:

| Item | Weight | Reason |
|---|---:|---|
| T004 auto-rickshaw fare | 2.07601% | statutory maximum fare |
| M001 paracetamol 500 mg | 1.52107% | NPPA ceiling, not a shelf transaction |
| D002 cutting chai | 0.89345% | trade-association rate card |

Older local/wholesale feeds remain available for diagnostics but are excluded from the active index/gate where superseded by DoCA series. Current filter details are in `rpi/superseded.py` and `docs/data/proxy_validation.csv`.

## 9. Historical source change — 2026-10-10 Rajkot web shops

The four local web-shop assignments (`F001`, `F004`, `F007`, `F016`) were made before this DoCA integration. They remain in the current plan and are scheduled to become index inputs in Nov 2026; they are not replaced by the DoCA-centre series. The collector stores prices from Rajkot retailers' own web shops, not a broad market panel. A gate failure is handled by the existing switch policy. This section records the Oct 10 decision; the current weights, gate results and headline are in sections 1–7 above.

## 10. 2026-10-16 DoCA history on the preserved daily-bot snapshot

- Used the latest main-repo bot snapshot (`e9bd9455cce702747c2701b6b6992dce65d47ec4`, run `20261016T094753877494Z`) rather than copying the older local database wholesale. Extended only `doca_rajkot` history to 2014-01-01 for gate overlap; balanced-panel `PANEL_START=2025-01-01` and the 2025-01-01 index base remain unchanged.
- Built the CPI2012-to-CPI2024 item splice (9,897 rows, 66 mapped items, 2014-01..2026-09); `validate_proxies()` requires that comparator and fails closed rather than silently using CPI2024-only history.
- A/B/C status is per-leg. B needs at least three paired calendar-aligned 12-month changes but no separate `n >= 24` floor; C needs `n >= 24`, log-level R², slope and last-24-month drift with the exact t-24 anchor. A constant level offset remains admissible. Any passing leg passes the item; without a passing leg, the overall verdict stays pending while any applicable leg remains unevaluable and fails only when all applicable legs have been evaluated and failed.
- F002/F003/F005/F008/F021/F022/F023 are wired to `doca_rajkot` from 2025-01. They pass C (F002) or B+C (the other six). F025 remains on Gondal; the Amul tariff and accruing Rajkot-local shop feeds are retained. F008 pools commodity IDs 17/18/19/20/21 into one matched-SKU item-level gate; the 34-row screen marks the five commodity rows as components, not separate gates.
- Refreshed the public DoCA commodity screen on 2026-10-16: 34 rows, with diagnostic `wire_to` counts 17 Rajkot, 7 Gujarat, 4 India, and 6 no passing panel. Its five F008 components are all tagged `combined_pool_component`.
- F022/F023 `official_link` products remain with zero observations because their independent cutoff is 2014-01, the first month of the DoCA history. No obsolete official observations were reinserted; the final database has 3,943 and 3,946 Rajkot observations for F022/F023, each with 150 comparator months.
- Gate count: **42 active series; 14 pass, 27 pending, 1 fail (R001 trend gate)**. Independent plan weight is 89.30849%; direct + Rajkot retail is 37.59469% (+8.64676 points versus the pre-promotion plan).
- Same-snapshot index effect, compared to an offline rebuild of the Oct 16 bot snapshot under its pre-promotion source plan: Sep **108.309→108.095 (−0.214)**; Oct **108.462→108.324 (−0.138)**; maximum absolute monthly difference **0.950 points in Jul 2026**.
- Warehouse provenance: the Oct 16 bot DB began at 344 products / 9,187 observations / 1,836 raw snapshots. After adding DoCA Rajkot history it had 355 / 62,950 / 1,836; after the offline rebuild trimmed 40 overlapping official-link observations, the final DB has 355 / 62,910 / 1,836. All non-DoCA source counts match the bot snapshot except `official_link` (814→774; 40 overlaps intentionally trimmed); `data/source_snapshot.json` records commit/run IDs, input DB hashes and the pre-rebuild non-DoCA checksum.
- The preregistration arrival ledger remains bounded to live index-era months from 2025-01. It stamps only newly seen months for existing items and only the latest live-era month for a newly gated item; the CPI2012 splice is not backfilled as if it were a new official release.
- The offline rebuild published as `20261016T115235171390Z`. It flagged the stale R003 register (131 days vs 120-day review), the separate R001 trend gate, and preregistration CUSUM flags for F013/F026; automatic demotion remained off.
- Tests: **336 passed, 2 skipped** in the final full-suite run (6 non-failing warnings). The policy rule, exact C anchor, F008 pooled-item scope and snapshot manifest are covered by tests.

## 11. Reproduce the summary

```bash
python scripts/build_official_spliced.py
python scripts/screen_doca_panels.py   # optional diagnostic; fetches the public DoCA mirror, no API key
python -m rpi refresh --offline        # no network source collectors
python -m pytest -q
```

The offline refresh performs no source fetch. For a narrow gate check, call `validate_proxies()` with `data/official/official_item_spliced.csv`; the gate suite and the F008 pooled-versus-component test live in `tests/test_eighth_sweep.py`, `tests/test_eleventh_sweep.py` and `tests/test_official_spliced.py`.
