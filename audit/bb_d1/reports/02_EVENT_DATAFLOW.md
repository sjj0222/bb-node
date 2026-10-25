# 02_EVENT_DATAFLOW.md

> 链路：Source Adapter → RAW → Normalized → Market Mapping → Unified → Event Engine → Feature/Signal → Replay
> 证据类别：**CODE / TEST / DATA / GIT / INFERENCE / UNKNOWN**

---

## 0. 字段溯源总表

| 阶段 | 文件:行 | `line_raw` 来源 | `line` 来源 | 备注 |
|---|---|---|---|---|
| Source | `sources/bb.py:40` | – | – | `mk_line = mk.get("li")`（**盘口级**） |
| Source | `sources/bb.py:43` | `op.get("li", mk_line)`（**选项级**，缺省回退盘口级） | – | **与上一行不同源** |
| Source | `sources/bb.py:46` | – | `float(mk_line)`（**盘口级**） | **main 未修 P1-4** |
| Source | `sources/bb.py:65` | 写入 `line_raw=str(raw_line)` | – | 选项级原文落库 |
| Mapping | `mapping/market.py:66-69` | `parse_line(record.line_raw)`（丢符号） | – | 写入 `market_mappings.line` |
| Mapping | `mapping/market.py:160`（仅 origin/phase1） | `parse_line_quarters` → `line_quarters` | – | **main 无此列** |
| Unified | `mapping/unified_service.py` / `mapping/unified_db.py:41-62` | 透传 | 透传 | `UNIQUE(source,source_match_id,source_market_id,option,received_at)` |
| Event | `events/engine_v3.py:42` | – | **配对用** `abs((x["line"] or 0)-(r["line"] or 0))` | 配对用错字段 |
| Event | `events/engine_v3.py:44-45` | **比较用** `str(a["line_raw"])!=str(r["line_raw"])` → `compare_line` | – | 比较用对字段 |
| Event | `events/engine_v3.py:54-63` | 落 `old_line_raw`/`new_line_raw` | – | `events_v3` **无 market_id 列** |

---

## 1. 高风险数据路径（5 条以上，每条给出完整证据链）

### HP-1 ★ `line` 与 `line_raw` 不同源 → 事件配对按错误字段就近取行
**原始字段**：`mk.li`（盘口级）+ `op.li`（选项级）
**赋值位置**：`sources/bb.py:40`（`mk_line`）、`:43`（`raw_line = op.get("li", mk_line)`）、`:46`（`line = float(mk_line)`）、`:65`（`line_raw`）
**中间转换**：`mapping/unified_service.py` → `unified_snapshots.line` = 盘口级、`unified_snapshots.line_raw` = 选项级
**事件配对**：`events/engine_v3.py:42` `a=min(cand,key=lambda x:abs((x["line"] or 0)-(r["line"] or 0)))`
**最终事件**：用错字段挑出的 "old" 行 → `events_v3` 写入的 `old_line_raw`/`new_line_raw` 可能来自**另一个 market_id / 另一个档位**
**证据**：CODE（`sources/bb.py:40-46`）；GIT（`origin/phase1` 提交 `af2db46` P1-4「line 与 line_raw 层级矛盾…修复四分之一球盘被归错线」，上游改为 `line = float(raw_line)`，**main 仍缺**）
**影响**：跨档位拼接 → 伪 LINE_CHANGE

### HP-2 ★ 配对键不含 `market_id` → 档位轮播时跨 market 配对
**原始字段**：`unified_snapshots.source_market_id`
**赋值位置**：`sources/bb.py:60` `source_market_id=mid`（= `mk.id`）
**中间转换**：`mapping/unified_db.py:26-32` UNIQUE 约束含 `source_market_id`
**事件配对**：`events/engine_v3.py:33-35` 键为 `(source, canonical_match_id, market_type, period, side, option)` —— **无 market_id**；`:38-39` 同键
**最终事件**：`events_v3` 表结构（`events/engine_v3.py:14-20`）**无 market_id 列** → 下游无法察觉错配
**证据**：CODE + DATA（`ladder.txt` 统计：同一 (match, market, option) 下 line 恒定；market_id 在 5 个档位间轮播，档位集合随快照变化 → 配对桶内可同时存在多个 market_id 的行）
**影响**：一条真实盘口变化被拆成多条事件，或把两个档位的行误当同一盘口

