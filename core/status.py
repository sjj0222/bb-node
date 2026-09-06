import sqlite3

DB="data/bb.db"

STAGES=[
 "COLLECT",
 "EVENT",
 "FEATURE",
 "SIGNAL",
 "STRATEGY",
 "DECISION"
]

def get_status():
 c=sqlite3.connect(DB)
 c.row_factory=sqlite3.Row

 out=[]

 for stage in STAGES:
  r=c.execute("""
   select stage,source,status,start_time,end_time,
          input_count,output_count,message
   from pipeline_runs
   where stage=?
   order by id desc
   limit 1
  """,(stage,)).fetchone()

  if r:
   duration=None
   if r["end_time"] and r["start_time"]:
    duration=r["end_time"]-r["start_time"]

   out.append({
    "stage":r["stage"],
    "source":r["source"],
    "status":r["status"],
    "start_time":r["start_time"],
    "end_time":r["end_time"],
    "duration_ms":duration,
    "input_count":r["input_count"] or 0,
    "output_count":r["output_count"] or 0,
    "message":r["message"] or ""
   })
  else:
   out.append({
    "stage":stage,
    "source":None,
    "status":"NO_RUN",
    "start_time":None,
    "end_time":None,
    "duration_ms":None,
    "input_count":0,
    "output_count":0,
    "message":""
   })

 c.close()
 return out


def print_status():
 import time

 c=sqlite3.connect(DB)

 r=c.execute(
  "select max(received_at),count(*) from unified_snapshots"
 ).fetchone()

 latest,total=r
 if latest:
  age=round(time.time()-latest/1000,1)
  state="OK" if age<=300 else "STALE"
  print(
   "UNIFIED latest="+str(latest),
   "rows="+str(total),
   "age="+str(age)+"s",
   state
  )
 else:
  print("UNIFIED NO_DATA")

 c.close()

 now=int(time.time()*1000)

 for r in get_status():
  age=None
  if r["start_time"]:
   age=round((now-r["start_time"])/1000,1)

  print(
   r["stage"],
   r["status"],
   "in="+str(r["input_count"]),
   "out="+str(r["output_count"]),
   "age="+str(age)+"s",
   "ms="+str(r["duration_ms"])
  )


if __name__=="__main__":
 print_status()
