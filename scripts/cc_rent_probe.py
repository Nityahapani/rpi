"""Probe Common Crawl for archived copies of the five MagicBricks Rajkot rent list pages (feasibility of a rent history). Bounded: 8 threads, 40 s per request."""
import requests, json, re
from concurrent.futures import ThreadPoolExecutor
S = requests.Session(); S.headers["User-Agent"] = "RajkotPriceIndex/0.1 (research; commoncrawl reader)"
ci = [c["id"] for c in S.get("https://index.commoncrawl.org/collinfo.json", timeout=60).json() if re.match(r"CC-MAIN-202[4-6]", c["id"])]
urls = [f"www.magicbricks.com/{p}-for-rent-in-rajkot-pppfr" for p in ("flats", "independent-house", "1-bhk-flats", "2-bhk-flats", "3-bhk-flats")]
def q(a):
    cid, u = a
    try: r = S.get(f"https://index.commoncrawl.org/{cid}-index", params=dict(url=u, output="json", fl="url,timestamp,status,filename,offset,length"), timeout=40)
    except Exception as e: return (cid, u, "ERR", [])
    out = []
    for l in r.text.splitlines():
        try: j = json.loads(l)
        except Exception: continue
        if "url" in j: out.append(j | {"crawl": cid})
    return (cid, u, r.status_code, out)
with ThreadPoolExecutor(8) as ex: res = list(ex.map(q, [(c, u) for c in ci for u in urls]))
hits = [h for *_, o in res for h in o]
print("queries", len(res), "errors", sum(1 for r in res if r[2] == "ERR"), "hits", len(hits))
for h in hits[:30]: print(h["crawl"], h["timestamp"][:8], h["status"], h["url"][-40:])
pass   # (no hits were found; nothing to save)
