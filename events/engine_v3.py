import sqlite3,time,hashlib
from events.line import compare_line
from core.log import start,finish,error

DB="data/bb.db"

def h(*x):
 s="|".join("" if v is None else str(v) for v in x)
 return hashlib.sha256(s.encode()).hexdigest()

def main():
 log_id=start("EVENT","unified")
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute("""create table if not exists events_v3(
 id integer primary key,canonical_match_id text,source text,
 source_match_id text,market_type text,period text,side text,
 option text,old_line_raw text,new_line_raw text,old_odds real,
 new_odds real,odds_direction text,line_direction text,
 line_change_type text,event_type text,old_time integer,new_time integer,
 event_hash text unique,created_at integer)""")
 rows=c.execute("""select * from unified_snapshots
 where canonical_match_id is not null
 order by received_at,id""").fetchall()
 ts=sorted(set(r["received_at"] for r in rows))
 if len(ts)<2:
  finish(log_id,"OK",len(rows),0,"需要至少2个时间点")
  print("需要至少2个时间点");return
 oldt,newt=ts[-2:]
 A=[r for r in rows if r["received_at"]==oldt]
 B=[r for r in rows if r["received_at"]==newt]
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
   if od: d="UP" if r["odds"]>a["odds"] else "DOWN"
   eh=h(r["canonical_match_id"],r["source"],k,a["line_raw"],
        r["line_raw"],a["odds"],r["odds"],oldt,newt,typ)
   x=c.execute("""insert or ignore into events_v3
   (canonical_match_id,source,source_match_id,market_type,period,side,
    option,old_line_raw,new_line_raw,old_odds,new_odds,odds_direction,
    line_direction,line_change_type,event_type,old_time,new_time,
    event_hash,created_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
   (r["canonical_match_id"],r["source"],r["source_match_id"],
    r["market_type"],r["period"],r["side"],r["option"],
    a["line_raw"],r["line_raw"],a["odds"],r["odds"],d,
    li["direction"] if li else None,li["change_type"] if li else None,
    typ,oldt,newt,eh,int(time.time()*1000)))
   n+=x.rowcount
 c.commit()
 finish(log_id,"OK",len(rows),n,"T1=%s T2=%s" % (oldt,newt))
 print("T1",oldt,"T2",newt)
 print("新增事件",n)
 for x in c.execute("select event_type,count(*) n from events_v3 group by event_type"):
  print(x["event_type"],x["n"])
 c.close()

if __name__=="__main__": main()