### HP-3 ★ `canonical_match_id` 恒为 None → `where canonical_match_id is not null` 恒空
**原始字段**：`sources/base.py` 的 `canonical_match_id`；`sources/bb.py:59` 显式 `canonical_match_id=None`
**赋值位置**：`sources/bb.py:59`
**中间转换**：`mapping/unified_service.py` 写 `unified_snapshots.canonical_match_id`
**事件配对**：`events/engine_v3.py:21-23` `select * from unified_snapshots where canonical_match_id is not null`
**最终事件**：**事件引擎读不到任何行 → 永不产出 LINE_CHANGE**
**证据**：CODE（`sources/bb.py:59`、`events/engine_v3.py:21-23`）；Agent B 独立确认
**影响**：严重度取决于 `mapping/service.auto_map` 是否在生产链路上回填 canonical id（**UNKNOWN**：本次未读 `mapping/service.py` 的调用方，也无运行数据）

### HP-4 ★ 事件引擎只比较最后两个时间点，回放引擎扫描全部窗口
**原始字段**：`unified_snapshots.received_at`
**中间转换**：`events/engine_v3.py:24` `ts=sorted(set(r["received_at"] for r in rows))`；`:28` `oldt,newt=ts[-2:]`
**事件配对**：仅最后一窗
**对比**：`replay/event_v2.py:25` `for oldt,newt in zip(ts,ts[1:])`（全窗口）；`replay/event_v1.py` 同为全窗口
**最终事件**：两条实现对同一数据产出**不同数量**的事件 → 事件与回放不可对账
**证据**：CODE（`events/engine_v3.py:24-28` vs `replay/event_v2.py:19-25`）
**影响**：replay 与 event 两库数据不一致（上游 `origin/phone-sync` 分支提交 `14c38d3 unify replay event calculation` 正是为此，但**未合并到 main**）

### HP-5 ★ `events/group_v3.py` 模块级写库副作用
**原始字段**：无（直接连库）
**赋值位置**：`events/group_v3.py:2` `c=sqlite3.connect("data/bb.db")`、`:4` create table、`:18` select、`:47` insert、`:54` commit、`:55` print
**中间转换**：无 `if __name__=="__main__"` 守卫（对比 `events/line.py:75`、`events/engine_v3.py:73` 均有守卫）
**最终事件**：任何 `import events.group_v3` 都会建表、读表、**写表**并打印
**证据**：CODE（逐行引用）
**影响**：import 副作用；`core/log.py:69` 的 `init()` 亦在 import 期建库

### HP-6 ★ feature/signal 层在全新库上直接崩溃
**原始字段**：`events_v3`
**赋值位置**：`features/engine_v1.py:7` `c.execute("delete from features_v1")`；`features/engine_v2.py:9` `c.execute("delete from features_v2")`
**中间转换**：`signals/engine_v1.py:18` `select * from features_v2`
**最终事件**：全仓库无任何 `create table features_v1/features_v2`（`grep -rn "create table.*features"` 无命中）→ `sqlite3.OperationalError: no such table` → 整条 feature→signal→strategy→decision 链断
**证据**：CODE + Agent B 独立 grep 确认
**影响**：全新库上事件下游全链路不可用

### HP-7 ★ 盘口级线与选项级线不一致时产生错误事件（BB-D1 未覆盖）
**原始字段**：`mk.li` vs `op.li`
**赋值位置**：`sources/bb.py:43,46`
**中间转换**：`unified_snapshots.line`（盘口级）与 `line_raw`（选项级）
**事件配对**：`events/engine_v3.py:42` 用 `line`（盘口级）配对，`:45` 用 `line_raw`（选项级）比较
**最终事件**：配对用盘口级、比较用选项级 → 二者不一致时事件语义自相矛盾
**证据**：CODE
**影响**：BB-D1 只改 `compare_line`，**不触碰此路径**

