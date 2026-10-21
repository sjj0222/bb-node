"""CLI/锁测试辅助进程: 获取并持有指定锁一段时间。

用法: python3 tests/_lock_helper.py <lock_name>
cmdline 包含仓库绝对路径(含 "bb-node"), 以便单实例锁的 PID 复用检测
能将其识别为本程序进程。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import lock


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "testlock"
    h = lock.acquire(name, timeout=0)
    if h is None:
        print("LOCK_BUSY %s" % name)
        return 1
    print("LOCKED %s pid=%s" % (name, os.getpid()), flush=True)
    time.sleep(30)
    h.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
