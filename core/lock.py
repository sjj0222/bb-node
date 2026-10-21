"""单实例锁(规格 14.1/14.2 Phase 1)。

用途: 防止采集调度器/monitor/稳定性测试在同一节点上被多进程重复启动,
     避免重复任务写库、PID 复用误杀等其他进程。

设计:
  - 锁文件位于 run/<name>.lock (run/ 已 gitignore), JSON 记录 pid/名称/令牌/启动时间。
  - 原子创建: os.open(O_CREAT|O_EXCL); 创建失败表示被占用。
  - 占用时读取锁内容, 按以下顺序判定 stale:
      1) pid 不存在(进程已死)               -> stale, 可接管
      2) pid 存在但 /proc/<pid>/cmdline 读不到 -> 未知, 保守视为占用(防误杀)
      3) pid 存在且 cmdline 不包含本程序标记  -> stale(PID 被其他程序复用), 可接管
      4) pid 存在且 cmdline 包含本程序标记  -> 真占用, 拒绝
  - 接管 stale 锁: 先删除旧锁文件, 再以 O_EXCL 重试(防两个接管者竞争)。
  - 释放: 仅当锁内容令牌与自身令牌一致时删除(不误删他人锁)。

Termux/Linux 为一级环境(/proc 可用); Windows 无 /proc 时退化为
"pid 存活即视为占用", 安全优先。
"""
import json
import os
import socket
import sys
import time

from core import env

LOCK_SUFFIX = ".lock"

# 本程序在命令行中的特征标记(用于防 PID 复用误判)
# 覆盖: python cli.py / python -m cli / python cli / stability/run.py / -m stability.run
_DEFAULT_MARKERS = ("cli.py", "cli", "bb-node", "bb_node", "bbnode",
                    "stability/run.py", "stability.run")


class AlreadyLocked(Exception):
    """锁被占用且不满足接管条件。"""


class LockHandle:
    def __init__(self, path, token):
        self.path = path
        self.token = token
        self._released = False

    def release(self):
        if self._released:
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                cur = json.load(f)
            if cur.get("token") == self.token:
                os.unlink(self.path)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        self._released = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def _lock_path(name):
    return os.path.join(env.run_dir(), name + LOCK_SUFFIX)


def _pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _cmdline(pid):
    """返回进程 cmdline 字符串; 无法读取返回 None。"""
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            raw = f.read().replace(b"\x00", b" ")
        return raw.decode("utf-8", errors="ignore")
    except OSError:
        return None


def _cmdline_matches(cmd, markers):
    if cmd is None:
        return None  # 未知
    return any(m in cmd for m in markers)


def _read_lock(path):
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _try_create(path, name, token):
    payload = {
        "pid": os.getpid(),
        "name": name,
        "token": token,
        "started_at": int(time.time() * 1000),
        "host": socket.gethostname(),
        "cmd": " ".join(sys.argv[:3]),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    return True


def _stale_reason(lock, markers):
    """返回 stale 原因字符串; 非 stale 返回 None。"""
    if not lock:
        return "lock 内容不可读"
    pid = lock.get("pid")
    if not _pid_alive(pid):
        return "pid %s 不存在" % pid
    cmd = _cmdline(pid)
    m = _cmdline_matches(cmd, markers)
    if m is None:
        return None  # 无 /proc, 无法确认 → 保守视为占用
    if not m:
        return "pid %s 被其他程序复用(cmdline 不含本程序标记)" % pid
    return None


def acquire(name, timeout=0, markers=None, block=True):
    """获取单实例锁。

    参数:
      name: 锁名(如 "monitor", "stability24h", "pipeline")
      timeout: 等待秒数; 0 表示只试一次(不等待)
      markers: 用于 PID 复用的命令行特征; 默认 _DEFAULT_MARKERS
      block: False 时即使 timeout>0 也不等待(兼容语义), 默认 True

    返回:
      LockHandle 或 None(被占用且未在 timeout 内获得)

    抛异常:
      AlreadyLocked: 占用且判定为真实占用(仅当 block=False 且想区分"等不到"时可不捕获)
    """
    path = _lock_path(name)
    os.makedirs(env.run_dir(), exist_ok=True)
    token = "%d.%f" % (os.getpid(), time.time())
    if markers is None:
        markers = _DEFAULT_MARKERS
    deadline = time.time() + max(0, timeout)

    while True:
        if _try_create(path, name, token):
            return LockHandle(path, token)
        # 被占用 → 检查是否 stale
        lock = _read_lock(path)
        reason = _stale_reason(lock, markers)
        if reason:
            # 安全接管: 先删旧, 再 O_EXCL 竞争; 输掉则回到循环
            try:
                os.unlink(path)
            except OSError:
                pass
            if _try_create(path, name, token):
                return LockHandle(path, token)
        if not block or time.time() >= deadline:
            return None
        time.sleep(0.5)
