import csv,glob,os
old={}
for f in sorted(glob.glob('/data/data/com.termux/files/home/odds_data/snapshots/*.csv')):
 t=os.path.basename(f)[9:-4]; cur={}
 for r in csv.DictReader(open(f,encoding='utf-8-sig')):
  k=(r['match_id'],r['mty'],r['pe'])
  i=r['option_index']
  if k[1] in ('1000','1007','1010'):
   cur.setdefault(k,{})[i]=r
 for k,x in cur.items():
  if k in old:
   a,b=old[k],x
   if 1 in a and 2 in a and 1 in b and 2 in b:
    l1,l2=a[1]['line'],a[2]['line']
    n1,n2=b[1]['line'],b[2]['line']
    if (l1,l2)!=(n1,n2):
     print(t,'|',k[0],k[1],'|',l1,'/',l2,'→',n1,'/',n2,'|',a[1]['home'],'vs',a[1]['away'])
  old[k]=x
