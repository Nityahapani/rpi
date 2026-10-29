# Rajkot Price Index - 2026-10


- Reference month 2026-09: index **108.09**, YoY **6.94%**
- Latest month 2026-10 (nowcast): index **108.3**  (95% CI 107.73-109.79)
- Nowcast 90% band for 2026-10: **107.42 - 109.19** (split-conformal from a rolling-origin back-test on official data; conservative)
- Month-on-month: **0.19%**
- Year-on-year: **7.14%**
- Weight with a real quote in this vintage, before any imputation: **65.5%** (the rest of this month's basket is filled by the rules below or by an official stand-in - it is NOT the same as the share that is independent of MoSPI)

## What is independent vs official-linked
- Official-linked stand-ins (MoSPI Gujarat-urban item indices) fill items with no independent source yet; they run to 2026-09. Their plan weight: 10.7%.
- Independent of MoSPI (observed, proxied or modelled): 89.3% of plan weight (in the latest month 2026-10: 89.3%). Months after 2026-09 are a nowcast: a trailing gap with no observation is filled by the seasonal-trend prior (long-run mean monthly change plus an empirical-Bayes-shrunk calendar-month deviation from 11 years of official Gujarat-urban data), while interior gaps and items without a seasonal table fall back to the item's own 12-month mean drift. Back-tested one-month-ahead error about 0.6 pp.
- No data at all: 0.0% of weight.

## Robustness variants (latest index level)
| item | level |
|---|---|
| geks_jevons | 108.28 |
| jevons_chain | 108.3 |
| regular_price | 108.3 |

## Divisions (change since base)
| item | % change |
|---|---|
| Personal care & misc. | 22.23 |
| Transport | 13.04 |
| Restaurants & accommodation | 11.61 |
| Education | 10.29 |
| Food & non-alcoholic beverages | 8.74 |
| Information & communication | 8.06 |
| Clothing & footwear | 5.48 |
| Household goods & services | 5.39 |
| Housing, water, electricity, fuels | 4.45 |
| Health | 3.08 |
| Recreation & culture | 2.1 |

_Weights: APPROX: MoSPI CPI2024 all-India urban group shares x Gujarat-urban division weights implied from official indices (ridge lambda=0.001, hold-out RMSE 0.013 idx pts vs 0.133 for all-India weights); within-group weights recovered node by node from the published official index tree (rpi/hierweights.py, blocked-CV ridge, top-down redistribution of unmapped branches); covers 92.8% of basket | price-updated to 2025-01 with official item indices. Run: 20261029T113459790169Z._