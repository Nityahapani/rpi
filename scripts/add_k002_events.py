"""K002 (smartphone) event checks, sweep 16. RUN ONCE (appends rows to data/official/event_checks.csv).

Dated manufacturer MRP changes for FIXED models. The official 'Mobile handset' index is quality-adjusted, so a matched-model list-price change
is expected to pass through only partly; the point of the check is to measure how much. DIAGNOSTIC ONLY: nothing here feeds the index.
Why no register: Samsung quotes mix MRP, 'list', 'offer' and with/without-charger prices (androidpure 6 Sep 2026), so no clean MRP path exists;
a single-model Apple path fails the drift gate against the official index (see data/official/source_inventory_2026-10-02.md section T).
"""
import csv
from pathlib import Path

P = Path("data/official/event_checks.csv")
rows = [
 ("K002", "Apple iPhone 16 128 GB India MRP 79,900 -> 69,900 (iPhone 17 launch repricing)", "2025-09-09", round((69900/79900-1)*100, 2),
  "https://www.gadgets360.com/mobiles/news/iphone-16-price-drop-india-after-iphone-17-launch-9248481",
  "Apple India website as quoted by Gadgets360 (10 Sep 2025)", "verified",
  "Fixed model, manufacturer MRP. Official handset index is hedonic, so muted pass-through is expected"),
 ("K002", "Samsung Galaxy A56 5G 8/128 GB MRP 38,999 -> 40,999 (A36 +1,500, F17 +1,000 same day)", "2026-01-05", round((40999/38999-1)*100, 2),
  "https://www.gizmochina.com/2026/01/05/samsung-galaxy-a-f-series-price-hike-india-2026/",
  "Samsung trade price-revision memo via tipster; Gizmochina and 91mobiles 5 Jan 2026", "corroborated",
  "List-price revision; online listings lagged (91mobiles). Samsung quotes mix MRP/list/offer, so only this one pair is used"),
 ("K002", "Apple iPhone 16 128 GB India MRP 69,900 -> 89,900 (older iPhones repriced after iPhone 18 launch)", "2026-09-10", round((89900/69900-1)*100, 2),
  "https://www.indiatoday.in/technology/news/story/iphone-17-india-price-increased-by-rs-17000-with-immediate-effect-here-is-new-price-2991284-2026-09-10",
  "India Today, Mobigyaan, Beebom, GadgetBridge, IBTimes 10 Sep 2026 (TOI and Business Standard print 79,900 as the old price; that is the 2024 launch price, superseded by the Sep 2025 cut)", "verified",
  "Takes effect immediately. Official Oct 2026 index (due mid-Nov) is the first test"),
]
have = {(r["item_id"], r["effective_from"]) for r in csv.DictReader(P.open())}
with P.open("a", newline="") as f:
    w = csv.writer(f)
    for r in rows:
        if (r[0], r[2]) not in have:
            w.writerow(r)
