import sqlite3
import hashlib

DB="data/bb.db"

def num(x):
    try:return float(x)
    except:return None

def direction(a,b):
    x,y=num(a),num(b)
    if x is None or y is None:return None
    if y>x:return "UP"
    if y<x:return "DOWN"
    return None

def main():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row

    c.execute("""
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      match_id TEXT NOT NULL,
      market_id TEXT NOT NULL,
      option_index INTEGER NOT NULL,
      mty TEXT,
      source TEXT NOT NULL,
      old_line TEXT,
      new_line TEXT,
      old_odds TEXT,
      new_odds TEXT,
      odds_direction TEXT,
      line_direction TEXT,
      event_type TEXT NOT NULL,
      old_run_id INTEGER NOT NULL,
      new_run_id INTEGER NOT NULL,
      event_time INTEGER NOT NULL,
      node_id TEXT NOT NULL,
      event_hash TEXT NOT NULL UNIQUE
    )
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_match_time
    ON events(match_id,event_time)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_market_time
    ON events(market_id,event_time)
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

    print("=== Event Engine V1 ===")

    for source,rs in groups.items():
        if len(rs)<2:
            continue

        for i in range(1,len(rs)):
            old,new=rs[i-1],rs[i]

            q="""
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
            """

            rows=c.execute(q,(old["id"],new["id"])).fetchall()

            batch_events=0

            for r in rows:
                od=direction(r["old_odds"],r["new_odds"])

                ld=None
                if str(r["old_line"]) != str(r["new_line"]):
                    ld=direction(r["old_line"],r["new_line"]) or "CHANGED"

                if not od and not ld:
                    continue

                if od and ld:
                    et="ODDS_AND_LINE"
                elif od:
                    et="ODDS"
                else:
                    et="LINE"

                raw="|".join([
                    str(r["match_id"]),
                    str(r["market_id"]),
                    str(r["option_index"]),
                    str(old["id"]),
                    str(new["id"]),
                    str(r["old_line"]),
                    str(r["new_line"]),
                    str(r["old_odds"]),
                    str(r["new_odds"])
                ])

                h=hashlib.sha256(raw.encode()).hexdigest()

                cur=c.execute("""
                INSERT OR IGNORE INTO events(
                  match_id,market_id,option_index,mty,source,
                  old_line,new_line,old_odds,new_odds,
                  odds_direction,line_direction,event_type,
                  old_run_id,new_run_id,event_time,node_id,event_hash
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,(
                    r["match_id"],
                    r["market_id"],
                    r["option_index"],
                    r["mty"],
                    source,
                    r["old_line"],
                    r["new_line"],
                    r["old_odds"],
                    r["new_odds"],
                    od,
                    ld,
                    et,
                    old["id"],
                    new["id"],
                    new["finished_at"] or new["started_at"],
                    r["node_id"],
                    h
                ))

                if cur.rowcount:
                    created+=1
                    batch_events+=1

            print(
                source,
                old["id"],"→",new["id"],
                "| 比较",len(rows),
                "| 新事件",batch_events
            )

    c.commit()

    total=c.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    print("\n=== 完成 ===")
    print("本次新增:",created)
    print("events总数:",total)

    print("\n事件类型:")
    for r in c.execute("""
      SELECT event_type,COUNT(*)
      FROM events
      GROUP BY event_type
      ORDER BY COUNT(*) DESC
    """):
        print(r[0],r[1])


    c.close()

if __name__=="__main__":
    main()
