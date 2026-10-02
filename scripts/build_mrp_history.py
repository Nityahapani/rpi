"""Build the archived price history of a fixed pool of Jockey India men's apparel SKUs (item C001 / C002) from the Internet Archive.

Why: Jockey sells at one all-India list price (no per-city pricing) through its own exclusive stores (including Rajkot) and its Shopify
web store, which publishes the same price in its public product JSON (robots.txt allows /products.json and /products/*).  The web store's
history is recoverable from dated Wayback snapshots of each product page, whose embedded variant JSON carries price per size.

Pool rule (fixed in advance, no price-based choice): tag 'Men' and not Women/Juniors/Boys/Girls; product_type T-Shirts or Polos -> C001,
Track Pants or Shorts -> C002; created before 2024-11-01 (so it existed at the base month); at least one Wayback capture of the product page in
2024-11..2025-03; size M variant.  Every product that meets the rule is used (no sampling, no price-based choice).
One Internet Archive CDX prefix query lists all captured product URLs, so no per-product probing is needed (the Archive throttles by IP).

Outputs (resumable): data/mrp/jockey_candidates.csv, data/mrp/jockey_archive_prices.csv  (one row per Wayback snapshot).
"""
from __future__ import annotations
import csv, json, random, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/mrp"; OUT.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (research; rajkot-price-index)"}
DOM = "jockey.in"
POOL_MAX = 20
MAX_PROBES = 110
TYPE_ITEM = {"T-Shirts": "C001", "Polos": "C001", "Track Pants": "C002", "Shorts": "C002"}


def live_products():
    allp = []
    for pg in range(1, 30):
        r = requests.get(f"https://www.{DOM}/products.json?limit=250&page={pg}", headers=H, timeout=60).json()["products"]
        if not r:
            break
        allp += r
    return allp


PAUSE = 1.5          # the Archive throttles by IP (connection resets): stay sequential and back off


def cdx(url, frm, to, collapse="timestamp:6"):
    for k in range(6):
        time.sleep(PAUSE)
        try:
            r = requests.get("http://web.archive.org/cdx/search/cdx", params={"url": url, "from": frm, "to": to, "output": "json", "fl": "timestamp",
                             "filter": "statuscode:200", "collapse": collapse}, headers=H, timeout=90)
            return [x[0] for x in r.json()[1:]]
        except Exception:
            time.sleep(20 * (k + 1))
    return None


def snap(url, ts):
    for k in range(5):
        time.sleep(PAUSE)
        try:
            r = requests.get(f"http://web.archive.org/web/{ts}id_/{url}", headers=H, timeout=90)
            if r.status_code == 200 and len(r.text) > 50000:
                return r.text
            if r.status_code == 404:
                return None
        except Exception:
            time.sleep(20 * (k + 1))
    return None


VAR = re.compile(r'\{"id":(\d+),"price":(\d+),"name":"[^"]*","public_title":(?:"[^"]*"|null),"sku":"([^"]*)"\}')


def parse_prices(html):
    """sku -> price (Rs) from the Shopify analytics variant list embedded in every product page."""
    return {m.group(3): int(m.group(2)) / 100 for m in VAR.finditer(html)}


def eligible(p):
    t = set(p["tags"])
    return ("Men" in t and not t & {"Women", "Juniors", "Boys", "Girls"} and p["product_type"] in TYPE_ITEM
            and p["created_at"] < "2024-11-01" and not re.search(r"boys|girls|women|kids|junior", p["handle"]))


def archive_index():
    """handle -> {YYYYMM: latest capture timestamp in that month} for every jockey.in product page captured since 2024-09."""
    for k in range(6):
        try:
            r = requests.get("http://web.archive.org/cdx/search/cdx", params={"url": f"{DOM}/products/", "matchType": "prefix", "from": "20240901",
                             "to": "20261002", "filter": "statuscode:200", "fl": "original,timestamp", "output": "txt", "limit": 300000}, headers=H, timeout=180)
            r.raise_for_status()
            break
        except Exception:
            time.sleep(20 * (k + 1))
    else:
        raise RuntimeError("CDX prefix query failed")
    idx: dict = {}
    for line in r.text.splitlines():
        try:
            u, ts = line.split()
        except ValueError:
            continue
        h = u.split("/products/")[-1].split("?")[0]
        idx.setdefault(h, {})
        idx[h][ts[:6]] = max(ts, idx[h].get(ts[:6], ""))
    return idx


def main():
    cand_path = OUT / "jockey_candidates.csv"
    idx = archive_index()
    if cand_path.exists():
        cands = list(csv.DictReader(open(cand_path)))
    else:
        cands = []
        for p in live_products():
            m = [v for v in p["variants"] if v["option1"] == "M"]
            ms = idx.get(p["handle"], {})
            if eligible(p) and m and any("202411" <= k <= "202503" for k in ms):
                cands.append(dict(item_id=TYPE_ITEM[p["product_type"]], handle=p["handle"], title=p["title"], product_type=p["product_type"], sku=m[0]["sku"],
                                  variant_id=m[0]["id"], live_price=m[0]["price"], live_compare_at=m[0]["compare_at_price"] or "", created=p["created_at"][:10]))
        with open(cand_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(cands[0])); w.writeheader(); w.writerows(cands)
    print("candidates", len(cands), file=sys.stderr, flush=True)
    arc = OUT / "jockey_archive_prices.csv"
    done = set()
    if arc.exists():
        done = {(r["sku"], r["ts"]) for r in csv.DictReader(open(arc))}
    new = not arc.exists()
    f = open(arc, "a", newline=""); w = csv.writer(f)
    if new:
        w.writerow(["item_id", "handle", "sku", "ts", "price", "snapshot_url"])
    for i, c in enumerate(cands):
        url = f"https://www.{DOM}/products/{c['handle']}"
        for ts in sorted(idx.get(c["handle"], {}).values()):
            if (c["sku"], ts) in done:
                continue
            h = snap(url, ts)
            pr = parse_prices(h).get(c["sku"]) if h else None
            if pr:
                w.writerow([c["item_id"], c["handle"], c["sku"], ts, pr, f"https://web.archive.org/web/{ts}/{url}"]); f.flush()
        print(f"sku {i + 1}/{len(cands)} done", file=sys.stderr, flush=True)
    print("done", file=sys.stderr)


if __name__ == "__main__":
    main()
