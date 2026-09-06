import sqlite3,hashlib
c=sqlite3.connect("data/bb.db");c.row_factory=sqlite3.Row

c.execute("""create table if not exists event_groups_v3(
id integer primary key,canonical_match_id text,source text,
market_type text,period text,old_time integer,new_time integer,
group_type text,event_count integer,detail text,group_hash text unique)""")

def depth(s):
 try:
  s=str(s or "").replace(" ","")
  if "/" in s:
   a,b=s.split("/",1)
   return round((abs(float(a))+abs(float(b)))/2,4)
  return abs(float(s))
 except:return None

rows=c.execute("select * from events_v3 order by new_time,id").fetchall()
gs={}
for r in rows:
 d=None if r["market_type"]=="1x2" else depth(r["old_line_raw"])
 k=(r["canonical_match_id"],r["source"],r["market_type"],
    r["period"],r["old_time"],r["new_time"],d)
 gs.setdefault(k,[]).append(r)

n=0
for k,rs in gs.items():
 ups=sum(r["odds_direction"]=="UP" for r in rs)
 downs=sum(r["odds_direction"]=="DOWN" for r in rs)
 lines=[r for r in rs if r["event_type"]=="LINE_CHANGE"]

 typ=None
 if lines and (ups or downs):
  typ="LINE_WATER"
 elif ups and downs:
  typ="WATER_SHIFT"

 if not typ:continue

 detail=";".join(
  "%s:%s>%s"%(r["option"],r["old_line_raw"],r["new_line_raw"])
  if r["event_type"]=="LINE_CHANGE"
  else "%s:%s>%s"%(r["option"],r["old_odds"],r["new_odds"])
  for r in rs)

 h=hashlib.sha256(repr((k,typ,detail)).encode()).hexdigest()
 x=c.execute("""insert or ignore into event_groups_v3
(canonical_match_id,source,market_type,period,old_time,new_time,
group_type,event_count,detail,group_hash)
values(?,?,?,?,?,?,?,?,?,?)""",
(k[0],k[1],k[2],k[3],k[4],k[5],typ,len(rs),detail,h))
 n+=x.rowcount

c.commit()
print("新增GROUP",n)
for r in c.execute("""select market_type,group_type,count(*)
from event_groups_v3 group by market_type,group_type"""):
 print(*r)
c.close()
