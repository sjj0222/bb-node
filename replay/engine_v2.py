import sqlite3,time,hashlib
from core.log import start,finish,error

DB="data/bb.db"

# 当前历史数据的正式Replay起点T1
# 后续建立Replay数据集元数据后移除
DEFAULT_START=1788659274783

def run(start_time=None,end_time=None):
 log_id=start("REPLAY_V2","unified_snapshots")
 c=sqlite3.connect(DB)
 c.row_factory=sqlite3.Row

 try:
  c.execute("""create table if not exists replay_runs_v2(
   id integer primary key,
   pipeline_run_id text,
   start_time integer,
   end_time integer,
   timestamp_count integer,
   window_count integer,
   rows integer,
   matches integer,
   status text,
   replay_hash text unique,
   created_at integer)""")

  if start_time is None:
   start_time=DEFAULT_START

  q="""
   select distinct received_at
   from unified_snapshots
   where received_at>=?
  """
  p=[start_time]

  if end_time is not None:
   q+=" and received_at<=?"
   p.append(end_time)

  q+=" order by received_at"

  ts=[r[0] for r in c.execute(q,p)]

  if len(ts)<2:
   print("REPLAY_V2: need >=2 timestamps")
   finish(log_id,"OK",0,0,"需要至少2个时间点")
   c.close()
   return None

  start_ts,end_ts=ts[0],ts[-1]

  rows=c.execute("""
   select count(*)
   from unified_snapshots
   where received_at>=?
   and received_at<=?
  """,(start_ts,end_ts)).fetchone()[0]

  matches=c.execute("""
   select count(distinct canonical_match_id)
   from unified_snapshots
   where received_at>=?
   and received_at<=?
   and canonical_match_id is not null
  """,(start_ts,end_ts)).fetchone()[0]

  gaps=[]
  for a,b in zip(ts,ts[1:]):
   gaps.append((a,b,b-a))

  h=hashlib.sha256(
   repr((start_ts,end_ts,ts,rows,matches,gaps)).encode()
  ).hexdigest()

  x=c.execute("""insert or ignore into replay_runs_v2(
   pipeline_run_id,start_time,end_time,timestamp_count,
   window_count,rows,matches,status,replay_hash,created_at)
   values(?,?,?,?,?,?,?,?,?,?)""",
   (log_id,start_ts,end_ts,len(ts),len(gaps),
    rows,matches,"READY",h,int(time.time()*1000)))

  c.commit()

  print("REPLAY_V2",x.rowcount)
  print("START",start_ts)
  print("END",end_ts)
  print("TIMESTAMPS",len(ts))
  print("WINDOWS",len(gaps))
  print("ROWS",rows)
  print("MATCHES",matches)

  for a,b,gap in gaps:
   print("WINDOW",a,b,"GAP_MS",gap)

  finish(
   log_id,"OK",
   rows,x.rowcount,
   "timestamps=%s windows=%s matches=%s" %
   (len(ts),len(gaps),matches)
  )

  return {
   "pipeline_run_id":log_id,
   "start_time":start_ts,
   "end_time":end_ts,
   "timestamp_count":len(ts),
   "window_count":len(gaps),
   "rows":rows,
   "matches":matches,
   "status":"READY",
   "replay_hash":h
  }

 except Exception as e:
  c.rollback()
  error("REPLAY_V2",e)
  finish(log_id,"ERROR",0,0,str(e)[:200])
  raise

 finally:
  c.close()

if __name__=="__main__":
 run()
