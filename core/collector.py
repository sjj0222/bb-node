import os,time,hashlib,requests,sys,json,uuid

ROOT=os.path.expanduser("~/bb_node")
sys.path.insert(0,ROOT)

from database.db import connect,init,data_hash
from sources.bb import BBAdapter
from mapping.match import make_canonical_id
from mapping.service import auto_map
from mapping.unified_service import unify
from mapping.db import init_mapping
from mapping.market_db import init_market_mapping
from mapping.unified_db import init_unified
from core.log import start,finish,error

URL="https://api.infv1.com/v1/match/getList"

TARGET={
11140:"欧冠",11062:"英超",10815:"西甲",11018:"意甲",
10807:"德甲",10983:"法甲",10640:"韩国K1",10706:"日本J1"
}

VERSION="0.1.0"
PROTOCOL="1"
NODE_FILE=os.path.join(ROOT,"config","node.json")
RAW_DIR=os.path.join(ROOT,"data","raw","bb")

def get_node_id():
    os.makedirs(os.path.dirname(NODE_FILE),exist_ok=True)

    if os.path.exists(NODE_FILE):
        try:
            with open(NODE_FILE,encoding="utf-8") as f:
                x=json.load(f)
            if x.get("node_id"):
                return x["node_id"]
        except Exception:
            pass

    nid="NODE-"+uuid.uuid4().hex[:16]

    with open(NODE_FILE,"w",encoding="utf-8") as f:
        json.dump({
            "node_id":nid,
            "created_at":int(time.time())
        },f,ensure_ascii=False,indent=2)

    return nid

NODE_ID=get_node_id()
S=requests.Session()
ADAPTER=BBAdapter()

def get_page(page,typ):
    for n in range(3):
        try:
            ts=int(time.time()*1000)
            did="H5-"+str(ts)

            raw=f"device-id={did}&os-type=1&timestamp={ts}&version=5.4.0"
            sign=hashlib.md5((raw+"global").encode()).hexdigest()

            h={
                "Content-Type":"application/json;charset=UTF-8",
                "device-id":did,
                "os-type":"1",
                "timestamp":str(ts),
                "version":"5.4.0",
                "sign":sign,
                "app-type":"0"
            }

            b={
                "current":page,
                "orderBy":0,
                "isPc":True,
                "type":typ,
                "sportId":1,
                "languageType":"CMN"
            }

            r=S.post(URL,headers=h,json=b,timeout=15)
            r.raise_for_status()
            j=r.json()

            if j.get("success"):
                return j

        except Exception as e:
            print("重试",n+1,str(e)[:60],flush=True)
            time.sleep(2)

    return None

def fetch(typ,name):
    matches={}
    page=1

    while True:
        print(name,"第",page,"页",flush=True)

        j=get_page(page,typ)

        if not j:
            print(name,"失败",flush=True)
            break

        d=j.get("data") or {}
        rec=d.get("records") or []
        total=d.get("total") or 0
        size=d.get("size") or 50

        for m in rec:
            lg=m.get("lg") or {}

            if lg.get("id") in TARGET:
                matches[str(m.get("id"))]=m

        if page*size>=total or not rec:
            break

        page+=1
        time.sleep(1)

    return matches

def parse(matches,source="bb"):
    rows=[]

    for m in matches.values():
        lg=m.get("lg") or {}
        ts=m.get("ts") or []

        home=ts[0].get("na","") if len(ts)>0 else ""
        away=ts[1].get("na","") if len(ts)>1 else ""

        for mg in m.get("mg") or []:
            mty=str(mg.get("mty",""))

            for mk in mg.get("mks") or []:
                market_id=str(mk.get("id"))
                ops=mk.get("op") or []

                for i,op in enumerate(ops):
                    rows.append({
                        "match_id":str(m.get("id")),
                        "source":source,
                        "league_id":lg.get("id"),
                        "league":TARGET.get(
                            lg.get("id"),lg.get("na","")
                        ),
                        "begin_time":m.get("bt",""),
                        "home":home,
                        "away":away,
                        "mty":mty,
                        "pe":mg.get("pe"),
                        "market_id":market_id,
                        "option_index":i+1,
                        "option":op.get("na",""),
                        "line":op.get("li",""),
                        "odds":op.get("od","")
                    })

    return rows

