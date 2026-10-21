# bb-node 安装 / 升级 / 卸载 / 恢复手册

发布候选: 0.3.0-rc1 (Phase 13)。本手册面向 Android Termux 优先, 兼容
普通 Linux。所有命令可重复执行, 不覆盖用户配置与数据库(规格 §14.1)。

## 1. 安装(可重复执行)

```sh
# 1) 克隆(替换为你的写权限方式)
git clone https://github.com/sjj0222/bb-node.git && cd bb-node
# 或从已有副本继续: 进入仓库目录

# 2) 检查运行环境(只读诊断, 不修改)
python3 cli.py check          # 环境/配置/数据库/磁盘/来源/迁移版本
python3 cli.py doctor         # 更细的体检(含锁、路径、权限)

# 3) 初始化(幂等; 已存在库与配置时只做缺失迁移, 不覆盖数据)
python3 cli.py init

# 4) 首次冒烟
python3 -m pytest tests/ -q -p no:cacheprovider   # 开发环境可选
python3 cli.py source status                       # 来源健康
```

前置要求:
- Python >= 3.10(不假定系统 Python 固定; Termux: `pkg install python`)
- 运行时第三方依赖: `requests`(适配器 HTTP 客户端)。
  Termux: `pip install requests`(或 `pkg install python-requests`);
  其余能力均为标准库。
- 数据/日志/运行目录可配置: 环境变量 `BB_NODE_HOME` / `BB_NODE_DB` /
  `BB_NODE_LOG`(未设置时用仓库内默认)。
- **配置必须可解析**: 若把数据目录挪出仓库(`BB_NODE_HOME=/tmp/xxx`),
  必须同时显式设置 `BB_NODE_CONFIG` 指向完整 config/config.json;
  配置缺失/损坏时 CLI 会明确报错退出(不再静默降级), 可先跑
  `cli.py check` 看 config_parse 项。
- 启动前检查目录权限与剩余空间: `cli.py check` 内置磁盘检查。

## 2. 升级(旧库安全升级)

```sh
git pull                                   # 拉取新版本
python3 cli.py init                        # 幂等迁移: 按 MIGRATIONS 链
                                           # 2->3->...->N, 每步有界且不删数据
python3 cli.py backup create               # 升级前建议留备份
python3 cli.py check                       # 确认 user_version == 期望值
```

升级不变量:
- 只增列/建表/建视图/建索引; 不重写、不删除既有行。
- 既有数据回填仅做无损字段(如 valid_from), 绝不伪造新列取值
  (Phase 6/7 新列对旧数据保持 NULL, 只对新数据生效)。

## 3. 卸载

```sh
# 停止所有进程
python3 cli.py monitor stop 2>/dev/null || true
# 移除单实例锁残留
rm -f run/*.lock
# 备份数据后删除仓库(如需彻底清理)
# 注意: bb.db / replay.db / data/raw 为数据本体, 卸载即丢失, 先备份
```

## 4. 恢复(从备份)

```sh
python3 cli.py backup list                 # 找到目标备份文件
python3 cli.py backup restore --file <备份.db> --force
# restore 先做 SHA-256 校验与 integrity_check; 覆盖前自动留存
# <备份.db>.pre-restore.<时间戳>
python3 cli.py check                       # 恢复后体检
```

## 5. Termux 运维注意(规格 §14.1)

- 不承诺在任意 Android ROM 下绝对常驻: 电池优化、网络切换、设备休眠
  可能杀后台。提供 `monitor restart` 手动恢复; 开机自启按用户显式启用。
- 状态与最近成功采集时间: `cli.py monitor status` / `cli.py check`。
- 24h 稳定性验收在 Termux 真机执行:
  `python3 stability/run.py --hours 24`(长任务有超时/心跳/退出清理,
  `run/` 下锁文件与 state.json 可见进度)。
- 磁盘告警: `cli.py check` 输出剩余空间与 DB 大小; 日志按大小轮转
  (`cli.py security rotate`)。

## 6. 故障恢复不依赖清库

- 单实例锁误留: 删除 `run/<name>.lock`(进程已死时)。
- 来源故障: 单来源失败不拖垮其他来源(Phase 3), 状态见 `source status`。
- 质量问题: `quality_errors` 拒绝表保留 raw_ref, 可 RAW 重放。
- 备份损坏: restore 校验和不通过即拒绝, 不覆盖现有库。
