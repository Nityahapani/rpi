# Rajkot Price Index - 2026-10


- Reference month 2026-08: index **107.35**, YoY **5.49%**
- Latest month 2026-10 (nowcast): index **108.74**  (95% CI 108.1-109.27)
- Nowcast 90% band for 2026-10: **107.27 - 110.23** (split-conformal from a rolling-origin back-test on official data; conservative)
- Month-on-month: **0.44%**
- Year-on-year: **7.21%**
- Directly observed share of CPI weight: **35%** (remainder imputed)

## What is independent vs official-linked
- Official-linked stand-ins (MoSPI Gujarat-urban item indices) fill items with no independent source yet; they run to 2026-08. Their plan weight: 30.7%.
- Independently observed items: 69.3% of weight (observed in latest month 2026-10: 69.3%). Months after 2026-08 are a nowcast: those items are observed; every other item carries its own 12-month mean drift (back-tested one-month-ahead error about 0.6 pp).
- No data at all: 0.0% of weight.

## Robustness variants (latest index level)
| item | level |
|---|---|
| geks_jevons | 108.71 |
| jevons_chain | 108.74 |
| regular_price | 108.74 |

## Divisions (change since base)
| item | % change |
|---|---|
| Personal care & misc. | 22.6 |
| Transport | 13.03 |
| Restaurants & accommodation | 10.63 |
| Education | 10.34 |
| Food & non-alcoholic beverages | 9.71 |
| Information & communication | 7.56 |
| Housing, water, electricity, fuels | 5.33 |
| Clothing & footwear | 5.18 |
| Household goods & services | 5.11 |
| Health | 3.33 |
| Recreation & culture | 2.67 |

_Weights: APPROX: MoSPI CPI2024 all-India urban group shares x Gujarat-urban division weights implied from official indices (ridge lambda=0.001, hold-out RMSE 0.013 idx pts vs 0.133 for all-India weights); within-group weights recovered node by node from the published official index tree (rpi/hierweights.py, blocked-CV ridge, top-down redistribution of unmapped branches); covers 92.8% of basket | price-updated to 2025-01 with official item indices. Run: 20261006T193248363875Z._