# CI 报告(Phase 13, 0.3.0-rc1)

当前无云端 CI 配置; 以下为本地全量回归基线(可复现), 作为发布候选门槛。

## 复现命令

```sh
cd bb-node
python3 -m pytest tests/ -q -p no:cacheprovider
```

## 结果(本发布候选实测)

- 全量通过: **242 passed** (46.2s), 0 failed / 0 error。
- 覆盖 Phase 1-13: test_phase1..10 + 既有 v0.2 测试(115 基线回归未删)。
- 关键专项:
  - R1 符号修复边界(parse_line_quarters 4 例)
  - R8 稳定性门限(6 例含边界)
  - 未来数据泄漏(as_of 排除未来观测)
  - 备份往返/篡改拒绝/保留策略
  - 事件幂等/消费幂等/回放确定性/回测严格切分

## 真实库验收(本环境实测)

- cli.py init 幂等迁移: user_version 3->4->...->11, 每步核对。
- 真实库(clone 基线 27,891 条 unified / 14.06MB):
  - Phase 5: 326 条既有映射回填 valid_from/rule_version
  - Phase 6/7: 新列(odds_raw/line_quarters/league_id/content_hash)
    对旧数据保持 NULL(不伪造)
  - Phase 11: backup create 实测 14.7MB, integrity ok, sha256 校验;
    security scan 0 处疑似秘密
  - Phase 12: stability 短时预演 1 轮真实采集, errors=0 -> PASS
    (reason: clean: errors=0), 终态与原因码落 stability_runs
- WAL 完整性: 基线 `PRAGMA integrity_check` = ok。

## 未覆盖 / 需外部环境

- 24h Termux 真机稳定性(云环境资源回收中断过, 非代码缺陷; 验收命令
  `python3 stability/run.py --hours 24`)。
- 推送 GitHub 远程(缺写权限凭据)。
- 云端 CI(未配置)。
