exec(open("mainline_v3.py").read().split("R=[]")[0])
R=[]
def dep(s):
 p=str(s).replace("+","")
 if "/" in p:
  a,b=p.split("/")
  x=float(a);y=float(b)
  if y and abs(y)<abs(x): y=x
  return (abs(x)+abs(y))/2
 return abs(float(p))
for mid,v in H.items():
 v.sort()
 for i in range(len(v)-1):
  a=v[i][1];b=v[i+1][1]
  if a[1]==b[1]: continue
  fut=[x[1][1] for x in v[i+1:i+5]]
  n=fut.count(b[1])
  if n<3 or a[1] in fut: continue
  d1=dep(a[1]);d2=dep(b[1])
  direction="DEEPER" if d2>d1 else "SHALLOWER"
  R.append((mid,a[0],a[1],round(a[3],2),round(a[4],2),
            b[0],b[1],round(b[3],2),round(b[4],2),direction,n))
for x in R: print(*x)
print("=== STAT ===")
print("REAL",len(R))
print("DEEPER",sum(x[-2]=="DEEPER" for x in R))
print("SHALLOWER",sum(x[-2]=="SHALLOWER" for x in R))
