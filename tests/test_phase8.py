"""Phase 8-10 测试: 事件/特征/信号/回放/回测(规格 §10-11)。

覆盖:
  1. 事件引擎: 幂等去重/发生时间与记录时间分离/消费幂等/稳定排序/
     赔率变化与映射批准事件接入
  2. 特征引擎: as_of 无未来泄漏/空值不填 0/失败记录原因/版本化不覆盖
  3. 信号引擎: 评估落库/生命周期 supersede/规则变更回归差异留痕
  4. Replay: 隔离输出/可复现顺序/失败清理不碰生产/按事件时间模式标注
  5. Backtest: 严格切分/缺失剔除报告/无泄漏/免责声明/输出字段
  6. 迁移 v9
"""
import json
import time

from database import db as database
from core import env
from event import engine as ev
from features import engine as fe
from signals import rules as sr
from replay import engine as rp
from mapping.unified_service import unify
from tests.helpers import nrec


def _put(db, smid="m1", odds=1.90, received_at=None, event_time=None):
    received_at = received_at or int(time.time() * 1000)
    rec = nrec("bb", smid, "k%s" % smid, "1000", "-0.5", "主队-0.5",
               odds, received_at, event_time=event_time,
               home="Manchester United", away="Chelsea")
    unify(rec, canonical_match_id="cm_e1", conn=db)


def _seed_quotes(db, base_t, steps):
    """base_t 起逐刻写入 HOME/AWAY 亚盘报价(供特征/信号)。

    side 由 option 文本在 normalize 推导: 主队-0.5 -> HOME, 客队+0.5 -> AWAY
    """
    for i, (ho, ao) in enumerate(steps):
        t = base_t + i * 5 * 60 * 1000
        rec_h = nrec("bb", "q%d" % i, "kh%d" % i, "1000", "-0.5",
                     "主队-0.5", ho, t, event_time=t,
                     home="Manchester United", away="Chelsea")
        unify(rec_h, canonical_match_id="cm_f1", conn=db)
        rec_a = nrec("bb", "q%d" % i, "ka%d" % i, "1000", "-0.5",
                     "客队+0.5", ao, t, event_time=t,
                     home="Manchester United", away="Chelsea")
        unify(rec_a, canonical_match_id="cm_f1", conn=db)
    db.commit()


# ---------- 1. 事件引擎 ----------

def test_emit_dedup(db):
    a = ev.emit(db, source="bb", event_type="match_new",
                entity_key="e1", event_time=1000, payload={"id": "e1"})
    b = ev.emit(db, source="bb", event_type="match_new",
                entity_key="e1", event_time=1000, payload={"id": "e1"})
    assert a is True and b is False          # 相同输入重复 -> 幂等
    assert db.execute("select count(*) from events").fetchone()[0] == 1


def test_event_time_vs_recorded(db):
    ev.emit(db, source="bb", event_type="odds_changed", entity_key="k1",
            event_time=5000, recorded_at=9000, payload={})
    row = db.execute("select event_time, recorded_at from events").fetchone()
    assert row[0] == 5000 and row[1] == 9000   # 两态分离


def test_consume_idempotent_and_order(db):
    ev.emit(db, source="bb", event_type="a", entity_key="x",
            event_time=100, payload={})
    ev.emit(db, source="bb", event_type="b", entity_key="x",
            event_time=200, payload={})
    first = list(ev.iter_events(db, "consumer1"))
    again = list(ev.iter_events(db, "consumer1"))
    assert [e["event_type"] for e in first] == ["a", "b"]
    assert all(e["consumed"] is True for e in first)
    assert all(e["consumed"] is False for e in again)  # 幂等消费


def test_quote_change_event_emitted(db):
    now = int(time.time() * 1000)
    _put(db, smid="chg1", odds=1.90, received_at=now - 1000)
    _put(db, smid="chg1", odds=2.10, received_at=now)
    db.commit()
    evs = [e for e in ev.iter_events(db, "t") if e["event_type"] ==
           "quote_changed"]
    assert len(evs) == 1
    p = evs[0]["payload"]
    assert p["canonical_match_id"] == "cm_e1"
    assert p["source_market_id"] == "kchg1"
    assert p["content_hash_before"] != p["content_hash_after"]
    assert evs[0]["entity_key"].startswith("cm_e1")


# ---------- 2. 特征引擎 ----------

