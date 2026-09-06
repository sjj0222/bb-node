import sqlite3,json,time

DB="data/bb.db"

def run():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute("delete from features_v2")

 rows=c.execute("select * from events_v3 order by new_time,id").fetchall()
 gs={}
 for r in rows:
  k=(r["canonical_match_id"],r["source"],r["market_type"],
     r["period"],r["old_time"],r["new_time"])
  gs.setdefault(k,[]).append(r)

 for k,rs in gs.items():
  ds=[]
  for r in rs:
   try: ds.append(abs(float(r["new_odds"])-float(r["old_odds"])))
   except: pass

  wc=len(rs)
  up=sum(r["odds_direction"]=="UP" for r in rs)
  down=sum(r["odds_direction"]=="DOWN" for r in rs)

  shifts=c.execute("""select count(*) from event_groups_v3
   where canonical_match_id=? and source=? and market_type=?
   and period=? and old_time=? and new_time=?
   and group_type='WATER_SHIFT'""",k).fetchone()[0]

  data={
   "avg_delta":round(sum(ds)/max(1,len(ds)),5),
   "max_delta":round(max(ds),5) if ds else 0,
   "total_delta":round(sum(ds),5),
   "direction_balance":round((up-down)/max(1,wc),4)
  }

  if k[2]=="asian_handicap":
   levels=max(1,wc//2)
   data["levels"]=levels
   data["shift_levels"]=shifts
   data["shift_ratio"]=round(shifts/levels,4)
  else:
   data["outcome_changes"]=wc
   data["shift_levels"]=shifts

  c.execute("""insert into features_v2(
   canonical_match_id,source,market_type,period,
   old_time,new_time,water_changes,up_count,down_count,
   shift_levels,shift_ratio,avg_delta,max_delta,total_delta,
   direction_balance,line_changes,feature_json,created_at)
   values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
   (k[0],k[1],k[2],k[3],k[4],k[5],wc,up,down,
    shifts,data.get("shift_ratio"),data["avg_delta"],
    data["max_delta"],data["total_delta"],data["direction_balance"],
    sum(r["event_type"]=="LINE_CHANGE" for r in rs),
    json.dumps(data,ensure_ascii=False),int(time.time()*1000)))

 c.commit()
 print("FEATURE_V2重建完成")
 for r in c.execute("""select market_type,count(*) from features_v2
 group by market_type"""):
  print(*r)
 c.close()

if __name__=="__main__":run()
