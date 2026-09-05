import csv,glob,os
for f in sorted(glob.glob("/data/data/com.termux/files/home/odds_data/snapshots/*.csv")):
 d={}
 for r in csv.DictReader(open(f,encoding="utf-8-sig")):
  if r["match_id"]=="5480974" and r["mty"]=="1000":
   d.setdefault(r["market_id"],{})[r["option_index"]]=r
 z=[]
 for m,x in d.items():
  if "1" in x and "2" in x:
   try:
    a,b=float(x["1"]["odds"]),float(x["2"]["odds"])
    z.append((abs(a-1.95)+abs(b-1.95),x["1"]["line"],x["2"]["line"],a,b,m))
   except: pass
 if z:
  q=min(z)
  print(os.path.basename(f)[9:-4],q[1:])