def test_feature_as_of_no_future_leak(db):
    base = int(time.time() * 1000) - 200 * 60 * 1000
    _seed_quotes(db, base, [(1.90, 2.00), (1.95, 1.95), (2.10, 1.90)])
    v_t1 = fe.compute_feature(db, "ah_odds_spread", "cm_f1", base)
    v_t15 = fe.compute_feature(db, "ah_odds_spread", "cm_f1",
                               base + 5 * 60 * 1000)
    v_t2 = fe.compute_feature(db, "ah_odds_spread", "cm_f1",
                              base + 10 * 60 * 1000)
    # T1 只能用 T1 前数据(第1刻 spread=-0.10); T+5m 用前两刻(0.00);
    # T+10m 用前三刻(0.20)
    assert abs(v_t1 - (-0.10)) < 1e-6
    assert abs(v_t15 - 0.0) < 1e-6
    assert abs(v_t2 - 0.20) < 1e-6
    # 泄漏测试: as_of 早于未来观测 -> 未来值不可见
    v_future = fe.compute_feature(db, "ah_odds_spread", "cm_f1",
                                  base - 5 * 60 * 1000)
    assert v_future is None                    # 无数据 -> 缺失, 不填 0


def test_feature_null_no_zero_default(db):
    base = int(time.time() * 1000) - 60 * 60 * 1000
    _seed_quotes(db, base, [(1.90, 2.00)])
    v = fe.compute_feature(db, "ah_odds_spread", "cm_none", base)
    assert v is None                           # 空值策略 absent, 不伪造 0
    n_err = db.execute("select count(*) from feature_errors").fetchone()[0]
    assert n_err == 0                          # 无数据不是失败, 不记录错误


def test_feature_error_recorded_on_failure(db):
    base = int(time.time() * 1000) - 60 * 60 * 1000
    v = fe.compute_feature(db, "odds_volatility_30m", "cm_f1", base)
    assert v is None
    # 真实失败路径: 用不存在特征的实现名强制公式缺失
    err = db.execute("""select count(*) from feature_errors
                        where feature_name='odds_volatility_30m'""").fetchone()
    assert err[0] == 0                        # 无数据仍非失败
    fe.compute_feature(db, "not_a_feature", "cm_f1", base)   # 未知特征
    assert db.execute(
        "select count(*) from feature_errors").fetchone()[0] == 1


def test_feature_version_keeps_old(db):
    base = int(time.time() * 1000) - 60 * 60 * 1000
    _seed_quotes(db, base, [(1.90, 2.00)])
    fe.compute_feature(db, "ah_odds_spread", "cm_f1", base)
    fe.compute_feature(db, "odds_volatility_30m", "cm_f1", base)
    n_versions = db.execute(
        "select count(distinct version) from feature_results").fetchone()[0]
    assert n_versions >= 2                     # 版本化, 各版本独立保留


# ---------- 3. 信号引擎 ----------

def test_signal_evaluate_and_lifecycle(db):
    base = int(time.time() * 1000) - 200 * 60 * 1000
    # 40 分钟时间轴: spread -0.10 -> 0.20 -> 0.60
    _seed_quotes(db, base, [(1.90, 2.00), (2.10, 1.90), (2.30, 1.70)])
    as_of = base + 35 * 60 * 1000
    res = sr.evaluate(db, "suspension_watch", "cm_f1", as_of)
    assert res["status"] == "active"
    assert res["output"]["fired"] is True      # (0.60-0.20)/0.20 = 200% > 10%
    assert "不自动下注" in res["reason"]
    n = sr.supersede(db, "suspension_watch", "sw-v1",
                     reason="superseded by sw-v2")
    assert n >= 1
    row = db.execute("""select status from signal_results
                        where rule_id='suspension_watch' and version='sw-v1'
                        limit 1""").fetchone()
    assert row[0] == "superseded"


def test_rule_regression_diff_recorded(db):
    base = int(time.time() * 1000) - 200 * 60 * 1000
    _seed_quotes(db, base, [(1.90, 2.00), (2.10, 1.90), (2.30, 1.70)])
    as_of = base + 35 * 60 * 1000
    sr.evaluate(db, "suspension_watch", "cm_f1", as_of)
    rows = sr.run_regression(
        db, "suspension_watch", "sw-v1", "sw-v2",
        [{"match_id": "cm_f1", "as_of_time": as_of}])
    assert rows and rows[0]["diff"].startswith("CHANGED")  # 差异留痕
    dbrow = db.execute("""select diff from rule_regressions
                          order by id desc limit 1""").fetchone()
    assert dbrow and dbrow[0] != "SAME"