### HP-8 ★ DB 路径读写分裂
**写入方**：`database/db.py:3-4`、`core/log.py:6-7` → `~/bb_node/data/bb.db`
**读取方**：`events/engine_v3.py:5`、`features/engine_v1.py:3`、`features/engine_v2.py:4`、`signals/engine_v1.py:4`、`strategies/engine_v1.py:4`、`replay/event_v1.py:4`、`replay/event_v2.py:4` → 相对 `"data/bb.db"`
**最终事件**：除非 CWD 恰为 `~/bb_node`，否则事件引擎读的是**另一个空库**
**证据**：CODE
**影响**：所有下游统计在默认部署下为空

### HP-9 ★ `steps` 双量纲（候选实现引入）
**赋值**：`devcopy/events/line.py:80` `steps=round(abs(vn-vo)/0.25,4)`（CROSS 分支，值空间） vs `:101` `steps=diff/0.25`（幅度分支，深度空间）
**落库**：无处落库（`events_v3` 无该列）
**最终事件**：同名字段两种含义
**证据**：CODE + 实测（`verify_matrix_output.txt` C 节：同一对输入 MAIN `steps=3.0` / CAND `steps=5.0`）
**影响**：未来任何按 steps 聚合的分析都会混算

### HP-10 ★ 混合符号腿产生 `changed=True` 且 `steps=0.0`
**输入**：`"-1/+1"` vs `"-1/-1"`（main `parse_line` 保留混合符号 `[-1.0, 1.0]`）
**行为**：候选 `value` = 0.0（中性）→ 不进 CROSS → 幅度分支 → depth 相等 → `diff=0` → `SHALLOWER/MULTI_STEP/steps=0.0`
**证据**：实测（`verify_boundary_output.txt`：`'-1/+1'` 候选 value=0.0，规范 mid=-4 → NO）
**影响**：矛盾输出（changed=True 但步数为 0）
**注**：真实数据中不出现混合符号腿（DATA：19 种线串的第二腿从不带独立符号），故为潜在而非现实缺陷

---

## 2. 经核查未发现问题的环节（CLEAN）

- `line_raw` 始终保留原始选项级字符串，**未被推断值覆盖**（`sources/bb.py:65` → `unified_snapshots` → `events_v3.old_line_raw/new_line_raw`）
- `compare_line` 对不可解析输入返回 `changed=None`（`events/line.py:49-55`），不产生伪事件
- `unified_db.py:56` `INSERT OR IGNORE` + UNIQUE 约束 → 同 (source,match,market,option,received_at) 不重复
- `events/engine_v3.py:54`、`replay/event_v2.py:61` 用 `insert or ignore` on `event_hash` → 重复运行幂等
- `sources/registry.py` 只有一个 adapter（`bb`），`source` 已在配对键中
- `mapping/market.py:49-54 detect_side` 只做队名精确匹配 → `side` 常为 NULL，实际由 `option` 承担区分（这正是 HP-2 键设计的由来）

---

## 3. 附录：源码原文（见文件后半部分）
# 02_EVENT_DATAFLOW.md
=== sources/bb.py ===
import json
import os
import hashlib
from .base import NormalizedRecord

