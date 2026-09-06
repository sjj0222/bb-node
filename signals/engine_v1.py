import sqlite3,json,time,hashlib
from core.log import start,finish,error

DB="data/bb.db"

def run():
 log_id=start("SIGNAL","features_v2")
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row

 try:
  c.execute("""create table if not exists signals_v1(
   id integer primary key,canonical_match_id text,source text,
   market_type text,period text,old_time integer,new_time integer,
   signal_type text,strength real,feature_json text,
   signal_hash text unique,created_at integer)""")

  rows=c.execute(
   "select * from features_v2 order by new_time,id"
  ).fetchall()

  n=0
  for r in rows:
   d=json.loads(r["feature_json"])
   sig=[]

   if r["market_type"]=="asian_handicap":
    if d.get("shift_levels",0)>=3:
     sig.append(("WATER_SHIFT_STRONG",
                 min(1,d["shift_levels"]/5)))

    if d.get("shift_ratio",0)>=0.8:
     sig.append(("MULTI_LEVEL_SYNC",
                 d["shift_ratio"]))

   for typ,strength in sig:
    h=hashlib.sha256(
     repr((r["canonical_match_id"],r["source"],
     r["market_type"],r["period"],r["old_time"],
     r["new_time"],typ)).encode()
    ).hexdigest()

    x=c.execute("""insert or ignore into signals_v1(
     canonical_match_id,source,market_type,period,
     old_time,new_time,signal_type,strength,
     feature_json,signal_hash,created_at)
     values(?,?,?,?,?,?,?,?,?,?,?)""",
     (r["canonical_match_id"],r["source"],
      r["market_type"],r["period"],r["old_time"],
      r["new_time"],typ,round(strength,4),
      r["feature_json"],h,int(time.time()*1000)))

    n+=x.rowcount

  c.commit()

  finish(
   log_id,"OK",
   len(rows),n,
   "SIGNAL_V1生成完成"
  )

  print("新增SIGNAL",n)
  for r in c.execute("""select signal_type,count(*)
   from signals_v1 group by signal_type"""):
   print(*r)

 except Exception as e:
  c.rollback()
  error("SIGNAL",e)
  finish(log_id,"ERROR",0,0,str(e)[:200])
  raise

 finally:
  c.close()

if __name__=="__main__":
 run()
