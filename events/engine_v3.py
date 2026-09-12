import sqlite3,time,hashlib
from events.line import compare_line
from core.log import start,finish,error

DB="data/bb.db"

def h(*x):
 s="|".join("" if v is None else str(v) for v in x)
 return hashlib.sha256(s.encode()).hexdigest()

def window_events(oldt,newt,A_rows,B_rows):
 """一个相邻窗口 oldt->newt -> events list（Live/Replay 共用入口）"""
 evs=[]
 old={}
 for r in A_rows:
  k=(r["source"],r["canonical_match_id"],r["market_type"],r["source_market_id"],
     r["period"],r["side"],r["option"])
  old.setdefault(k,[]).append(r)
 for r in B_rows:
  k=(r["source"],r["canonical_match_id"],r["market_type"],r["source_market_id"],
     r["period"],r["side"],r["option"])
  cand=old.get(k,[])
  if not cand: continue
  a=min(cand,key=lambda x:abs((x["line"] or 0)-(r["line"] or 0)))
  od=a["odds"]!=r["odds"]
  lc=str(a["line_raw"])!=str(r["line_raw"])
  info=compare_line(a["line_raw"],r["line_raw"]) if lc else None
  events=[]
  if od: events.append(("ODDS_CHANGE",None))
  if info and info["changed"]: events.append(("LINE_CHANGE",info))
  for typ,li in events:
   d=None
   if od: d="UP" if r["odds"]>a["odds"] else "DOWN"
   eh=h(r["canonical_match_id"],r["source"],k,a["line_raw"],
        r["line_raw"],a["odds"],r["odds"],oldt,newt,typ)
   evs.append({
    "canonical_match_id":r["canonical_match_id"],
    "source":r["source"],
    "source_match_id":r["source_match_id"],
    "source_market_id":r["source_market_id"],
    "market_type":r["market_type"],
    "period":r["period"],
    "side":r["side"],
    "option":r["option"],
    "old_line_raw":a["line_raw"],
    "new_line_raw":r["line_raw"],
    "old_odds":a["odds"],
    "new_odds":r["odds"],
    "odds_direction":d,
    "line_direction":li["direction"] if li else None,
    "line_change_type":li["change_type"] if li else None,
    "event_type":typ,
    "old_time":oldt,
    "new_time":newt,
    "event_hash":eh
   })
 return evs

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
 n=0
 for oldt,newt in zip(ts,ts[1:]):
  A=[r for r in rows if r["received_at"]==oldt]
  B=[r for r in rows if r["received_at"]==newt]
  for e in window_events(oldt,newt,A,B):
   x=c.execute("""insert or ignore into events_v3
   (canonical_match_id,source,source_match_id,source_market_id,market_type,period,side,
    option,old_line_raw,new_line_raw,old_odds,new_odds,odds_direction,
    line_direction,line_change_type,event_type,old_time,new_time,
    event_hash,created_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
   (e["canonical_match_id"],e["source"],e["source_match_id"],e["source_market_id"],
    e["market_type"],e["period"],e["side"],e["option"],
    e["old_line_raw"],e["new_line_raw"],e["old_odds"],e["new_odds"],e["odds_direction"],
    e["line_direction"],e["line_change_type"],
    e["event_type"],e["old_time"],e["new_time"],
    e["event_hash"],int(time.time()*1000)))
   n+=x.rowcount
 c.commit()
 finish(log_id,"OK",len(rows),n,"T1=%s T2=%s" % (oldt,newt))
 print("T1",oldt,"T2",newt)
 print("新增事件",n)
 for x in c.execute("select event_type,count(*) n from events_v3 group by event_type"):
  print(x["event_type"],x["n"])
 c.close()

if __name__=="__main__": main()
