# Rajkot Price Index - 2026-10


- Reference month 2026-08: index **107.32**, YoY **5.44%**
- Latest month 2026-10 (nowcast): index **108.37**  (95% CI 107.59-109.13)
- Nowcast 90% band for 2026-10: **106.91 - 109.85** (split-conformal from a rolling-origin back-test on official data; conservative)
- Month-on-month: **0.16%**
- Year-on-year: **6.8%**
- Weight with a real quote in this vintage, before any imputation: **65.5%** (the rest of this month's basket is filled by the rules below or by an official stand-in - it is NOT the same as the share that is independent of MoSPI)

## What is independent vs official-linked
- Official-linked stand-ins (MoSPI Gujarat-urban item indices) fill items with no independent source yet; they run to 2026-08. Their plan weight: 10.8%.
- Independent of MoSPI (observed, proxied or modelled): 89.2% of plan weight (in the latest month 2026-10: 89.2%). Months after 2026-08 are a nowcast: a trailing gap with no observation is filled by the seasonal-trend prior (long-run mean monthly change plus an empirical-Bayes-shrunk calendar-month deviation from 11 years of official Gujarat-urban data), while interior gaps and items without a seasonal table fall back to the item's own 12-month mean drift. Back-tested one-month-ahead error about 0.6 pp.
- No data at all: 0.0% of weight.

## Robustness variants (latest index level)
| item | level |
|---|---|
| geks_jevons | 108.33 |
| jevons_chain | 108.37 |
| regular_price | 108.37 |

## Divisions (change since base)
| item | % change |
|---|---|
| Personal care & misc. | 23.0 |
| Transport | 13.02 |
| Restaurants & accommodation | 10.63 |
| Education | 10.34 |
| Food & non-alcoholic beverages | 9.15 |
| Information & communication | 7.56 |
| Clothing & footwear | 5.18 |
| Household goods & services | 5.11 |
| Housing, water, electricity, fuels | 4.45 |
| Health | 3.33 |
| Recreation & culture | 2.67 |

_Weights: APPROX: MoSPI CPI2024 all-India urban group shares x Gujarat-urban division weights implied from official indices (ridge lambda=0.001, hold-out RMSE 0.013 idx pts vs 0.133 for all-India weights); within-group weights recovered node by node from the published official index tree (rpi/hierweights.py, blocked-CV ridge, top-down redistribution of unmapped branches); covers 92.8% of basket | price-updated to 2025-01 with official item indices. Run: 20261010T111152661891Z._