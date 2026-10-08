# Rajkot Price Index - 2026-10


- Reference month 2026-08: index **107.32**, YoY **5.44%**
- Latest month 2026-10 (nowcast): index **108.38**  (95% CI 107.46-109.08)
- Nowcast 90% band for 2026-10: **106.91 - 109.86** (split-conformal from a rolling-origin back-test on official data; conservative)
- Month-on-month: **0.16%**
- Year-on-year: **6.8%**
- Directly observed share of CPI weight: **66%** (remainder imputed)

## What is independent vs official-linked
- Official-linked stand-ins (MoSPI Gujarat-urban item indices) fill items with no independent source yet; they run to 2026-08. Their plan weight: 10.8%.
- Independently observed items: 89.2% of weight (observed in latest month 2026-10: 89.2%). Months after 2026-08 are a nowcast: those items are observed; every other item carries its own 12-month mean drift (back-tested one-month-ahead error about 0.6 pp).
- No data at all: 0.0% of weight.

## Robustness variants (latest index level)
| item | level |
|---|---|
| geks_jevons | 108.34 |
| jevons_chain | 108.38 |
| regular_price | 108.38 |

## Divisions (change since base)
| item | % change |
|---|---|
| Personal care & misc. | 22.93 |
| Transport | 13.08 |
| Restaurants & accommodation | 10.63 |
| Education | 10.34 |
| Food & non-alcoholic beverages | 9.15 |
| Information & communication | 7.56 |
| Clothing & footwear | 5.18 |
| Household goods & services | 5.11 |
| Housing, water, electricity, fuels | 4.45 |
| Health | 3.33 |
| Recreation & culture | 2.67 |

_Weights: APPROX: MoSPI CPI2024 all-India urban group shares x Gujarat-urban division weights implied from official indices (ridge lambda=0.001, hold-out RMSE 0.013 idx pts vs 0.133 for all-India weights); within-group weights recovered node by node from the published official index tree (rpi/hierweights.py, blocked-CV ridge, top-down redistribution of unmapped branches); covers 92.8% of basket | price-updated to 2025-01 with official item indices. Run: 20261008T120331648388Z._