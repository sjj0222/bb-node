import sqlite3,json,time,hashlib

DB="data/bb.db"

def run():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute("""create table if not exists decisions_v1(
 id integer primary key,
 canonical_match_id text,source text,
 market_type text,period text,
 old_time integer,new_time integer,
 strategy_name text,status text,
 candidate integer,direction text,selection text,
 evidence_json text,decision_hash text unique,created_at integer)""")

 rows=c.execute("""
 select * from strategies_v1
 where status='TRIGGERED'
 order by id
 """).fetchall()

 n=0
 for r in rows:
  evidence=json.loads(r["signals_json"] or "[]")
  h=hashlib.sha256(
   repr((r["canonical_match_id"],r["source"],
   r["market_type"],r["period"],
   r["old_time"],r["new_time"],
   r["strategy_name"])).encode()).hexdigest()

  x=c.execute("""insert or ignore into decisions_v1(
  canonical_match_id,source,market_type,period,
  old_time,new_time,strategy_name,status,candidate,
  direction,selection,evidence_json,decision_hash,created_at)
  values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
  (r["canonical_match_id"],r["source"],
   r["market_type"],r["period"],
   r["old_time"],r["new_time"],
   r["strategy_name"],"CANDIDATE",1,
   "UNKNOWN","UNKNOWN",
   json.dumps(evidence,ensure_ascii=False),
   h,int(time.time()*1000)))
  n+=x.rowcount

 c.commit()
 print("新增DECISION",n)
 for r in c.execute("""select status,count(*)
 from decisions_v1 group by status"""):
  print(*r)
 c.close()

if __name__=="__main__":run()
