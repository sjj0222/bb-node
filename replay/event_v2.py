import sqlite3,time,hashlib
from events.line import compare_line

DB="data/bb.db"

def h(*x):
 return hashlib.sha256("|".join("" if v is None else str(v) for v in x).encode()).hexdigest()

def main():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute("""create table if not exists replay_events_v2(
 id integer primary key,old_time integer,new_time integer,
 canonical_match_id text,source text,market_type text,period text,
 side text,option text,old_line_raw text,new_line_raw text,
 old_odds real,new_odds real,odds_direction text,
 line_direction text,line_change_type text,event_type text,
 event_hash text unique,created_at integer)""")

 ts=[r[0] for r in c.execute(
  "select distinct received_at from unified_snapshots order by received_at")]
 ts=[x for x in ts if x>1788658122585]

 total=0

 for oldt,newt in zip(ts,ts[1:]):
  A=c.execute("select * from unified_snapshots where received_at=? and canonical_match_id is not null",(oldt,)).fetchall()
  B=c.execute("select * from unified_snapshots where received_at=? and canonical_match_id is not null",(newt,)).fetchall()

  old={}
  for r in A:
   k=(r["source"],r["canonical_match_id"],r["market_type"],
      r["period"],r["side"],r["option"])
   old.setdefault(k,[]).append(r)

  n=0

  for r in B:
   k=(r["source"],r["canonical_match_id"],r["market_type"],
      r["period"],r["side"],r["option"])
   cand=old.get(k,[])
   if not cand: continue

   a=min(cand,key=lambda x:abs((x["line"] or 0)-(r["line"] or 0)))
   od=a["odds"]!=r["odds"]
   lc=str(a["line_raw"])!=str(r["line_raw"])
   info=compare_line(a["line_raw"],r["line_raw"]) if lc else None
   events=[]

   if od: events.append(("WATER_CHANGE",None))
   if info and info["changed"]: events.append(("LINE_CHANGE",info))

   for typ,li in events:
    d=None
    if od:
     d="UP" if r["odds"]>a["odds"] else "DOWN"

    eh=h(r["canonical_match_id"],r["source"],k,
         a["line_raw"],r["line_raw"],a["odds"],
         r["odds"],oldt,newt,typ)

    x=c.execute("""insert or ignore into replay_events_v2(
    old_time,new_time,canonical_match_id,source,market_type,period,
    side,option,old_line_raw,new_line_raw,old_odds,new_odds,
    odds_direction,line_direction,line_change_type,event_type,
    event_hash,created_at)
    values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (oldt,newt,r["canonical_match_id"],r["source"],
     r["market_type"],r["period"],r["side"],r["option"],
     a["line_raw"],r["line_raw"],a["odds"],r["odds"],d,
     li["direction"] if li else None,
     li["change_type"] if li else None,
     typ,eh,int(time.time()*1000)))

    n+=x.rowcount

  total+=n
  print("WINDOW",oldt,newt,"EVENTS",n)

 c.commit()

 print("TOTAL",total)
 for r in c.execute("""select event_type,count(*) n
 from replay_events_v2 group by event_type"""):
  print(r["event_type"],r["n"])

 c.close()

if __name__=="__main__":main()
