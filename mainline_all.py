import csv,glob,os,collections
D=collections.defaultdict(list)
for f in sorted(glob.glob("/data/data/com.termux/files/home/odds_data/snapshots/*.csv")):
 for r in csv.DictReader(open(f,encoding="utf-8-sig")):
  if r["mty"]=="1000":
   D[(r["match_id"],os.path.basename(f)[9:-4],r["market_id"])].append(r)
C=collections.defaultdict(list)
for (mid,t,mi),v in D.items():
 x={r["option_index"]:r for r in v}
 if "1" in x and "2" in x:
  a=float(x["1"]["odds"]);b=float(x["2"]["odds"])
  C[(mid,t)].append((abs(a-1.95)+abs(b-1.95),x["1"]["line"],x["2"]["line"],a,b,mi))
n=0
for k,v in C.items():
 q=min(v)
 if n<30: print(k,q[1:])
 n+=1
print("pairs:",len(C))

P={}
print("=== LINE CHANGES ===")
for k,v in C.items():
 q=min(v); mid,t=k; line=q[1]
 if mid in P and P[mid][1]!=line:
  print(mid,P[mid][0],P[mid][1],"->",t,line)
 P[mid]=(t,line)
S=0;K=0
for mid,t in sorted(C):
 q=min(C[(mid,t)])
 if mid in P and t>P[mid][0]:
  K+=1
  if q[1]==P[mid][1]: S+=1
print("same:",S,"/",K,"rate:",round(S/K*100,2) if K else 0)
