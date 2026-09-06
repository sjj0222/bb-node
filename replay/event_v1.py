import sqlite3,time,hashlib
from events.line import compare_line

DB="data/bb.db"

def h(*x):
 return hashlib.sha256("|".join("" if v is None else str(v) for v in x).encode()).hexdigest()

def replay(c,oldt,newt):
 A=c.execute("select * from unified_snapshots where received_at=? and canonical_match_id is not null",(oldt,)).fetchall()
 B=c.execute("select * from unified_snapshots where received_at=? and canonical_match_id is not null",(newt,)).fetchall()

 old={}
 for r in A:
  k=(r["source"],r["canonical_match_id"],r["market_type"],r["period"],r["side"],r["option"])
  old.setdefault(k,[]).append(r)

 n=0
 for r in B:
  k=(r["source"],r["canonical_match_id"],r["market_type"],r["period"],r["side"],r["option"])
  cand=old.get(k,[])
  if not cand: continue
  a=min(cand,key=lambda x:abs((x["line"] or 0)-(r["line"] or 0)))

  od=a["odds"]!=r["odds"]
  lc=str(a["line_raw"])!=str(r["line_raw"])
  info=compare_line(a["line_raw"],r["line_raw"]) if lc else None

  if od:
   n+=1
  if info and info["changed"]:
   n+=1
 return n

def main():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row

 c.execute("""create table if not exists replay_events_v1(
 id integer primary key,old_time integer,new_time integer,
 event_count integer,created_at integer,
 replay_hash text unique)""")

 ts=[r[0] for r in c.execute(
  "select distinct received_at from unified_snapshots order by received_at")]

 ts=[x for x in ts if x>1788658122585]

 total=0
 for a,b in zip(ts,ts[1:]):
  n=replay(c,a,b)
  total+=n
  hsh=h(a,b,n)
  c.execute("""insert or ignore into replay_events_v1
  (old_time,new_time,event_count,created_at,replay_hash)
  values(?,?,?,?,?)""",(a,b,n,int(time.time()*1000),hsh))
  print("WINDOW",a,b,"EVENTS",n)

 c.commit()
 print("TOTAL",total)
 c.close()

if __name__=="__main__":main()
