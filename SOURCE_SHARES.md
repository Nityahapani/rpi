# Source shares and the independent share — finalised from the master table (2026-10-08; updated 2026-10-10, see section 9)

Consolidated breakdown of what carries the index weight, computed directly from `registry/items.csv`
(the 67-item master table, added 2026-10-07) using the live bucket rules in `rpi/proxy_check.py`
(`PROXY_SOURCES`, `PROXY_ITEMS`, `RETAIL_SOURCES`, `MODELLED_SOURCES`) plus the master's own
`bucket_override` column. Gate verdicts are joined from the last pipeline run
(`docs/data/status.json -> proxy_validation`).

Nothing reads `registry/items.csv` yet (it is reference-only), so it was first checked against the
things that *do* drive the pipeline. It agrees exactly:

| Check | Result |
|---|---|
| 67 items joined to `data/source_plan.csv` | 0 `primary_source` mismatches, 0 `plan_class` mismatches |
| weights vs `data/weights_cpi2024_gujarat_urban.csv` | 0 mismatches, both sum 100.0000 |
| names / divisions vs `data/basket.csv` | 0 mismatches |
| recomputed plan shares vs published `docs/data/summary.json` | identical to the decimal |

## 1. Headline: independent share

| Class | Weight | Items |
|---|---|---|
| **independent** | **89.2%** | 55 |
| linked (official MoSPI item index used as a stand-in — not independent) | 10.8% | 11 |
| none (no source at all) | 0.003% | 1 (`T005`) |

**Independent = 89.2%** = 70.2% observed prices + 19.0% modelled rent.

## 2. The four independent buckets

| Bucket | Weight | Items |
|---|---|---|
| direct (administered tariff / spot / PNG) | **22.1%** | 11 |
| retail quotes (DoCA Rajkot centre + Rajkot web shops, gated) | **6.8%** | 7 |
| **modelled** (R001 rent, trend-gated) | **19.0%** | 1 |
| proxy (wholesale / national panel / Ahmedabad shelf / regulated ceiling) | **41.2%** | 36 |
| | **89.2%** | 55 |

## 3. Gate status, weighted

| Gate | Weight | Items | Meaning |
|---|---|---|---|
| pass | **34.4%** | 13 | validated against the official item index |
| pending | **28.2%** | 28 | fewer than 6 overlapping months: counted but **unvalidated** |
| n/a | 26.6% | 14 | administered/spot series plus the 3 ceiling items: no gate applies |

Items passing: `F002 F003 F005 F006 F008 F011 F013 F020 F021 F024 F026 R001 E001`.

**65% of the independent weight is either validated or a price that is definitionally the price;
28.2 points are still unvalidated.**

## 4. Source-by-source weight (all 16 sources)

| Source | Weight | Items | What it is |
|---|---|---|---|
| `tariff` | 25.13% | 11 | administered registers: petrol, diesel, LPG, PNG, electricity, water, milk, telecom, OTT, NPPA ceiling, auto fare, chai |
| `rent_signal` | 19.00% | 1 | **MODELLED** rent (Labour Bureau CPI-IW housing ensemble) |
| `dmart_ahmedabad` | 12.22% | 16 | DMart Ready Ahmedabad shelf, fixed SKU pool |
| `official_link` | 10.81% | 11 | **official MoSPI item index fed back in (not independent)** |
| `doca_national` | 9.12% | 7 | DoCA all-India balanced retail panel |
| `vishal_diary` | 6.95% | 3 | Vishal Mega Mart e-store diary |
| `rajkot_shops` | 4.79% | 4 | Rajkot retailers' own web shops (Shopify / WooCommerce feeds); index input from Nov 2026 |
| `frc_rajkot` | 3.62% | 1 | Gujarat FRC approved school fees (Rajkot) |
| `mandi_gondal` | 3.30% | 3 | Gondal veg mandi, wholesale |
| `doca_rajkot` | 2.06% | 3 | DoCA Rajkot-centre retail quotes |
| `gr_metals` | 0.79% | 2 | goodreturns Rajkot gold/silver spot |
| `fresha_salon` | 0.69% | 1 | Fresha salon menu (one venue) |
| `gr_png` | 0.68% | 1 | goodreturns Rajkot PNG |
| `doca_gujarat` | 0.59% | 1 | DoCA Gujarat-centres panel |
| `district_cinema` | 0.24% | 1 | district.in Rajkot cinema diary |
| `none` | 0.003% | 1 | `T005`, genuinely no data |

