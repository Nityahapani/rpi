# Leakage-aware item-model experiments

**Status: research/shadow only. No model was promoted into the published RPI, the DoCA gate, or the frozen prospective ledger.**

Reproduce with:

```bash
python -m econ items-backtest
```

CSV/JSON outputs are written under `econ/outputs/items_backtest/` (ignored by git). The report in this file records the run against the Oct 16, 2026 workspace snapshot.

## Leakage controls

The previous item experiment used published `index_results`, selected rows by checking whether the RPI change differed from the official target, and read the GEKS variant. That can both select on the outcome and let later observations affect early GEKS relatives. This experiment instead:

- Rebuilds item changes from active raw quote observations after applying the repository's superseded-source and switch rules.
- Excludes every `official_link` observation and leaves months with insufficient source quotes missing—there is no official-link backfill or imputation in the feature.
- Uses causal matched-model chain-Jevons changes, the headline elementary method; each monthly feature uses the matched quotes in that month and the immediately prior month, not future GEKS-window observations.
- Retains exact source/official matches. **82 of 505** source item-months happen to match within tolerance; they were not removed by comparing them with the target.
- Uses an expanding outer split: every model is fit using target months strictly before its test month. Huber clipping, identity-shrink weight and recency half-life are selected only in inner expanding folds within that outer training sample.
- Records the maximum `fetched_at` among quotes used for each feature. A separate release replay excludes source observations fetched on or after the date-only official arrival cutoff.

The comparator is `data/official/official_item_spliced.csv`, and the item panel remains bounded at the configured index base (2025-01); the long DoCA history is not treated as pre-2025 published RPI history.

## Data and vintage limitation

The source-only panel contains **505 item-months, 27 items and 20 months** (2025-02 through 2026-09). The repository does not contain real-time input snapshots for most historical origins: many 2025–26 source records in the current archive were fetched during Oct 10–16, 2026, after those historical months' official releases. Therefore the expanding archive results below are **chronological and target-leakage-safe, but not a vintage-safe historical backtest**. They are exploratory and must not be used to claim an out-of-sample accuracy gain.

Only one non-bootstrap official arrival is currently recorded: 2026-09, first seen on 2026-10-16. The strict replay uses a conservative cutoff of 2026-10-16 00:00 UTC, excluding same-day fetches. It has 247 training item-months across 19 months and 13 source-supported test items. Their latest contributing input was fetched 2026-10-14 17:31:31 UTC. This is one matured test month, so the results are descriptive, not statistically conclusive.

## Models

- **Raw**: source-only change, `ŷ = x` (the benchmark).
- **Pooled OLS** and **fixed Huber**: pooled intercept/slope, with Huber `c=1.345` for the fixed version.
- **Nested Huber**: `c ∈ {0.8, 1.0, 1.345, 2.0, 3.0}` selected by month-balanced expanding validation inside each outer training fold, then refit on all outer training data.
- **Identity-shrunk Huber**: blends the fixed-Huber calibration toward the raw identity forecast, `x + γ(ŷ_Huber − x)`, with `γ ∈ {0, .25, .5, .75, 1}` selected inside each outer training fold. `γ=0` is exactly raw.
- **Recency-weighted Huber**: exponential month-age weights, with half-life in `{3, 6, 12, 24, ∞}` selected inside each outer training fold; `∞` means no decay.
- **Robust median offset**: adds the median, across training months, of each month's basket-weighted median `(y−x)` residual. This is a robust bias-only correction.
- **Through-origin Huber**: robustly estimates one pooled slope in `y=βx`, with no intercept.
- **Hierarchical static**: item intercepts and slopes shrunk toward pooled coefficients by `n/(n+10)`; the shrinkage constant is fixed, not selected on test data.
- **Hierarchical state-space**: the same partial-pooling regression plus a common residual state, `u_t = φu_(t−1) + η_t`. State observations are basket-weighted **prequential** errors from prior months; a scalar Kalman filter estimates the AR(1) state and forecasts it one step ahead. The test month's official value is not used.

Metrics are monthly item inflation errors in percentage points. `Basket RMSE/MAE` normalizes official item weights within each month and then gives each test month equal weight. Archive confidence intervals for RMSE gaps use paired 3-month moving-block bootstrap resampling (4,000 replicates); the single strict month has no interval.

## Results

