# Rajkot Price Index - 2026-10


- Reference month 2026-08: index **107.63**, YoY **5.58%**
- Latest month 2026-10 (nowcast): index **109.68**  (95% CI 107.87-110.76)
- Nowcast 90% band for 2026-10: **107.41 - 112.0** (split-conformal from a rolling-origin back-test on official data; conservative)
- Month-on-month: **0.73%**
- Year-on-year: **7.9%**
- Directly observed share of CPI weight: **24%** (remainder imputed)

## What is independent vs official-linked
- Official-linked stand-ins (MoSPI Gujarat-urban item indices) fill items with no independent source yet; they run to 2026-08. Their plan weight: 42.0%.
- Independently observed items: 56.4% of weight (observed in latest month 2026-10: 56.4%). Months after 2026-08 are a nowcast: those items are observed; every other item carries its own 12-month mean drift (back-tested one-month-ahead error about 0.6 pp).
- No data at all: 1.6% of weight.

## Robustness variants (latest index level)
| item | level |
|---|---|
| geks_jevons | 109.39 |
| jevons_chain | 109.68 |
| regular_price | 109.68 |

## Divisions (change since base)
| item | % change |
|---|---|
| Personal care & misc. | 36.82 |
| Transport | 12.88 |
| Restaurants & accommodation | 11.56 |
| Food & non-alcoholic beverages | 10.67 |
| Education | 10.27 |
| Information & communication | 6.22 |
| Housing, water, electricity, fuels | 5.51 |
| Clothing & footwear | 5.09 |
| Household goods & services | 4.71 |
| Recreation & culture | 2.66 |
| Health | 2.36 |

_Weights: APPROX: MoSPI CPI2024 all-India urban group shares x Gujarat-urban division weights implied from official indices (ridge lambda=0.001, hold-out RMSE 0.013 idx pts vs 0.133 for all-India weights); equal split within group; covers 92.8% of basket | price-updated to 2025-01 with official item indices. Run: 20261006T120042444876Z._