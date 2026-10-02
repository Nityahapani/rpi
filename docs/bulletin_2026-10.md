# Rajkot Price Index - 2026-10


- Reference month 2026-08: index **107.67**, YoY **5.75%**
- Latest month 2026-10 (nowcast): index **109.41**  (bootstrap CI withheld: hybrid index)
- Nowcast 90% band for 2026-10: **107.15 - 111.73** (split-conformal from a rolling-origin back-test on official data; conservative)
- Month-on-month: **0.48%**
- Year-on-year: **7.6%**
- Directly observed share of CPI weight: **17%** (remainder imputed)

## What is independent vs official-linked
- Official-linked stand-ins (MoSPI Gujarat-urban item indices) fill items with no independent source yet; they run to 2026-08. Their plan weight: 59.9%.
- Independently observed items: 38.5% of weight (observed in latest month 2026-10: 38.5%). Months after 2026-08 are a nowcast: those items are observed; every other item carries its own 12-month mean drift (back-tested one-month-ahead error about 0.6 pp).
- No data at all: 1.6% of weight.

## Robustness variants (latest index level)
| item | level |
|---|---|
| geks_jevons | 109.4 |
| jevons_chain | 109.41 |
| regular_price | 109.41 |

## Divisions (change since base)
| item | % change |
|---|---|
| Personal care & misc. | 41.9 |
| Transport | 13.03 |
| Restaurants & accommodation | 11.56 |
| Education | 10.27 |
| Food & non-alcoholic beverages | 9.17 |
| Information & communication | 6.22 |
| Housing, water, electricity, fuels | 5.51 |
| Clothing & footwear | 5.09 |
| Household goods & services | 4.71 |
| Recreation & culture | 2.66 |
| Health | 2.36 |

_Weights: APPROX: MoSPI CPI2024 all-India urban group shares x Gujarat-urban division weights implied from official indices (ridge lambda=0.001, hold-out RMSE 0.013 idx pts vs 0.133 for all-India weights); equal split within group; covers 92.8% of basket | price-updated to 2025-01 with official item indices. Run: 20261002T142115410488Z._