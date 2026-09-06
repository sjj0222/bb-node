import sqlite3,time,hashlib

DB="data/bb.db"

def run():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute("""create table if not exists replay_runs_v1(
 id integer primary key,
 start_time integer,end_time integer,
 rows integer,matches integer,
 replay_hash text unique,created_at integer)""")

 ts=[r[0] for r in c.execute(
  "select distinct received_at from unified_snapshots order by received_at")]

 if len(ts)<2:
  print("REPLAY: need >=2 timestamps")
  return

 start,end=ts[0],ts[-1]
 rows=c.execute(
  "select count(*) from unified_snapshots where received_at between ? and ?",
  (start,end)).fetchone()[0]
 matches=c.execute(
  "select count(distinct canonical_match_id) from unified_snapshots where received_at between ? and ?",
  (start,end)).fetchone()[0]

 h=hashlib.sha256(repr((start,end,rows,matches)).encode()).hexdigest()

 x=c.execute("""insert or ignore into replay_runs_v1(
 start_time,end_time,rows,matches,replay_hash,created_at)
 values(?,?,?,?,?,?)""",
 (start,end,rows,matches,h,int(time.time()*1000)))

 c.commit()

 print("REPLAY",x.rowcount)
 print("START",start)
 print("END",end)
 print("ROWS",rows)
 print("MATCHES",matches)
 print("TIMESTAMPS",len(ts))
 c.close()

if __name__=="__main__":run()