## 5. Two nuances the master makes precise

### a) Plan share is not the realised share

89.2% is the **plan** figure: the weight of items that have (or are accruing) an independent series.
In the last fully official month, **Aug 2026, only 60.2% of weight was actually independent**; 39.1%
still carried official stand-in observations. The gap is the forward diaries that only began collecting
in Sep/Oct 2026 — 29 items (Vishal x3, 17 DMart items, 3 Gondal mandi, gold/silver, cinema) whose plan
weight is independent but whose history is back-filled by the official index.

| Month | Independent observations |
|---|---|
| 2026-08 (last official month) | **60.2%** |
| 2026-09 | 65.9% |
| 2026-10 (nowcast) | **89.2%** |

Honest reading: the basket is fully wired, and independent data actually reaches that weight from
Sep 2026 onward, growing month by month as the diaries fill in.

### b) Risk concentration

| Pending block | Weight | Note |
|---|---|---|
| `dmart_ahmedabad` | **12.22%** (16 items) | one Ahmedabad shelf-price pool — cannot be gated before ~Mar 2027 |
| `vishal_diary` | 6.95% (3 items) | clothing/footwear e-store |
| `mandi_gondal` | 3.30% (3 items) | **expected to fail** its gate (CEDA back-test, inventory AD) |
| `rajkot_shops` | 4.79% (4 items) | new 2026-10-10; index input from Nov 2026; gate pending until ~Apr 2027 |
| `fresha_salon` / `district_cinema` | 0.93% | one venue / one city |

`dmart_ahmedabad` alone is **12.2% of the index** resting on a single unvalidated proxy from a different
city; the Gondal mandi vegetables (3.3%) are expected to fail when their gate matures (about Mar 2027).

## 6. The two adjustment columns in the master

**`bucket_override = proxy` (3 items, 4.49%)** — forced out of the *direct* bucket into *proxy*, because a
regulated ceiling or an association rate card is not an observed paid price:

| Item | Weight | Why |
|---|---|---|
| `T004` Auto-rickshaw fare | 2.08% | statutory maximum fare, not a paid fare |
| `M001` Paracetamol 500 mg | 1.52% | NPPA ceiling (a cap, not a shelf price) |
| `D002` Cutting chai | 0.89% | trade-association rate card |

**`superseded_local_feeds = Y` (5 items)** — `F003 F005 F020 F021 F024`: their older local wholesale feeds stay
in the database as diagnostics but are excluded from the index, the gate and the cut-offs (DoCA panels took over).

## 7. The 11 official stand-ins (agreement here is circular)

| Item | Weight | Item | Weight |
|---|---|---|---|
| `D003` Street snack plate | 4.50% | `T003` City bus fare | 0.53% |
| `D001` Veg thali | 1.26% | `S003` Newspaper | 0.36% |
| `M003` GP consultation | 1.20% | `T006` Two-wheeler tyre | 0.17% |
| `E002` Tuition fee | 1.18% | `K003` Broadband | 0.12% |
| `M004` Hospital ward | 0.81% | `E004` Photocopy | 0.09% |
| `K002` Smartphone | 0.59% | | |

## 8. Independent share by division

| Division | Total | Independent | Share of division |
|---|---|---|---|
| Food & non-alcoholic beverages | 31.12% | 31.12% | 100% |
| Housing, water, electricity, fuels | 24.22% | 24.22% | 100% |
| Transport | 10.35% | 9.64% | 93% |
| Clothing & footwear | 6.95% | 6.95% | 100% |
| **Restaurants & accommodation** | 6.65% | 0.89% | **13%** |
| Health | 5.05% | 3.04% | 60% |
| Education | 4.89% | 3.62% | 74% |
| Personal care & misc. | 4.18% | 4.18% | 100% |
| Information & communication | 3.34% | 2.63% | 79% |
| Household goods & services | 2.00% | 2.00% | 100% |
| Recreation & culture | 1.24% | 0.88% | 71% |

