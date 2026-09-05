exec(open("mainline_v3.py").read().split("R=[]")[0])

def eq(x):
 return abs(x[3]-1.95)+abs(x[4]-1.95)

def depth(s):
 p=str(s).replace("+","")
 if "/" in p:
  a,b=p.split("/")
  a=float(a);b=float(b)
  if not str(p.split("/")[1]).startswith(("+","-")): b=-abs(b) if a<0 else abs(b)
  return (abs(a)+abs(b))/2
 return abs(float(p))

R=[]
for mid,v in H.items():
 v.sort()
 lines=[x[1][1] for x in v]
 for i in range(len(v)-1):
  a=v[i][1];b=v[i+1][1]
  if a[1]==b[1]: continue
  fut=lines[i+1:i+11]
  if len(fut)<5: typ="EDGE"
  else:
   nb=fut.count(b[1]); oa=fut.count(a[1])
   first_old=next((j for j,x in enumerate(fut) if x==a[1]),99)
   first_new=next((j for j,x in enumerate(fut) if x==b[1]),99)
   if oa>0 and first_old<8:
    typ="OSCILLATION"
   elif nb>=7 and oa==0 and eq(b)<=0.30:
    typ="CONFIRMED"
   else:
    typ="LIKELY"
  di="DEEPER" if depth(b[1])>depth(a[1]) else "SHALLOWER"
  R.append((mid,a[0],a[1],b[0],b[1],di,typ))
for x in R: print(*x)
print("=== STAT ===")
for k in ["CONFIRMED","LIKELY","OSCILLATION","EDGE"]:
 print(k,sum(x[-1]==k for x in R))
print("TOTAL",len(R))
