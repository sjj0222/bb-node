import csv,glob,os
old={}
for f in sorted(glob.glob('/data/data/com.termux/files/home/odds_data/snapshots/*.csv')):
 t=os.path.basename(f)[9:-4]; cur={}
 for r in csv.DictReader(open(f,encoding='utf-8-sig')):
  k=(r['match_id'],r['mty'],r['pe'],r['option_index'])
  cur.setdefault(k,set()).add(r['line'])
 for k,v in cur.items():
  if k in old:
   add=v-old[k]; rem=old[k]-v
   if add or rem:
    print(t,k,'消失',rem,'出现',add)
  old[k]=v
