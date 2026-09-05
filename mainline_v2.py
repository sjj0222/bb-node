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
  C[(mid,t)].append((abs(a-1.95)+abs(b-1.95),x["1"]["line"],mi))
H=collections.defaultdict(list)
for (mid,t),v in C.items(): H[mid].append((t,min(v)))
S=K=0
for mid,v in H.items():
 v.sort()
 for i in range(len(v)-1):
  a=v[i][1][1];b=v[i+1][1][1]
  K+=1
  if a==b:S+=1
print("matches:",len(H),"transitions:",K,"same:",S,"rate:",round(S/K*100,2) if K else 0)
print("=== CANDIDATES ===")
for mid,v in H.items():
 v.sort()
 for i in range(len(v)-1):
  a=v[i][1];b=v[i+1][1]
  if a[1]!=b[1]:
   print(mid,v[i][0],a[1],a[2],"->",v[i+1][0],b[1],b[2])