def save(rows,source,run_id,started):
    now=int(time.time())
    c=connect()
    matches=set()

    for r in rows:
        mid=r["match_id"]
        matches.add(mid)

        c.execute("""
        INSERT INTO matches(
            match_id,league_id,league,begin_time,
            home,away,source,updated_at
        )
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(match_id) DO UPDATE SET
            league_id=excluded.league_id,
            league=excluded.league,
            begin_time=excluded.begin_time,
            home=excluded.home,
            away=excluded.away,
            source=excluded.source,
            updated_at=excluded.updated_at
        """,(
            mid,r["league_id"],r["league"],r["begin_time"],
            r["home"],r["away"],r["source"],now
        ))

        c.execute("""
        INSERT INTO markets(
            market_id,match_id,mty,pe,updated_at
        )
        VALUES(?,?,?,?,?)
        ON CONFLICT(market_id) DO UPDATE SET
            mty=excluded.mty,
            pe=excluded.pe,
            updated_at=excluded.updated_at
        """,(
            r["market_id"],mid,r["mty"],r["pe"],now
        ))

        h=data_hash(r)

        c.execute("""
        INSERT OR IGNORE INTO snapshots(
            collection_run_id,match_id,market_id,
            option_index,option,line,odds,
            collected_at,node_id,data_hash
        )
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,(
            run_id,mid,r["market_id"],r["option_index"],
            r["option"],r["line"],r["odds"],
            now,NODE_ID,h
        ))

    c.execute("""
    UPDATE collection_runs
    SET finished_at=?,match_count=?,row_count=?,success=1
    WHERE id=?
    """,(
        int(time.time()),
        len(matches),
        len(rows),
        run_id
    ))

    c.commit()
    c.close()

    return len(matches),len(rows)

def save_new_layers(raw_matches,received_at):
    os.makedirs(RAW_DIR,exist_ok=True)

    total_norm=0
    total_unified=0
    match_count=0

    for m in raw_matches.values():
        raw_ref=ADAPTER.save_raw(m,RAW_DIR)

        records=ADAPTER.normalize(
            m,
            received_at,
            raw_ref=raw_ref
        )

        if not records:
            continue

        x=records[0]

        mm=auto_map(x,x)
        cid=mm["canonical_match_id"]

        match_count+=1
        total_norm+=len(records)

        for r in records:
            unify(r,cid)
            total_unified+=1

    return {
        "matches":match_count,
        "normalized":total_norm,
        "unified":total_unified
    }

def run_type(typ,name):
    started=int(time.time())

    c=connect()
    cur=c.execute("""
    INSERT INTO collection_runs(
        started_at,source,success
    ) VALUES(?,?,0)
    """,(started,name))

    run_id=cur.lastrowid
    c.commit()
    c.close()

    log_id=start("COLLECT",name)

    try:
        matches=fetch(typ,name)

        received_at=int(time.time()*1000)

        rows=parse(matches,"bb")

        mc,rc=save(
            rows,
            name,
            run_id,
            started
        )

        nl=save_new_layers(
            matches,
            received_at
        )

        finish(
            log_id,"OK",
            mc,rc,
            "normalized=%s unified=%s" %
            (nl["normalized"],nl["unified"])
        )

        return {
            "run_id":run_id,
            "source":name,
            "matches":mc,
            "rows":rc,
            "normalized":nl["normalized"],
            "unified":nl["unified"],
            "success":True
        }

    except Exception as e:
        error("COLLECT",e)
        finish(log_id,"ERROR",0,0,str(e)[:200])
        c=connect()
        c.execute("""
        UPDATE collection_runs
        SET finished_at=?,success=0,error=?
        WHERE id=?
        """,(
            int(time.time()),
            str(e)[:500],
            run_id
        ))
        c.commit()
        c.close()
        raise

def collect():
    init()
    init_mapping()
    init_market_mapping()
    init_unified()

    print("=== BB Collector Core ===")
    print("Node:",NODE_ID)

    a=run_type(3,"今日")
    print(
        "今日完成：比赛",a["matches"],
        "盘口",a["rows"],
        "Unified",a["unified"]
    )

    b=run_type(4,"早盘")
    print(
        "早盘完成：比赛",b["matches"],
        "盘口",b["rows"],
        "Unified",b["unified"]
    )

    print("=== 本轮完成 ===")

if __name__=="__main__":
    collect()
