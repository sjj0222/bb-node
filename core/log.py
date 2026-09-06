import os
import time
import logging
import sqlite3

BASE=os.path.expanduser("~/bb_node")
DB=os.path.join(BASE,"data","bb.db")
LOG=os.path.join(BASE,"data","logs","bb-node.log")

os.makedirs(os.path.dirname(LOG),exist_ok=True)

logging.basicConfig(
 filename=LOG,
 level=logging.INFO,
 format="%(asctime)s | %(levelname)s | %(message)s"
)

def init():
 c=sqlite3.connect(DB)
 c.execute("""create table if not exists pipeline_runs(
 id integer primary key,
 run_id text,
 stage text,
 source text,
 start_time integer,
 end_time integer,
 status text,
 input_count integer,
 output_count integer,
 message text
 )""")
 c.commit()
 c.close()

def start(stage,source=""):
 run_id=str(int(time.time()*1000))
 t=int(time.time()*1000)
 c=sqlite3.connect(DB)
 c.execute("""insert into pipeline_runs
 (run_id,stage,source,start_time,status)
 values(?,?,?,?,?)""",
 (run_id,stage,source,t,"RUNNING"))
 c.commit()
 c.close()
 logging.info("%s START run=%s source=%s",stage,run_id,source)
 return run_id

def finish(run_id,status="OK",input_count=0,
           output_count=0,message=""):
 t=int(time.time()*1000)
 c=sqlite3.connect(DB)
 c.execute("""update pipeline_runs
 set end_time=?,status=?,input_count=?,
 output_count=?,message=? where run_id=?""",
 (t,status,input_count,output_count,message,run_id))
 row=c.execute(
  "select stage,source from pipeline_runs where run_id=?",
  (run_id,)).fetchone()
 c.commit()
 c.close()
 stage,source=row if row else ("UNKNOWN","")
 logging.info(
  "%s END run=%s source=%s status=%s in=%s out=%s %s",
  stage,run_id,source,status,input_count,output_count,message)

def error(stage,e):
 logging.exception("%s ERROR %s",stage,e)

init()
