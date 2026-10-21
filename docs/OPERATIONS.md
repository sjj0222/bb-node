# bb-node 运维手册 (Phase 13, 0.3.0-rc1)

## 1. 日常运行

```sh
# 单轮采集(bb + sx)
python3 cli.py collect bb                   # 或 sx; 幂等, 失败可重试
# 守护监控(多轮, 持锁)
python3 cli.py monitor start --interval 60
python3 cli.py monitor status               # 状态/最近成功采集时间
# 24h 稳定性(发布门槛, Termux 真机)
python3 stability/run.py --hours 24
```

## 2. 数据与查询

```sh
python3 cli.py unified query  --match <canonical_match_id>     # 多条件查询
python3 cli.py unified latest --match <id>                     # 最新值视图
python3 cli.py unified series --match <id> --market asian_handicap  # 时间序列
python3 cli.py unified compare --match <id> --market asian_handicap  # 跨源对比
python3 cli.py unified plan --json         # EXPLAIN QUERY PLAN 基线
```

## 3. 映射人工审批(Phase 5)

```sh
python3 cli.py mapping list                          # pending 队列
python3 cli.py mapping approve --index <n> --operator <name> --note "..."
python3 cli.py mapping audit                        # 审计历史
```
所有映射变更写 mapping_audit; 旧 canonical 下游 unified 标记 superseded
(不删除历史)。

## 4. 质量与事件

```sh
python3 cli.py quality run                          # 质量校验入口
# 事件/特征/信号/回放为库级服务(event/features/signals/replay 模块),
# 测试覆盖见 tests/test_phase8.py
```

## 5. 备份与恢复(Phase 11)

```sh
python3 cli.py backup create --retention-days 14     # 备份+sha256+清单+保留
python3 cli.py backup list
python3 cli.py backup restore --file <备份.db> --force
```
备份写临时文件后原子重命名; 校验和与 integrity_check 通过才可恢复。

## 6. 安全(Phase 11)

```sh
python3 cli.py security scan --max-matches 100       # 秘密明文扫描
python3 cli.py security rotate --max-bytes 52428800 # 日志轮转(50MB/保留5份)
```
约束: API Token/Cookie/密码不得入库、入日志、入诊断包(§13.2);
`.env` 仅在 .gitignore 内本地使用。

## 7. 稳定性门槛(Phase 12, R8 修复)

终态判定(可审计原因码):
- errors==0 -> PASS
- 有错误: rounds>=4 且错误率<=25% 且恢复率>=50% -> PASS, 否则 ERROR
结果与 status_reason 落 stability_runs; 状态文件 run/stability/*.json。

## 8. 已知限制(诚实披露)

- 后台常驻: Android 电池优化/休眠/网络切换可能杀进程, 不承诺绝对常驻;
  提供手动恢复与状态检查(§14.1)。
- 主盘口选择默认策略 main-v1(来源优先级 bb>sx, 冲突取优先级+原因码);
  策略参数为代码常量, 调整需改代码并回归。
- 新字段(odds_raw/line_quarters/league_id/content_hash)只对新数据生效,
  历史 27,891 条 unified 不伪造回填。
- 24h 稳定性需 Termux 真机最终验收(云环境曾因资源回收中断, 非代码缺陷)。
- Phase 14(Windows/Android UI 与同步)可延期, 不阻塞本地核心发布。
