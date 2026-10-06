# Rajkot Price Index - 2026-10


- Reference month 2026-08: index **107.63**, YoY **5.58%**
- Latest month 2026-10 (nowcast): index **109.5**  (95% CI 108.07-110.23)
- Nowcast 90% band for 2026-10: **107.83 - 111.19** (split-conformal from a rolling-origin back-test on official data; conservative)
- Month-on-month: **0.52%**
- Year-on-year: **7.73%**
- Directly observed share of CPI weight: **24%** (remainder imputed)

## What is independent vs official-linked
- Official-linked stand-ins (MoSPI Gujarat-urban item indices) fill items with no independent source yet; they run to 2026-08. Their plan weight: 42.0%.
- Independently observed items: 56.4% of weight (observed in latest month 2026-10: 56.4%). Months after 2026-08 are a nowcast: those items are observed; every other item carries its own 12-month mean drift (back-tested one-month-ahead error about 0.6 pp).
- No data at all: 1.6% of weight.

## Robustness variants (latest index level)
| item | level |
|---|---|
| geks_jevons | 109.37 |
| jevons_chain | 109.5 |
| regular_price | 109.5 |

## Divisions (change since base)
| item | % change |
|---|---|
| Personal care & misc. | 37.18 |
| Transport | 12.87 |
| Restaurants & accommodation | 11.38 |
| Education | 9.86 |
| Food & non-alcoholic beverages | 9.64 |
| Information & communication | 6.19 |
| Housing, water, electricity, fuels | 6.08 |
| Clothing & footwear | 5.21 |
| Household goods & services | 4.99 |
| Recreation & culture | 3.07 |
| Health | 2.74 |

_Weights: APPROX: MoSPI CPI2024 all-India urban group shares x Gujarat-urban division weights implied from official indices (ridge lambda=0.001, hold-out RMSE 0.013 idx pts vs 0.133 for all-India weights); equal split within group; covers 92.8% of basket | price-updated to 2025-01 with official item indices. Run: 20261006T183230295952Z._