class BBAdapter:
    source = "bb"
    bookmaker = None

    def save_raw(self, match, raw_dir):
        os.makedirs(raw_dir, exist_ok=True)
        mid = str(match.get("id"))
        text = json.dumps(match, ensure_ascii=False, sort_keys=True)
        ref = hashlib.sha256(text.encode()).hexdigest()
        path = os.path.join(raw_dir, ref + ".json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return ref

    def normalize(self, match, received_at, raw_ref=None):
        out = []
        lg = match.get("lg") or {}
        ts = match.get("ts") or []

        home = ts[0].get("na","") if len(ts)>0 else ""
        away = ts[1].get("na","") if len(ts)>1 else ""

        try:
            event_time = int(match.get("bt")) if match.get("bt") is not None else None
        except (TypeError, ValueError):
            event_time = None

        for mg in match.get("mg") or []:
            mty = str(mg.get("mty",""))
            pe = mg.get("pe")

            for mk in mg.get("mks") or []:
                mid = str(mk.get("id"))
                mk_line = mk.get("li")

                for op in mk.get("op") or []:
                    raw_line = op.get("li", mk_line)

                    try:
                        line = float(mk_line) if mk_line is not None else None
                    except (TypeError, ValueError):
                        line = None

                    try:
                        odds = float(op.get("od")) if op.get("od") is not None else None
                    except (TypeError, ValueError):
                        odds = None

                    out.append(NormalizedRecord(
                        source=self.source,
                        bookmaker=self.bookmaker,
                        source_match_id=str(match.get("id")),
                        canonical_match_id=None,
                        source_market_id=mid,
                        market_type=mty,
                        period=str(pe) if pe is not None else None,
                        home=home,
                        away=away,
                        line_raw=str(raw_line) if raw_line is not None else None,
                        line=line,
                        option=op.get("na",""),
                        odds=odds,
                        event_time=event_time,
                        server_time=None,
                        received_at=received_at,
                        raw_ref=raw_ref
                    ))

        return out

=== mapping/match.py ===

import re
import hashlib
import unicodedata
from difflib import SequenceMatcher

def norm_name(s):
    s = str(s or "").strip().lower()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\s\-_.·'’]+", "", s)
    s = re.sub(r"[^\w\u4e00-\u9fff]", "", s)
    return s

def name_score(a, b):
    a, b = norm_name(a), norm_name(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()

def time_score(a, b, tolerance=900):
    if a is None or b is None:
        return 0.0
    try:
        d = abs(int(a) - int(b)) / 1000
    except:
        return 0.0
    if d > tolerance:
        return 0.0
    return max(0.0, 1.0 - d / tolerance)

def make_canonical_id(home, away, event_time):
    key = "%s|%s|%s" % (
        norm_name(home),
        norm_name(away),
        int(event_time or 0) // 60000
    )
    return "cm_" + hashlib.sha256(key.encode()).hexdigest()[:20]

def match_score(a, b):
    hs = name_score(a.home, b.home)
    aws = name_score(a.away, b.away)
    ts = time_score(a.event_time, b.event_time)

    score = hs * 0.4 + aws * 0.4 + ts * 0.2

    if hs == 1 and aws == 1 and ts >= 0.8:
        status = "matched"
    elif score >= 0.88:
        status = "matched"
    elif score >= 0.72:
        status = "possible"
    else:
        status = "unmatched"

    return {
        "status": status,
        "confidence": round(score, 4),
        "home_score": round(hs, 4),
        "away_score": round(aws, 4),
        "time_score": round(ts, 4)
    }

def map_match(a, b):
    r = match_score(a, b)
    if r["status"] == "matched":
        cid = make_canonical_id(
            a.home,
            a.away,
            a.event_time
        )
    else:
        cid = None
    r["canonical_match_id"] = cid
    return r

=== mapping/service.py ===

from .match import map_match
from .db import save_mapping

def auto_map(a, b):
    r = map_match(a, b)

    data = {
        "source": a.source,
        "source_match_id": a.source_match_id,
        "canonical_match_id": r["canonical_match_id"],
        "home": a.home,
        "away": a.away,
        "event_time": a.event_time,
        "confidence": r["confidence"],
        "status": r["status"]
    }

    save_mapping(data)
    return data

=== mapping/market_service.py ===

from .market import normalize
from .market_db import save_market

def map_and_save(record, canonical_match_id=None):
    m=normalize(record)

    save_market(
        m,
        canonical_match_id=canonical_match_id,
        source_match_id=record.source_match_id
    )

    return m

=== mapping/unified_service.py ===

from .market import normalize
from .unified_db import save_unified

def unify(record, canonical_match_id=None):
    market=normalize(record)

    save_unified(
        type("UnifiedRecord",(),{
            "source":record.source,
            "bookmaker":record.bookmaker,
            "source_match_id":record.source_match_id,
            "source_market_id":market.source_market_id,
            "market_type":market.market_type,
            "period":market.period,
            "line_raw":market.line_raw,
            "line":market.line,
            "side":market.side,
            "option":market.option,
            "odds":market.odds,
            "event_time":record.event_time,
            "server_time":record.server_time,
            "received_at":record.received_at,
            "raw_ref":record.raw_ref
        })(),
        canonical_match_id=canonical_match_id
    )

    return market

=== mapping/db.py ===

import time
from database.db import connect

def init_mapping():
    c = connect()
    c.execute("""
    CREATE TABLE IF NOT EXISTS match_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        source_match_id TEXT NOT NULL,
        canonical_match_id TEXT,
        home TEXT,
        away TEXT,
        event_time INTEGER,
        confidence REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        UNIQUE(source, source_match_id)
    )
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_mm_canonical
    ON match_mappings(canonical_match_id)
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_mm_event
    ON match_mappings(event_time)
    """)
    c.commit()
    c.close()

def save_mapping(r):
    now = int(time.time() * 1000)
    c = connect()
    c.execute("""
    INSERT INTO match_mappings
    (source,source_match_id,canonical_match_id,
     home,away,event_time,confidence,status,
     created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(source,source_match_id)
    DO UPDATE SET
      canonical_match_id=excluded.canonical_match_id,
      home=excluded.home,
      away=excluded.away,
      event_time=excluded.event_time,
      confidence=excluded.confidence,
      status=excluded.status,
      updated_at=excluded.updated_at
    """, (
        r["source"],
        r["source_match_id"],
        r.get("canonical_match_id"),
        r.get("home"),
        r.get("away"),
        r.get("event_time"),
        r.get("confidence",0),
        r.get("status","unmatched"),
        now,
        now
    ))
    c.commit()
    c.close()

def get_by_source(source, source_match_id):
    c = connect()
    r = c.execute("""
    SELECT * FROM match_mappings
    WHERE source=? AND source_match_id=?
    """,(source,str(source_match_id))).fetchone()
    c.close()
    return dict(r) if r else None

def get_by_canonical(canonical_match_id):
    c = connect()
    rows = c.execute("""
    SELECT * FROM match_mappings
    WHERE canonical_match_id=?
    ORDER BY source
    """,(canonical_match_id,)).fetchall()
    c.close()
    return [dict(r) for r in rows]

def list_mappings(status=None, limit=100):
    c = connect()
    if status:
        rows=c.execute("""
        SELECT * FROM match_mappings
        WHERE status=?
        ORDER BY updated_at DESC LIMIT ?
        """,(status,limit)).fetchall()
    else:
        rows=c.execute("""
        SELECT * FROM match_mappings
        ORDER BY updated_at DESC LIMIT ?
        """,(limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]

=== mapping/market_db.py ===

import time
from database.db import connect

def init_market_mapping():
    c=connect()
    c.execute("""
    CREATE TABLE IF NOT EXISTS market_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        canonical_match_id TEXT,
        source_match_id TEXT NOT NULL,
        source_market_id TEXT NOT NULL,
        market_type TEXT NOT NULL,
        period TEXT,
        line_raw TEXT,
        line REAL,
        side TEXT,
        option TEXT NOT NULL,
        odds REAL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        UNIQUE(source,source_match_id,source_market_id,option)
    )
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_market_canonical
    ON market_mappings(canonical_match_id)
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_market_type
    ON market_mappings(market_type,period)
    """)
    c.commit()
    c.close()

def save_market(m, canonical_match_id=None, source_match_id=None):
    now=int(time.time()*1000)
    c=connect()

    c.execute("""
    INSERT INTO market_mappings
    (source,canonical_match_id,source_match_id,source_market_id,
     market_type,period,line_raw,line,side,option,odds,
     created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(source,source_match_id,source_market_id,option)
    DO UPDATE SET
      canonical_match_id=excluded.canonical_match_id,
      market_type=excluded.market_type,
      period=excluded.period,
      line_raw=excluded.line_raw,
      line=excluded.line,
      side=excluded.side,
      odds=excluded.odds,
      updated_at=excluded.updated_at
    """,(
        m.source,
        canonical_match_id,
        source_match_id or "",
        m.source_market_id,
        m.market_type,
        m.period,
        m.line_raw,
        m.line,
        m.side,
        m.option,
        m.odds,
        now,
        now
    ))

    c.commit()
    c.close()

def get_markets(canonical_match_id):
    c=connect()
    rows=c.execute("""
    SELECT *
    FROM market_mappings
    WHERE canonical_match_id=?
    ORDER BY market_type,period,line,source_market_id,option
    """,(canonical_match_id,)).fetchall()
    c.close()
    return [dict(x) for x in rows]

def get_source_market(source,source_match_id,source_market_id):
    c=connect()
    rows=c.execute("""
    SELECT *
    FROM market_mappings
    WHERE source=? AND source_match_id=? AND source_market_id=?
    ORDER BY option
    """,(source,str(source_match_id),str(source_market_id))).fetchall()
    c.close()
    return [dict(x) for x in rows]

=== mapping/unified_db.py ===

import time
from database.db import connect

def init_unified():
    c=connect()
    c.execute("""
    CREATE TABLE IF NOT EXISTS unified_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        canonical_match_id TEXT,
        source TEXT NOT NULL,
        bookmaker TEXT,
        source_match_id TEXT NOT NULL,
        source_market_id TEXT NOT NULL,
        market_type TEXT NOT NULL,
        period TEXT,
        line_raw TEXT,
        line REAL,
        side TEXT,
        option TEXT NOT NULL,
        odds REAL,
        event_time INTEGER,
        server_time INTEGER,
        received_at INTEGER NOT NULL,
        raw_ref TEXT,
        created_at INTEGER NOT NULL,
        UNIQUE(
          source,
          source_match_id,
          source_market_id,
          option,
          received_at
        )
    )
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_unified_match
    ON unified_snapshots(canonical_match_id,received_at)
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_unified_market
    ON unified_snapshots(
      canonical_match_id,market_type,period,line,received_at
    )
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_unified_source
    ON unified_snapshots(source,source_match_id,received_at)
    """)
    c.commit()
    c.close()

def save_unified(record, canonical_match_id=None):
    now=int(time.time()*1000)
    c=connect()

    c.execute("""
    INSERT OR IGNORE INTO unified_snapshots
    (canonical_match_id,source,bookmaker,
     source_match_id,source_market_id,
     market_type,period,line_raw,line,side,
     option,odds,event_time,server_time,
     received_at,raw_ref,created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """,(
        canonical_match_id,
        record.source,
        record.bookmaker,
        record.source_match_id,
        record.source_market_id,
        record.market_type,
        record.period,
        record.line_raw,
        record.line,
        record.side,
        record.option,
        record.odds,
        record.event_time,
        record.server_time,
        record.received_at,
        record.raw_ref,
        now
    ))

    c.commit()
    c.close()

def get_match(canonical_match_id,limit=500):
    c=connect()
    rows=c.execute("""
    SELECT *
    FROM unified_snapshots
    WHERE canonical_match_id=?
    ORDER BY received_at ASC,id ASC
    LIMIT ?
    """,(canonical_match_id,limit)).fetchall()
    c.close()
    return [dict(x) for x in rows]

def get_market(canonical_match_id,market_type,
               period=None,limit=500):
    c=connect()

    if period is None:
        rows=c.execute("""
        SELECT *
        FROM unified_snapshots
        WHERE canonical_match_id=?
          AND market_type=?
        ORDER BY received_at ASC,id ASC
        LIMIT ?
        """,(canonical_match_id,market_type,limit)).fetchall()
    else:
        rows=c.execute("""
        SELECT *
        FROM unified_snapshots
        WHERE canonical_match_id=?
          AND market_type=?
          AND period=?
        ORDER BY received_at ASC,id ASC
        LIMIT ?
        """,(canonical_match_id,market_type,period,limit)).fetchall()

    c.close()
    return [dict(x) for x in rows]

=== events/engine_v3.py ===

import sqlite3,time,hashlib
from events.line import compare_line
from core.log import start,finish,error

DB="data/bb.db"

def h(*x):
 s="|".join("" if v is None else str(v) for v in x)
 return hashlib.sha256(s.encode()).hexdigest()

def main():
 log_id=start("EVENT","unified")
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute("""create table if not exists events_v3(
 id integer primary key,canonical_match_id text,source text,
 source_match_id text,market_type text,period text,side text,
 option text,old_line_raw text,new_line_raw text,old_odds real,
 new_odds real,odds_direction text,line_direction text,
 line_change_type text,event_type text,old_time integer,new_time integer,
 event_hash text unique,created_at integer)""")
 rows=c.execute("""select * from unified_snapshots
 where canonical_match_id is not null
 order by received_at,id""").fetchall()
 ts=sorted(set(r["received_at"] for r in rows))
 if len(ts)<2:
  finish(log_id,"OK",len(rows),0,"需要至少2个时间点")
  print("需要至少2个时间点");return
 oldt,newt=ts[-2:]
 A=[r for r in rows if r["received_at"]==oldt]
 B=[r for r in rows if r["received_at"]==newt]
 old={}
 for r in A:
  k=(r["source"],r["canonical_match_id"],r["market_type"],
     r["period"],r["side"],r["option"])
  old.setdefault(k,[]).append(r)
 n=0
 for r in B:
  k=(r["source"],r["canonical_match_id"],r["market_type"],
     r["period"],r["side"],r["option"])
  cand=old.get(k,[])
  if not cand: continue
  a=min(cand,key=lambda x:abs((x["line"] or 0)-(r["line"] or 0)))
  od=a["odds"]!=r["odds"]
  lc=str(a["line_raw"])!=str(r["line_raw"])
  info=compare_line(a["line_raw"],r["line_raw"]) if lc else None
  events=[]
  if od: events.append(("WATER_CHANGE",None))
  if info and info["changed"]: events.append(("LINE_CHANGE",info))
  for typ,li in events:
   d=None
   if od: d="UP" if r["odds"]>a["odds"] else "DOWN"
   eh=h(r["canonical_match_id"],r["source"],k,a["line_raw"],
        r["line_raw"],a["odds"],r["odds"],oldt,newt,typ)
   x=c.execute("""insert or ignore into events_v3
   (canonical_match_id,source,source_match_id,market_type,period,side,
    option,old_line_raw,new_line_raw,old_odds,new_odds,odds_direction,
    line_direction,line_change_type,event_type,old_time,new_time,
    event_hash,created_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
   (r["canonical_match_id"],r["source"],r["source_match_id"],
    r["market_type"],r["period"],r["side"],r["option"],
    a["line_raw"],r["line_raw"],a["odds"],r["odds"],d,
    li["direction"] if li else None,li["change_type"] if li else None,
    typ,oldt,newt,eh,int(time.time()*1000)))
   n+=x.rowcount
 c.commit()
 finish(log_id,"OK",len(rows),n,"T1=%s T2=%s" % (oldt,newt))
 print("T1",oldt,"T2",newt)
 print("新增事件",n)
 for x in c.execute("select event_type,count(*) n from events_v3 group by event_type"):
  print(x["event_type"],x["n"])
 c.close()

if __name__=="__main__": main()

=== replay/event_v1.py ===

import sqlite3,time,hashlib
from events.line import compare_line

DB="data/bb.db"

def h(*x):
 return hashlib.sha256("|".join("" if v is None else str(v) for v in x).encode()).hexdigest()

def replay(c,oldt,newt):
 A=c.execute("select * from unified_snapshots where received_at=? and canonical_match_id is not null",(oldt,)).fetchall()
 B=c.execute("select * from unified_snapshots where received_at=? and canonical_match_id is not null",(newt,)).fetchall()

 old={}
 for r in A:
  k=(r["source"],r["canonical_match_id"],r["market_type"],r["period"],r["side"],r["option"])
  old.setdefault(k,[]).append(r)

 n=0
 for r in B:
  k=(r["source"],r["canonical_match_id"],r["market_type"],r["period"],r["side"],r["option"])
  cand=old.get(k,[])
  if not cand: continue
  a=min(cand,key=lambda x:abs((x["line"] or 0)-(r["line"] or 0)))

  od=a["odds"]!=r["odds"]
  lc=str(a["line_raw"])!=str(r["line_raw"])
  info=compare_line(a["line_raw"],r["line_raw"]) if lc else None

  if od:
   n+=1
  if info and info["changed"]:
   n+=1
 return n

def main():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row

 c.execute("""create table if not exists replay_events_v1(
 id integer primary key,old_time integer,new_time integer,
 event_count integer,created_at integer,
 replay_hash text unique)""")

 ts=[r[0] for r in c.execute(
  "select distinct received_at from unified_snapshots order by received_at")]

 ts=[x for x in ts if x>1788658122585]

 total=0
 for a,b in zip(ts,ts[1:]):
  n=replay(c,a,b)
  total+=n
  hsh=h(a,b,n)
  c.execute("""insert or ignore into replay_events_v1
  (old_time,new_time,event_count,created_at,replay_hash)
  values(?,?,?,?,?)""",(a,b,n,int(time.time()*1000),hsh))
  print("WINDOW",a,b,"EVENTS",n)

 c.commit()
 print("TOTAL",total)
 c.close()

if __name__=="__main__":main()

=== replay/event_v2.py ===

import sqlite3,time,hashlib
from events.line import compare_line

DB="data/bb.db"

def h(*x):
 return hashlib.sha256("|".join("" if v is None else str(v) for v in x).encode()).hexdigest()

def main():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute("""create table if not exists replay_events_v2(
 id integer primary key,old_time integer,new_time integer,
 canonical_match_id text,source text,market_type text,period text,
 side text,option text,old_line_raw text,new_line_raw text,
 old_odds real,new_odds real,odds_direction text,
 line_direction text,line_change_type text,event_type text,
 event_hash text unique,created_at integer)""")

 ts=[r[0] for r in c.execute(
  "select distinct received_at from unified_snapshots order by received_at")]
 ts=[x for x in ts if x>1788658122585]

 total=0

 for oldt,newt in zip(ts,ts[1:]):
  A=c.execute("select * from unified_snapshots where received_at=? and canonical_match_id is not null",(oldt,)).fetchall()
  B=c.execute("select * from unified_snapshots where received_at=? and canonical_match_id is not null",(newt,)).fetchall()

  old={}
  for r in A:
   k=(r["source"],r["canonical_match_id"],r["market_type"],
      r["period"],r["side"],r["option"])
   old.setdefault(k,[]).append(r)

  n=0

  for r in B:
   k=(r["source"],r["canonical_match_id"],r["market_type"],
      r["period"],r["side"],r["option"])
   cand=old.get(k,[])
   if not cand: continue

   a=min(cand,key=lambda x:abs((x["line"] or 0)-(r["line"] or 0)))
   od=a["odds"]!=r["odds"]
   lc=str(a["line_raw"])!=str(r["line_raw"])
   info=compare_line(a["line_raw"],r["line_raw"]) if lc else None
   events=[]

   if od: events.append(("WATER_CHANGE",None))
   if info and info["changed"]: events.append(("LINE_CHANGE",info))

   for typ,li in events:
    d=None
    if od:
     d="UP" if r["odds"]>a["odds"] else "DOWN"

    eh=h(r["canonical_match_id"],r["source"],k,
         a["line_raw"],r["line_raw"],a["odds"],
         r["odds"],oldt,newt,typ)

    x=c.execute("""insert or ignore into replay_events_v2(
    old_time,new_time,canonical_match_id,source,market_type,period,
    side,option,old_line_raw,new_line_raw,old_odds,new_odds,
    odds_direction,line_direction,line_change_type,event_type,
    event_hash,created_at)
    values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (oldt,newt,r["canonical_match_id"],r["source"],
     r["market_type"],r["period"],r["side"],r["option"],
     a["line_raw"],r["line_raw"],a["odds"],r["odds"],d,
     li["direction"] if li else None,
     li["change_type"] if li else None,
     typ,eh,int(time.time()*1000)))

    n+=x.rowcount

  total+=n
  print("WINDOW",oldt,newt,"EVENTS",n)

 c.commit()

 print("TOTAL",total)
 for r in c.execute("""select event_type,count(*) n
 from replay_events_v2 group by event_type"""):
  print(r["event_type"],r["n"])

 c.close()

if __name__=="__main__":main()
