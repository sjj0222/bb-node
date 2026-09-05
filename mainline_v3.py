import csv,glob,os,collections
D=collections.defaultdict(list)
for f in sorted(glob.glob("/data/data/com.termux/files/home/odds_data/snapshots/*.csv")):
 t=os.path.basename(f)[9:-4]
 for r in csv.DictReader(open(f,encoding="utf-8-sig")):
  if r["mty"]=="1000": D[(r["match_id"],t,r["market_id"])].append(r)
C=collections.defaultdict(list)
for (mid,t,mi),v in D.items():
 x={r["option_index"]:r for r in v}
 if "1" in x and "2" in x:
  a=float(x["1"]["odds"]);b=float(x["2"]["odds"])
  C[(mid,t)].append((abs(a-1.95)+abs(b-1.95),x["1"]["line"],mi,a,b))
H=collections.defaultdict(list)
for (mid,t),v in C.items(): H[mid].append((t,min(v)))
R=[]
for mid,v in H.items():
 v.sort()
 for i in range(len(v)-1):
  a=v[i][1];b=v[i+1][1]
  if a[1]==b[1]: continue
  fut=[x[1][1] for x in v[i+1:i+5]]
  if not fut: continue
  n=fut.count(b[1])
  back=b[1] if a[1] in fut else ""
  if n>=3 and back=="": typ="REAL"
  elif b[1] in fut and a[1] in fut: typ="NOISE"
  else: typ="LIKELY"
  R.append((mid,a[0],a[1],b[0],b[1],n,typ))
for x in R: print(*x)
print("=== STAT ===")
for k in ["REAL","LIKELY","NOISE"]:
 print(k,sum(x[-1]==k for x in R))
print("TOTAL",len(R))