Weakest coverage is **Restaurants & accommodation at 13%**: the thali / snack-plate cost-push model failed
its gate (corr 0.24 / 0.15), so 5.76 of that division's 6.65 points are official stand-ins.

## Bottom line

**89.2% independent (70.2% observed + 19.0% modelled), 10.8% official stand-in, 0.0% no source.**
Of the 89.2%: **34.4% has passed a gate, 26.6% needs no gate, 28.2% is still pending/unvalidated** —
with 12.2 of those 28.2 points in a single Ahmedabad DMart shelf-price pool and 3.3 points in the Gondal mandi feed
the project's own back-test expects to fail. Realised independent coverage in the last official month
(Aug 2026) was 60.2%, rising to the full 89.2% from Oct 2026 (nowcast) as the diaries accrue.

## 9. Change log 2026-10-10: web-shop switch

Four items now take their index input from the Rajkot web shops, from the November 2026 build (`config/settings.toml` `[index.switches]`, rule in `rpi/switches.py`). Their weight moved between buckets; the independent total did not change.

| Item | Weight | Was | Now |
|---|---|---|---|
| F001 wheat atta | 1.12% | `mandi_rajkot_apmc` (2 months) | `rajkot_shops` |
| F004 moong dal | 0.47% | `mandi_rajkot_apmc` (2 months) | `rajkot_shops` |
| F007 cottonseed oil | 0.07% | `dmart_ahmedabad` (1 month) | `rajkot_shops` |
| F016 turmeric | 3.13% | `dmart_ahmedabad` (1 month) | `rajkot_shops` |

Kept on their gate-passing sources (no switch): F002, F003, F005, F008 on `doca_national` (22 months, passes the India gate); F006, F013, F026 on `doca_rajkot`.

| Bucket | Before | After |
|---|---|---|
| independent | 89.2% | 89.2% |
| direct | 22.1% | 22.1% |
| retail | 2.1% | 6.8% |
| modelled | 19.0% | 19.0% |
| proxy | 46.0% | 41.2% |

Gate totals are unchanged (pass 34.4%, pending 28.2%, n/a 26.6%): the four switched items were already pending. The new source needs about six overlapping months before its gate can be judged (first about Apr 2027); a fail reverts the switch.

Shadow only (collected, screened, not in the index): the web-shop pool for F002/F003/F005/F008; the Apple India iPhone price for K002 (0.59%, still a stand-in); the rent-listings candidate for R001 (waiting for a 50% listing share, about May 2027).

Index effect: the published October figure moved from 108.367 to 108.372 (+0.005), because the 10 Oct shop quotes enter that month's imputation. The first shop-driven month is November 2026.

## Reproduce

```python
import json
import pandas as pd
from rpi.proxy_check import PROXY_SOURCES, PROXY_ITEMS, RETAIL_SOURCES, MODELLED_SOURCES

m = pd.read_csv("registry/items.csv", dtype=str, keep_default_na=False)
m["w"] = m.weight.astype(float)
tot = m.w.sum()

print(m.groupby("plan_class").w.sum() / tot * 100)           # independent 89.2 / linked 10.8 / none 0.0

ind = m[m.plan_class == "independent"]
proxy = ind.primary_source.isin(PROXY_SOURCES) | ind.item_id.isin(PROXY_ITEMS) | (ind.bucket_override == "proxy")
retail = ind.primary_source.isin(RETAIL_SOURCES)
model = ind.primary_source.isin(MODELLED_SOURCES)
print("direct", ind.loc[~proxy & ~retail & ~model, "w"].sum() / tot * 100)
print("proxy ", ind.loc[proxy, "w"].sum() / tot * 100)
print("retail", ind.loc[retail, "w"].sum() / tot * 100)
print("model ", ind.loc[model, "w"].sum() / tot * 100)

val = pd.DataFrame(json.load(open("docs/data/status.json"))["proxy_validation"]).set_index("item_id")
gate = ind.item_id.map(val.verdict).fillna("n/a")
print(ind.groupby(gate).w.sum() / tot * 100)                 # pass 34.4 / pending 28.2 / n/a 26.6
```
