"""Phase 4 测试: 标准化与数据质量(规格 §7)。

覆盖:
  1. 迁移 v5: quality_errors 拒绝表
  2. validator 四层校验(结构/语义/时间)
  3. collector: 校验失败不静默丢弃, 落拒绝表, 不伪造缺失值
  4. Normalizer 版本化: 输出携带 normalizer 名/版本/config hash/RAW ID
  5. 确定性: 同输入两次 normalize 输出一致
  6. 错误可从 RAW 重放
"""
import dataclasses
import json
import math

from sources import bb as bb_mod
from sources import sx as sx_mod
from core import collector, env
from database import db as database
from quality import validator as v
from quality import errors as qerr
from tests.helpers import nrec

_MATCH = {
    "id": "9001",
    "lg": {"id": 11062},
    "ts": [{"na": "Manchester United"}, {"na": "Chelsea"}],
    "bt": 1700000000000,
    "mg": [{"mty": "1000", "pe": 0, "mks": [
        {"id": "k1", "li": "-0.5", "op": [
            {"li": "-0.5", "od": "1.90", "na": "主队-0.5"},
            {"li": "-0.5", "od": "2.05", "na": "客队+0.5"}]}]}],
}


# ---------- 1. 迁移 v5 ----------

def test_migrate_v5_rejection_table(db):
    tables = {r[0] for r in db.execute(
        "select name from sqlite_master where type='table'")}
    assert "quality_errors" in tables
    assert db.execute("PRAGMA user_version").fetchone()[0] == 10


def test_migrate_v5_idempotent(db):
    database.init()
    con = database.connect()
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    con.close()


# ---------- 2. validator ----------

def _rec(**kw):
    """构造一条记录; odds/received_at/market_type/option 是 nrec 定位参数。"""
    odds = kw.pop("odds", 1.90)
    received_at = kw.pop("received_at", 5000)
    market_type = kw.pop("market_type", "1000")
    option = kw.pop("option", "主队-0.5")
    return nrec("bb", "m1", "mm1", market_type, "-0.5", option, odds,
                received_at, **kw)


def test_validator_ok():
    assert v.validate(_rec()) == []


def test_validator_odds_missing():
    errs = v.validate(_rec(odds=None))
    assert any(code == v.ODDS_MISSING for _, code, _ in errs)


def test_validator_odds_out_of_range():
    assert any(code == v.ODDS_OUT_OF_RANGE
               for _, code, _ in v.validate(_rec(odds=0.5)))
    assert any(code == v.ODDS_OUT_OF_RANGE
               for _, code, _ in v.validate(_rec(odds=99.0)))


def test_validator_line_invalid():
    assert any(code == v.LINE_INVALID
               for _, code, _ in v.validate(_rec(line=math.inf)))


def test_validator_missing_field():
    errs = v.validate(_rec(home=None))
    assert any(code == v.MISSING_FIELD for _, code, _ in errs)


def test_validator_time_order():
    # server_time 晚于 received_at 超过容差(10min) -> TIME_ORDER
    errs = v.validate(_rec(server_time=1000 + 700000, received_at=1000))
    assert any(code == v.TIME_ORDER for _, code, _ in errs)


# ---------- 3. collector 集成 ----------

def test_collector_rejects_bad_odds_to_queue(db):
    con = db
    bad = _rec(odds=None)
    counts = {"mapped": 0, "unmapped": 0, "invalid": 0,
              "pending": 0, "unified": 0}
    collector._process_records([bad], counts, con, source="bb", run_id=9)
    con.commit()
    assert counts["invalid"] == 1
    assert counts["unified"] == 0       # 缺失值不被伪造
    rows = con.execute("select layer,code,status from quality_errors").fetchall()
    assert rows, "校验失败必须落拒绝表"
    assert any(r[1] == "ODDS_MISSING" for r in rows)
    assert all(r[2] == "open" for r in rows)


def test_quality_errors_upsert_dedup(db):
    con = db
    bad = _rec(odds=None, raw_ref="same-hash")
    collector._process_records([bad, bad], counts := {
        "mapped": 0, "unmapped": 0, "invalid": 0,
        "pending": 0, "unified": 0}, con, source="bb", run_id=9)
    con.commit()
    rows = con.execute(
        "select retried_count from quality_errors where raw_ref=?",
        ("same-hash",)).fetchall()
    assert len(rows) == 1          # 幂等合并
    assert rows[0][0] >= 1


# ---------- 4. Normalizer 版本化 ----------

def test_bb_normalize_metadata():
    recs = bb_mod.BBAdapter(leagues={}).normalize(_MATCH, 5000, raw_ref="h" * 64)
    assert recs
    r = recs[0]
    assert r.normalizer_name == "bb"
    assert r.normalizer_version == "bb-normalize-v1"
    assert r.config_hash
    assert r.raw_ref == "h" * 64


def test_sx_normalizer_constant():
    assert sx_mod.SXBetAdapter.NORMALIZER_VERSION.startswith("sx-normalize")


# ---------- 5. 确定性(§7.3) ----------

def test_normalize_deterministic():
    a = bb_mod.BBAdapter(leagues={})
    r1 = [dataclasses.asdict(r) for r in a.normalize(_MATCH, 5000)]
    r2 = [dataclasses.asdict(r) for r in a.normalize(_MATCH, 5000)]
    assert r1 == r2


# ---------- 6. 可从 RAW 重放 ----------

def test_quality_error_replayable_from_raw(db, tmp_path, monkeypatch):
    raw_ref = "c" * 64
    # 在 raw 目录真实落一个 RAW 文件(重放入口)
    raw_dir = env.raw_dir("bb")
    import os
    os.makedirs(raw_dir, exist_ok=True)
    with open(os.path.join(raw_dir, raw_ref + ".json"), "w",
              encoding="utf-8") as f:
        json.dump(_MATCH, f)
    path = qerr.raw_path_for("bb", raw_ref)
    assert os.path.exists(path)
    # 从 RAW 文件可重新解析出记录
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    recs = bb_mod.BBAdapter(leagues={}).normalize(payload, 5000, raw_ref)
    assert recs and recs[0].source_match_id == "9001"