# ---------- 4. Replay ----------

def test_replay_isolated_deterministic(db):
    now = int(time.time() * 1000)
    ev.emit(db, source="bb", event_type="x", entity_key="a",
            event_time=now - 3000, recorded_at=now - 3000, payload={})
    ev.emit(db, source="bb", event_type="y", entity_key="b",
            event_time=now - 1000, recorded_at=now - 1000, payload={})
    r1 = rp.replay_run(db, name="r1", start_ms=now - 10000, end_ms=now)
    r2 = rp.replay_run(db, name="r2", start_ms=now - 10000, end_ms=now)
    seq1 = [e["event_type"] for e in rp.replay_results(db, r1["run_id"])]
    seq2 = [e["event_type"] for e in rp.replay_results(db, r2["run_id"])]
    assert seq1 == ["x", "y"] and seq1 == seq2      # 可复现, 稳定排序
    assert r1["summary"]["events"] == 2
    # 生产 events 未被回放改写
    assert db.execute("select count(*) from events").fetchone()[0] == 2


def test_replay_event_time_mode_labeled(db):
    now = int(time.time() * 1000)
    ev.emit(db, source="bb", event_type="z", entity_key="c",
            event_time=now - 5000, recorded_at=now - 1000, payload={})
    r = rp.replay_run(db, name="et", start_ms=now - 10000, end_ms=now,
                      mode="event_time")
    assert r["summary"]["mode"] == "event_time"     # 单独标明模式
    row = db.execute("select mode from replay_runs "
                     "where run_id=?", (r["run_id"],)).fetchone()
    assert row[0] == "event_time"


def test_replay_failure_cleanup(db):
    # 构造回放失败: 无效模式不会写 run 成功态
    try:
        rp.replay_run(db, name="bad", start_ms=1, end_ms=2, mode="wrong")
        assert False
    except ValueError:
        pass
    # 生产 events 无污染
    assert db.execute("select count(*) from events").fetchone()[0] == 0


# ---------- 5. Backtest ----------

def test_backtest_strict_split_no_leak(db):
    now = int(time.time() * 1000)
    base = now - 5 * 60 * 60 * 1000
    _seed_quotes(db, base, [(1.90, 2.00), (1.80, 2.10)])
    train_end = base + 2 * 60 * 60 * 1000
    out = rp.backtest(
        db, rule_id="suspension_watch", version="sw-v1",
        train_start=base - 60 * 60 * 1000, train_end=train_end,
        test_start=train_end, test_end=now,
        params={"threshold_pct": 10.0}, seed=42)
    s = out["summary"]
    assert s["windows"][0]["label"] == "train"
    assert s["windows"][1]["label"] == "test"
    assert s["strict_split"][2] == s["strict_split"][1]  # test 起点=train 终点
    assert any("无未来泄漏" in n for n in s["notes"])
    assert any("不静默填补" in n for n in s["notes"])
    assert any("不代表未来收益保证" in n for n in s["notes"])
    row = db.execute("select summary, seed from backtest_runs "
                     "where run_id=?", (out["run_id"],)).fetchone()
    assert row and json.loads(row[0])["seed"] == 42


def test_backtest_missing_reported_not_filled(db):
    now = int(time.time() * 1000)
    out = rp.backtest(db, rule_id="suspension_watch", version="sw-v1",
                      train_start=now - 20000, train_end=now - 10000,
                      test_start=now - 10000, test_end=now)
    win = out["summary"]["windows"][0]
    assert win["samples"] == 0 and win["missing_excluded"] == 0
    assert win["coverage"] == 0.0


# ---------- 6. 迁移 v9 ----------

def test_migrate_v9(db):
    tables = {r[0] for r in db.execute(
        "select name from sqlite_master where type='table'")}
    for t in ("events", "event_consumers", "feature_results",
              "feature_errors", "signal_results", "rule_regressions",
              "replay_runs", "replay_events", "backtest_runs"):
        assert t in tables, t
    assert db.execute("PRAGMA user_version").fetchone()[0] == 9


def test_config_schema_version_is_9():
    assert env.schema_version() == 9
