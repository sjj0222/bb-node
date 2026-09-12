import sqlite3,time
from events.engine_v3 import window_events

DB="data/bb.db"

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

  n=0

  for e in window_events(oldt,newt,A,B):
   x=c.execute("""insert or ignore into replay_events_v2(
   old_time,new_time,canonical_match_id,source,market_type,period,
   side,option,old_line_raw,new_line_raw,old_odds,new_odds,
   odds_direction,line_direction,line_change_type,event_type,
   event_hash,created_at)
   values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
   (e["old_time"],e["new_time"],e["canonical_match_id"],e["source"],
    e["market_type"],e["period"],e["side"],e["option"],
    e["old_line_raw"],e["new_line_raw"],e["old_odds"],e["new_odds"],
    e["odds_direction"],e["line_direction"],e["line_change_type"],
    e["event_type"],e["event_hash"],int(time.time()*1000)))

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
