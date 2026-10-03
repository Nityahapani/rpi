"""Fetch the Wayback captures listed in data/ceat/captures.csv and parse the schema.org Product JSON-LD (SKU, name, tax-inclusive price).
Resumable; 4 parallel requests, shuffled order (every month is covered early); output data/ceat/sku_prices.csv (ts, url, sku, name, price)."""
import requests, re, json, os, threading, pandas as pd
from concurrent.futures import ThreadPoolExecutor

S = requests.Session(); S.headers["User-Agent"] = "RajkotPriceIndex/0.1 (research; archive reader)"
OUT = "data/ceat/sku_prices.csv"; DONE = "data/ceat/fetched.csv"
cap = pd.read_csv("data/ceat/captures.csv", dtype=str)
done = set()
if os.path.exists(DONE):
    f = pd.read_csv(DONE, dtype=str); done = set(f.ts + f.url)
lock = threading.Lock()


def parse(x):
    out = []
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', x, re.S):
        try: j = json.loads(m.group(1))
        except Exception: continue
        for p in (j if isinstance(j, list) else [j]):
            if isinstance(p, dict) and p.get("@type") == "Product":
                try: out.append((str(p["sku"]), p["name"], float(p["offers"]["price"])))
                except Exception: pass
    return out


def work(r):
    try:
        x = S.get(f"http://web.archive.org/web/{r.ts}id_/{r.url}", timeout=120)
    except Exception as e:
        print("ERR", r.ts, r.url, e, flush=True); return
    if x.status_code != 200:
        print("HTTP", x.status_code, r.ts, r.url, flush=True); return
    rows = parse(x.text)
    with lock:
        pd.DataFrame([dict(ts=r.ts, url=r.url, sku=a, name=b, price=c) for a, b, c in rows]).to_csv(OUT, mode="a", header=not os.path.exists(OUT), index=False)
        pd.DataFrame([dict(ts=r.ts, url=r.url, n=len(rows))]).to_csv(DONE, mode="a", header=not os.path.exists(DONE), index=False)


if __name__ == "__main__":
    todo = [r for _, r in cap.sample(frac=1.0, random_state=7).iterrows() if r.ts + r.url not in done]
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(work, todo))
    print("finished")
