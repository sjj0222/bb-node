"""Unit Test: 盘口线解析与事件差分(规则 9/21 + 回归: -0.5 -> -0.75 识别)。

compare_line 返回结构:
  {changed: bool|None, direction: DEEPER/SHALLOWER/SAME/UNKNOWN,
   change_type: QUARTER_STEP/HALF_STEP/MULTI_STEP/SAME/UNKNOWN, steps}
"""
import pytest

from events.line import parse_line, compare_line


def test_parse_single():
    assert parse_line("-0.5") == [-0.5]
    assert parse_line("2.5") == [2.5]
    assert parse_line("0") == [0.0]


def test_parse_split():
    assert parse_line("-1/1.5") == [-1.0, -1.5]
    assert parse_line("0.75/1") == [0.75, 1.0]


def test_parse_invalid():
    assert parse_line("abc") is None
    assert parse_line(None) is None
    assert parse_line("") is None


def test_compare_quarter_deeper():
    # 回归: 盘口 -0.5 -> -0.75 被错误识别的 bug 场景(规则 39)
    res = compare_line("-0.5", "-0.75")
    assert res["changed"] is True
    assert res["direction"] == "DEEPER"
    assert res["change_type"] == "QUARTER_STEP"
    assert res["steps"] == 1


def test_compare_quarter_shallower():
    res = compare_line("-0.75", "-0.5")
    assert res["direction"] == "SHALLOWER"
    assert res["change_type"] == "QUARTER_STEP"


def test_compare_half():
    res = compare_line("-1", "-1.5")
    assert res["direction"] == "DEEPER"
    assert res["change_type"] == "HALF_STEP"


def test_compare_same():
    res = compare_line("-0.5", "-0.5")
    assert res["changed"] is False
    assert res["direction"] == "SAME"


def test_compare_invalid_returns_unknown():
    res = compare_line("abc", "-0.5")
    assert res["changed"] is None
    assert res["direction"] == "UNKNOWN"
    res2 = compare_line("-0.5", None)
    assert res2["changed"] is None
