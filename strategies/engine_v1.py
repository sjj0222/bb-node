import sqlite3,json,time,hashlib
from core.log import start,finish,error

DB="data/bb.db"

def run():

 log_id=start("STRATEGY","signals_v1")
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute("""create table if not exists strategies_v1(
 id integer primary key,
 canonical_match_id text,source text,
 market_type text,period text,
 old_time integer,new_time integer,
 strategy_name text,status text,
 direction text,selection text,bet integer,
 signals_json text,strategy_hash text unique,created_at integer)""")

 rows=c.execute("""
 select * from signals_v1
 order by canonical_match_id,old_time,id
 """).fetchall()

 groups={}
 for r in rows:
  k=(r["canonical_match_id"],r["source"],
     r["market_type"],r["period"],r["old_time"],r["new_time"])
  groups.setdefault(k,[]).append(r)

 n=0
 for k,rs in groups.items():
  names={r["signal_type"] for r in rs}

  if "WATER_SHIFT_STRONG" in names and \
     "MULTI_LEVEL_SYNC" in names:
   mid,src,mt,period,t1,t2=k
   sj=[r["signal_type"] for r in rs]
   h=hashlib.sha256(repr((k,"AH_MULTI_LEVEL_WATER")).encode()).hexdigest()

   x=c.execute("""insert or ignore into strategies_v1(
   canonical_match_id,source,market_type,period,
   old_time,new_time,strategy_name,status,
   direction,selection,bet,signals_json,
   strategy_hash,created_at)
   values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
   (mid,src,mt,period,t1,t2,
    "AH_MULTI_LEVEL_WATER","TRIGGERED",
    None,None,0,json.dumps(sj),
    h,int(time.time()*1000)))
   n+=x.rowcount

 c.commit()
 
 finish(log_id,"OK",len(rows),n,"STRATEGY_V1生成完成")
 print("新增STRATEGY",n)

 for r in c.execute("""select strategy_name,status,count(*)
 from strategies_v1 group by strategy_name,status"""):
  print(*r)
 c.close()

if __name__=="__main__":run()
