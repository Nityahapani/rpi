# Instamart Rajkot: a Rajkot retail shelf for packaged goods

> **Status 2026-11-21: collector built and unit-tested, NOT WIRED.** No item is routed to this source in
> `data/source_plan.csv`, because no pool and no prices have been collected yet: Swiggy rate-limited this
> machine's IP (HTTP 202) after the reconnaissance sessions. The store and its priced tiles were read live; the
> full harvest was not. The figures in this note are the *intended* coverage, not measured coverage — the
> published coverage split still reports the old shelf.

Every packaged good in the basket used to be priced outside Rajkot: DMart Ready serves **no** Rajkot pincode
(`/api/v1/pincodes/search/360001` -> 0 stores on 2026-11-21; 380001 Ahmedabad -> 13), and Vishal is a national e-store.
Swiggy Instamart does serve the city.

## What is used

A headless Chromium is geolocated to 22.3039/70.8022 and the page's own "Use current location" action resolves
**store/pod 1395731 — "Sadar, Rajkot, Gujarat 360001"**. The page then loads `/api/instamart/home/v2?...&storeId=1395731`,
whose product tiles carry, per SKU:

| field | used as |
|---|---|
| `price.offerPrice` | the price a shopper pays |
| `price.mrp` | `regular_price` (the promo-free index variant) |
| `quantityDescription`, `weightInGrams` | pack size -> unit price |
| `inventory.inStock` | out-of-stock SKUs are skipped, never carried forward |
| `podId` | confirms the tile belongs to the Rajkot store (1395731) |

The item series is the matched-model Jevons chain of a fixed SKU pool (`data/instamart/pool.csv`), so pack size, brand
mix and Instamart's own discounting only enter as changes of the *same* SKU.

## Coverage

15 items, **16.4% of basket weight**, moved from the Ahmedabad DMart shelf (12.2%) and the national Vishal e-store (4.2%):

    F014 tea, F017 biscuits, P001 soap, P002 shampoo, P003 toothpaste, H001 detergent,
    H002 dishwash, F018 noodles, F012 ghee, F010 curd, F019 bread, F015 salt,
    H003 bulb, E003 notebook, M002 antiseptic, H004 pressure cooker

Index switch starts **2026-12** (`config/settings.toml [index.switches]`); 2026-11 accrual is the link month the switch
rule keeps. Months before that keep the official stand-in, so the published history does not move.

## To run

    PYTHONPATH=. python3 scripts/build_instamart_pool.py     # once, from the Rajkot store, before any history
    PYTHONPATH=. python3 -m rpi refresh                      # accrues daily, then replays into the index

Accrual needs a machine that can open a browser. The daily runner can ingest the accrued CSV without one.

## Known limit

Swiggy rate-limits an egress IP after roughly a dozen browser sessions (HTTP 202, "We'll be back shortly"). The
collector treats that as a skip, not a failure, and the series simply does not extend that day.
