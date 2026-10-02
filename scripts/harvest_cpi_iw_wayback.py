import json,re,subprocess,time,sys
def curl(u,tries=5):
    for i in range(tries):
        r=subprocess.run(["curl","-s","-m","90","-A","Mozilla/5.0 RajkotPriceIndexBot/0.1","-L","-w","\n%{http_code}",u],capture_output=True)
        out=r.stdout.decode('utf8','ignore')
        body,_,code=out.rpartition("\n")
        if code=="200" and len(body)>1000: return body
        time.sleep(3)
    return None
cdx=curl("https://web.archive.org/cdx/search/cdx?url=labourbureau.gov.in&output=json&filter=statuscode:200&collapse=timestamp:8&from=20241001&limit=600")
caps=[x[1:3] for x in json.loads(cdx)[1:]]
print(len(caps),'captures')
M3=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
res={}; fails=[]
for ts,orig in caps:
    h=curl(f"https://web.archive.org/web/{ts}id_/{orig}")
    if not h: fails.append(ts); continue
    t=re.sub(r'<script.*?</script>|<style.*?</style>','',h,flags=re.S); t=re.sub(r'<[^>]+>',' ',t); t=re.sub(r'\s+',' ',t)
    m=re.search(r'GUJARAT Centre Name (\w+) - (\d{4}) (\w+) - (\d{4})(.{0,200}?)Rajkot (\d{2,3}\.\d) (\d{2,3}\.\d)',t)
    if not m: fails.append(ts+'?'); continue
    p1=f"{m.group(2)}-{M3.index(m.group(1)[:3])+1:02d}"; p2=f"{m.group(4)}-{M3.index(m.group(3)[:3])+1:02d}"
    # also all Gujarat centres
    seg=t[t.find('GUJARAT Centre Name'):][:400]
    cs={}
    for c in ['Ahmedabad','Bhavnagar','Rajkot','Surat','Vadodara']:
        mm=re.search(rf'{c} (\d{{2,3}}\.\d) (\d{{2,3}}\.\d)',seg)
        if mm: cs[c]=(float(mm.group(1)),float(mm.group(2)))
    res[ts]=dict(p1=p1,p2=p2,centres=cs)
    print(ts,p1,p2,cs.get('Rajkot'),flush=True)
json.dump(dict(res=res,fails=fails),open('cpiiw_harvest.json','w'),indent=1)
print('fails',fails)
