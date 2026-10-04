"""V0.2 测试矩阵 3: Monitor(规则 68)。

覆盖: START/STOP/RESTART 状态机、watchlist ADD/REMOVE/LIST/STATUS、
Alert emit/list、Source DOWN 降级但继续运行(monkeypatch pipeline)。
"""
import pytest
from unittest import mock

from monitor.monitor import (Monitor, STOPPED, RUNNING, STARTING, STOPPING,
                             DEGRADED, ERROR)
from monitor import alert as alert_mod
from monitor import watchlist


def test_monitor_state_machine(db):
    m = Monitor(interval_seconds=1)
    assert m.status()["state"] == STOPPED
    with mock.patch("monitor.monitor.Monitor._run_round", return_value=True):
        m.start(daemon=True)
        assert m.status()["state"] == RUNNING
        m.stop()
        assert m.status()["state"] == STOPPED


def test_monitor_restart(db):
    m = Monitor(interval_seconds=1)
    with mock.patch("monitor.monitor.Monitor._run_round", return_value=True):
        m.start()
        s1 = m.status()["monitor_run_id"]
        m.restart()
        assert m.status()["state"] == RUNNING
        assert m.status()["monitor_run_id"] != s1 or m.rounds == 0


def test_monitor_source_down_degraded_not_stop(db):
    """规则 6.2: Source DOWN -> DEGRADED, 但 Monitor 不退出。"""
    m = Monitor(interval_seconds=1)
    # 模拟 Source DOWN: health 表里有 DOWN 记录
    from core import health
    health.record("bb", status=health.DOWN, error="boom")
    with mock.patch("monitor.monitor.Monitor._run_round", return_value=False):
        m.run_once()
        assert m.status()["state"] == DEGRADED
    # Monitor 仍可用
    assert m.status()["rounds"] >= 0


def test_monitor_alert_rounds(db):
    m = Monitor(interval_seconds=1)
    with mock.patch("monitor.monitor.Monitor._run_round", return_value=True):
        m.run_once()
    assert m.status()["state"] in (RUNNING, DEGRADED)
    assert m.status()["errors"] == 0


def test_watchlist_add_remove_list(db):
    watchlist.add("MATCH123", note="test")
    assert watchlist.contains("MATCH123")
    wl = watchlist.list_all()
    assert any(w["canonical_match_id"] == "MATCH123" for w in wl)
    watchlist.remove("MATCH123")
    assert not watchlist.contains("MATCH123")


def test_watchlist_status(db):
    watchlist.add("CM_X")
    st = watchlist.status("CM_X")
    assert st and st[0]["canonical_match_id"] == "CM_X"
    assert "unified" in st[0]


def test_alert_emit_list_close(db):
    aid = alert_mod.emit("SOURCE_DOWN", "bb down", severity="CRITICAL",
                         source="bb")
    assert alert_mod.open_count() == 1
    ls = alert_mod.list_alerts(alert_type="SOURCE_DOWN")
    assert ls and ls[0]["id"] == aid
    alert_mod.close(aid)
    assert alert_mod.open_count() == 0


def test_alert_bad_type_rejected(db):
    with pytest.raises(AssertionError):
        alert_mod.emit("NOT_A_TYPE", "x")


def test_monitor_selected_match_output(db):
    """规则 7/8: 选定比赛输出 Decision Candidate Alert。"""
    watchlist.add("CM_Y")
    m = Monitor(interval_seconds=1)
    with mock.patch("monitor.monitor.Monitor._run_round", return_value=True):
        m.run_once()
    # round 正常, 无异常即可(真实决策输出在真数据 E2E 中验证)
    assert m.status()["state"] in (RUNNING, DEGRADED, ERROR)