### Archive-based expanding replay — exploratory only

12 outer months (2025-10 through 2026-09), **313 scored item-months**:

| Model | Basket RMSE | Basket MAE | Bias | RMSE gap vs raw | 95% block-bootstrap interval |
|---|---:|---:|---:|---:|---:|
| Raw | 3.498 | 1.082 | −0.095 | — | — |
| Robust median offset | 3.498 | 1.080 | −0.100 | 0.000 | [−0.003, +0.002] |
| Identity-shrunk Huber | 2.974 | 0.961 | +0.087 | −0.525 | [−0.882, −0.212] |
| Recency-weighted Huber | 2.962 | 0.962 | +0.124 | −0.536 | [−0.964, −0.163] |
| Through-origin Huber | 2.938 | 0.971 | +0.212 | −0.560 | [−0.945, −0.244] |
| Pooled OLS | 2.948 | 0.960 | +0.136 | −0.550 | [−0.962, −0.211] |
| Fixed Huber | 2.941 | 0.959 | +0.124 | −0.557 | [−0.975, −0.215] |
| Nested Huber | 2.942 | 0.957 | +0.126 | −0.556 | [−0.971, −0.215] |
| Hierarchical static | 3.123 | 0.983 | +0.181 | −0.375 | [−0.942, +0.064] |
| Hierarchical state-space | 3.134 | 1.035 | +0.273 | −0.365 | [−0.926, +0.068] |

On the archive splits, through-origin Huber has the lowest RMSE (2.938), only marginally below fixed/nested Huber (2.941/2.942); these are all pseudo-OOS results, not real-time accuracy evidence. Inner tuning chose identity blend `γ=.75` in 7 folds and `γ=1` in 5; the recency model chose no decay (`∞`) in 11 of 12 folds. The median-offset correction is effectively indistinguishable from raw. The source-vintage limitation still rules out a winner claim.

### Strict release-date replay — September 2026

| Model | Basket RMSE | Basket MAE | Bias | RMSE gap vs raw |
|---|---:|---:|---:|---:|
| Raw | 3.628 | 2.692 | +0.267 | — |
| Robust median offset | 3.642 | 2.763 | +0.412 | +0.014 |
| Identity-shrunk Huber | 4.793 | 3.190 | +1.482 | +1.165 |
| Through-origin Huber | 5.603 | 3.437 | +2.045 | +1.975 |
| Fixed Huber | 5.628 | 3.356 | +1.887 | +2.000 |
| Nested Huber | 5.628 | 3.356 | +1.887 | +2.000 |
| Recency-weighted Huber | 5.628 | 3.356 | +1.887 | +2.000 |
| Pooled OLS | 6.196 | 3.375 | +1.967 | +2.568 |
| Hierarchical static | 6.772 | 4.064 | +2.294 | +3.144 |
| Hierarchical state-space | 6.913 | 4.269 | +2.682 | +3.285 |

There are **13 item-months in one test month** and no meaningful confidence interval. Nested Huber chose `c=1.345`, identity shrink chose `γ=.75`, and the recency selector chose no decay. The robust median offset was closest to raw but still slightly worse; every fitted-slope alternative was materially worse. The state-space fit estimated `φ≈0.071` and a common one-step residual correction of about **−0.388 percentage points**; adding it made this test worse. This one month cannot establish that raw is generally superior, but it does not validate the archive gains either.

## Decision

**Do not adopt any calibration technique yet.** Through-origin Huber, recency-weighted Huber, and identity-shrunk Huber reduce archive RMSE, but those historical inputs were fetched after many test months; their apparent gains are not real-time evidence. The only strict release month favors raw over every fitted-slope technique, while the robust median offset is nearly tied but slightly worse. One month is not enough to declare a winner in either direction. Keep all methods shadow-only, leave the published index and frozen ledger unchanged, and collect prospectively timestamped forecasts before future official releases. A credible adoption decision needs more independent, vintage-safe monthly origins; the existing ledger's pre-registered rule requires 12 scored months with a paired interval fully below zero.

One related snapshot caveat: the item splice and official-arrival ledger include 2026-09, while the SQLite `official_series` general-index table used by the separate `python -m econ score` command currently ends at 2026-08. This experiment uses the item splice and arrival ledger directly; it does not rewrite that general-index table or alter the existing prospective ledger.
