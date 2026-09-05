import sqlite3

DB="data/bb.db"

def num(x):
    try:return float(x)
    except:return None

def dir2(a,b):
    x,y=num(a),num(b)
    if x is None or y is None:return None
    if y>x:return "UP"
    if y<x:return "DOWN"
    return None

def main():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row

    c.execute("""
    CREATE TABLE IF NOT EXISTS event_groups(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      match_id TEXT NOT NULL,
      market_id TEXT NOT NULL,
      source TEXT NOT NULL,
      old_run_id INTEGER NOT NULL,
      new_run_id INTEGER NOT NULL,
      event_time INTEGER NOT NULL,
      group_type TEXT NOT NULL,
      option_count INTEGER NOT NULL,
      event_count INTEGER NOT NULL,
      detail TEXT
    )
    """)

    c.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_event_group
    ON event_groups(
      match_id,market_id,source,old_run_id,new_run_id,group_type
    )
    """)

    runs=c.execute("""
    SELECT id,source,started_at,finished_at
    FROM collection_runs
    WHERE success=1
    ORDER BY started_at,id
    """).fetchall()

    groups={}
    for r in runs:
        groups.setdefault(r["source"],[]).append(r)

    created=0

    print("=== Event Engine V2 ===")

    for source,rs in groups.items():
        if len(rs)<2:
            continue

        for i in range(1,len(rs)):
            old,new=rs[i-1],rs[i]

            rows=c.execute("""
            SELECT
              a.match_id,
              a.market_id,
              a.option_index,
              a.line old_line,
              b.line new_line,
              a.odds old_odds,
              b.odds new_odds,
              a.node_id,
              m.mty
            FROM snapshots a
            JOIN snapshots b
              ON a.match_id=b.match_id
             AND a.market_id=b.market_id
             AND a.option_index=b.option_index
             AND a.node_id=b.node_id
            JOIN markets m ON a.market_id=m.market_id
            WHERE a.collection_run_id=?
              AND b.collection_run_id=?
            ORDER BY a.match_id,a.market_id,a.option_index
            """,(old["id"],new["id"])).fetchall()

            market_rows={}
            for r in rows:
                market_rows.setdefault(
                    (r["match_id"],r["market_id"]),
                    []
                ).append(r)

            for key,rs2 in market_rows.items():
                changed=[]

                for r in rs2:
                    od=dir2(r["old_odds"],r["new_odds"])
                    line=str(r["old_line"]) != str(r["new_line"])

                    if od or line:
                        changed.append((r,od,line))

                if len(changed)<2:
                    continue

                ups=sum(1 for _,d,_ in changed if d=="UP")
                downs=sum(1 for _,d,_ in changed if d=="DOWN")
                lines=sum(1 for _,_,l in changed if l)

                if ups and downs:
                    gt="LINE_WATER" if lines else "WATER_SHIFT"
                elif lines:
                    gt="LINE_CHANGE"
                else:
                    continue

                detail=";".join(
                    "%s:%s>%s"%(r["option_index"],r["old_odds"],r["new_odds"])
                    for r,_,_ in changed
                )

                cur=c.execute("""
                INSERT OR IGNORE INTO event_groups(
                  match_id,market_id,source,
                  old_run_id,new_run_id,event_time,
                  group_type,option_count,event_count,detail
                )
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,(
                    key[0],
                    key[1],
                    source,
                    old["id"],
                    new["id"],
                    new["finished_at"] or new["started_at"],
                    gt,
                    len(rs2),
                    len(changed),
                    detail
                ))

                if cur.rowcount:
                    created+=1

                    print(
                        source,
                        "|",key[0],
                        "|",key[1],
                        "|",gt,
                        "|",detail
                    )

    c.commit()

    total=c.execute(
        "SELECT COUNT(*) FROM event_groups"
    ).fetchone()[0]

    print("\n=== 完成 ===")
    print("本次新增:",created)
    print("event_groups总数:",total)

    print("\n=== 类型 ===")
    for r in c.execute("""
      SELECT group_type,COUNT(*)
      FROM event_groups
      GROUP BY group_type
      ORDER BY COUNT(*) DESC
    """):
        print(r[0],r[1])

    c.close()

if __name__=="__main__":
    main()
