"""Harvest DMart Ready (Ahmedabad store 10681) category listings for the candidate basket items -> data/dmart/candidates.csv.
One-off helper used to CHOOSE the fixed SKU pool (scripts/build_dmart_pool.py).  4 s between requests, no retries, stops on any non-200.
Run: python3 scripts/dmart_harvest.py"""
import requests, time, pandas as pd, sys
S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0 (compatible; RajkotPriceIndex/1.0; research)","Accept":"application/json","Origin":"https://www.dmart.in","Referer":"https://www.dmart.in/"})
CATS={"F007":["240277"],"F010":["240892"],"F012":["240287","240264"],"F014":["240879"],"F015":["240235"],"F016":["240272"],"F017":["240329","240331","240332"],"F018":["240324"],"F019":["240318"],
"H001":["240857"],"H002":["240855"],"H003":["241183","241175"],"H004":["241246"],"P001":["241101"],"P002":["241106"],"P003":["241125"],"M002":["240864"],"E003":["240915"]}
ONLY=sys.argv[1:]            # optional: harvest only these items and merge into the existing candidates.csv
rows=[]; n=0
for it,cids in CATS.items():
    if ONLY and it not in ONLY: continue
    for cid in cids:
        page=1
        while True:
            r=S.get(f"https://digital.dmart.in/api/v3/plp/{cid}",params=dict(page=page,size=40,channel="web",storeId=10681),timeout=40); n+=1
            if r.status_code!=200: print("STOP",it,cid,page,r.status_code); break
            j=r.json(); prods=j.get("products",[]); tot=j.get("totalRecords",0)
            for p in prods:
                for s in p.get("sKUs",[]):
                    rows.append(dict(item=it,cat=cid,brand=p.get("manufacturer"),pname=p.get("name"),pid=p.get("productId"),sku=s.get("skuUniqueID"),name=s.get("name"),mrp=float(s.get("priceMRP") or 0),sale=float(s.get("priceSALE") or 0),inv=s.get("invStatus"),buy=s.get("buyable"),var=s.get("variantTextValue")))
            time.sleep(4)
            if len(prods)<40 or page*40>=tot: break
            page+=1
        print(it,cid,"requests so far",n,"rows",len(rows),flush=True)
d=pd.DataFrame(rows)
if ONLY:
    old=pd.read_csv("data/dmart/candidates.csv"); d=pd.concat([old[~old.item.isin(ONLY)],d],ignore_index=True)
d.to_csv("data/dmart/candidates.csv",index=False); print(len(d), d.groupby("item").sku.nunique().to_dict())
