# R001 rent signal (v1 -> v3): notes (mirrors inventory section AJ)

Public data only (Labour Bureau CPI-IW housing group): all-India half-year levels 2020H2-2026H2 and a 78-centre panel 2020H2-2023H1 (`centre_housing.csv`; none later is published by centre).
Code: `rpi/rentsignal.py`. Outputs: `data/official/rent_signal_*.csv|json`, `rent_monthly_info_search.csv`. Tests: `tests/test_rentsignal.py`.

- v1 constant ratio 0.354: YoY 1.47% vs official 2.43%.  v2 Kalman time-varying ratio (chosen after v1 failed): beta 0.539, YoY 2.25%.
- v3 = mean of E4 (additive deviation shrunk to the all-centre mean, empirical Bayes) and E5 (pooled-parameter Kalman ratio). Selection rule declared before comparing with MoSPI: keep panel-scored models that beat the all-India-step baseline on one-step RMSE over 78 centres x 3 origins (all-India 1.435; E1 1.642; E3 1.481; E4 1.375; E5 1.422 pp). Rajkot mean abs error: all-India 1.03, E4 0.15, E5 0.18.
- v3 steps (pp/half): 2025H1 1.21, 2025H2 1.23, 2026H1 1.09, 2026H2 0.80.
- Gate screen n=20 (2025-01..2026-08): v3 YoY 2.18% vs 2.43%, cum 3.59% vs 3.85%, drift 0.003, corr -0.21 -> FAIL (corr only). All-five equal weight: 2.02% / 3.33% / 0.005 / -0.21.
- Monthly-information search: 52 items + Rajkot CPI-IW general vs official monthly rent changes: max corr 0.61; chance max over 53 series (n=19) median 0.56, 95th pct 0.69. Nothing beyond chance.
- Gate ceiling (`gate_ceiling`): official monthly rent changes average 0.203%, sd 0.071, lag-1 autocorr 0.10 (mostly noise around a flat trend). Corr with v3 staircase -0.21, v3 linearly interpolated -0.30, and the official series' OWN linear time trend (in-sample oracle) only 0.24. So no trend-type signal, however accurate, can reach corr >= 0.5; only a signal that sees the monthly noise can, and that information exists only in the official series.
- Decision: R001 stays `official_link`; independent share stays 70.2%. Wiring needs a user decision to adopt a trend-only gate for rent.

## v4: calibrated trend gate (candidate, NOT adopted; R001 only)
- The existing drift cap (0.10 log points = 10 pp) is far looser than the whole 19-month official rent change (3.85 pp): "corr dropped, drift kept" would pass a flat signal (it does: drift 0.039) and all-India housing. A trend gate therefore needs a tolerance with a stated basis.
- Rule (`trend_gate`, z fixed in advance at 1.645): official monthly sd s = 0.071 pp is noise no independent signal can track; accept if |cumulative gap| <= z*s*sqrt(19) = 0.51 pp and |last-12-month gap| <= z*s*sqrt(12) = 0.41 pp.
- Results (gap in pp, cum / 12m): flat -3.85 / -2.43 fail; v1 -1.44 / -0.96 fail; v2 -0.19 / -0.19 pass; **v3 panel-selected -0.26 / -0.25 pass**; v3 all-five equal weight -0.52 / -0.41 fail (marginal); all-India housing +2.95 / +1.74 fail.
- Operating characteristics (cumulative test): P(accept) = 0.90 for a perfect signal (10% false rejection), 0.51 at 0.5 pp true trend error, 0.056 at 1.0 pp, 0.001 at 1.5 pp. It detects trend errors above roughly 1 pp over 19 months (about 0.6 pp a year).
- Caveats: it was designed after the corr gate failed (post hoc); the tolerance has no tuned parameter except z; it checks level/trend only, not monthly timing; cumulative noise assumed iid (lag-1 autocorr 0.10).

## Wired 2026-10-06 (user decision): R001 `rent_signal`, MODELLED, trend-gated
- `data/source_plan.csv` R001: `rent_signal`, class independent. Collector `rpi/collectors/rent_signal.py` (v3 panel-selected ensemble, 2025-01 to the end of the last housing half, never extrapolated; needs a new Labour Bureau half-year row each Jan/Jul in `data/labour_bureau/housing_group.csv`, otherwise the series stops after 2026-12 and the item is imputed). Registered in BACKFILL_SOURCES (official back-fills before 2025-01), SINGLE_SERIES_SOURCES, GATED_SOURCES, MODELLED_SOURCES (own bucket, not PROXY_SOURCES).
- Gate: `proxy_check.validate_proxies` routes modelled sources to `rentsignal.judge_trend` (trend gate, z = 1.645, pending below 14 overlapping months); every refresh re-gates, a fail surfaces as the usual "PROXY FAILS VALIDATION" error. The correlation gate is unchanged for every other item.
- Before/after (offline refresh, run 20261006T221856254671Z): independent plan share 70.2% -> 89.2% (modelled bucket 19.0%, observed/proxy 70.2%). Published index Aug 2026 107.365 -> 107.316 (YoY 5.49% -> 5.44%); Oct 2026 108.576 -> 108.363 (MoM 0.28% -> 0.15%, YoY 7.03% -> 6.79%). R001 gate in the run: pass, n=20, cumulative gap -0.26 pp (tol 0.51), 12-month gap -0.25 pp (tol 0.41). The Sep/Oct 2026 R001 values are now the model, not a peer-imputed nowcast.
- Honest labelling: this is a MODEL calibrated on Labour Bureau housing data, not observed rents; the gate was changed for R001 after the correlation gate failed (post hoc, disclosed); gate power only detects trend errors above about 1 pp over 19 months; monthly timing within each half is a flat run-rate.
- Review triggers: Sep 2026 MoSPI (mid-Oct 2026) adds a 21st month to the gate; if the trend gate fails, R001 reverts to `official_link` (edit the plan row, rerun refresh).
