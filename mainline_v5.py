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
  fut=lines[i+1:i+6]
  n=fut.count(b[1])
  if not n: continue
  back=a[1] in fut
  later=fut[1:] if len(fut)>1 else []
  stable=later.count(b[1])>=2
  oscill=back and b[1] in later
  ed=eq(a);ne=eq(b)
  if oscill:
   typ="OSCILLATION"
  elif stable and ne<=0.30:
   typ="CONFIRMED"
  else:
   typ="LIKELY"
  di="DEEPER" if depth(b[1])>depth(a[1]) else "SHALLOWER"
  R.append((mid,a[0],a[1],round(ed,2),b[0],b[1],round(ne,2),di,n,typ))
for x in R: print(*x)
print("=== STAT ===")
for k in ["CONFIRMED","LIKELY","OSCILLATION"]:
 print(k,sum(x[-1]==k for x in R))
print("TOTAL",len(R))
