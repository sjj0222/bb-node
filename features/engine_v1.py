import sqlite3,json,time

DB="data/bb.db"

def run():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute("delete from features_v1")

 rows=c.execute("""select * from events_v3
 order by new_time,id""").fetchall()

 gs={}
 for r in rows:
  k=(r["canonical_match_id"],r["source"],r["market_type"],
     r["period"],r["old_time"],r["new_time"])
  gs.setdefault(k,[]).append(r)

 n=0
 for k,rs in gs.items():
  wc=len(rs)
  up=sum(r["odds_direction"]=="UP" for r in rs)
  down=sum(r["odds_direction"]=="DOWN" for r in rs)
  lc=sum(r["event_type"]=="LINE_CHANGE" for r in rs)

  ws=c.execute("""select count(*) from event_groups_v3
   where canonical_match_id=? and source=? and market_type=?
   and period=? and old_time=? and new_time=?
   and group_type='WATER_SHIFT'""",
   k).fetchone()[0]

  data={
   "water_changes":wc,
   "up_count":up,
   "down_count":down,
   "up_ratio":round(up/max(1,wc),4),
   "down_ratio":round(down/max(1,wc),4),
   "water_shift_levels":ws,
   "line_changes":lc
  }

  c.execute("""insert into features_v1(
   canonical_match_id,source,market_type,period,
   old_time,new_time,water_changes,up_count,down_count,
   water_shift,line_changes,feature_json,created_at)
   values(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
   (k[0],k[1],k[2],k[3],k[4],k[5],
    wc,up,down,ws,lc,json.dumps(data,ensure_ascii=False),
    int(time.time()*1000)))
  n+=1

 c.commit()
 print("新增FEATURE",n)
 for r in c.execute("""select market_type,count(*)
  from features_v1 group by market_type"""):
  print(*r)
 c.close()

if __name__=="__main__":
 run()
