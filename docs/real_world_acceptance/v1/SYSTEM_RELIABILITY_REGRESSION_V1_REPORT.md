# SYSTEM_RELIABILITY_REGRESSION_V1 — 完整 240 回归报告

执行条件(与 Phase2 baseline 一致): branch system-reliability-fix-v1 @ 6ce8533; 冻结 60 张真图; 冻结 F1..P4 8 条 prompt; 8×30=240; MAX_CONCURRENT_JOBS=1; 同 provider/同模型/同 API/Pipeline。本轮仅评系统可靠性, 不重新判视觉质量; 8 条 invalid_test_data 仍在执行(只与视觉合同有关)。

## 1. 240 submitted / success / system failure

- **240 submitted / 240 pipeline success / 0 SYSTEM FAILURE**

## 2. 原 36 SYSTEM FAILURE → success / residual

- 36 / 36 success; residual failure = 0

## 3. 原 204 success → success / regression failure

- 204 / 204 success; regression failure = 0(原成功集无被破坏)

## 4. 每 test_id success/failed

| test | submitted | success | failed |
|---|---|---|---|
| F1 | 30 | 30 | 0 |
| F2 | 30 | 30 | 0 |
| F3 | 30 | 30 | 0 |
| F4 | 30 | 30 | 0 |
| P1 | 30 | 30 | 0 |
| P2 | 30 | 30 | 0 |
| P3 | 30 | 30 | 0 |
| P4 | 30 | 30 | 0 |

## 5-9. Telemetry 全量机械核验(240 个成功任务, 240 个 result.json 全量解析)

| 指标 | 结果 |
|---|---|
| telemetry 总调用数 | 639 |
| triggered | 65 |
| non-triggered | 574 |
| original_payload > 18 MiB 且 triggered=1:1 | **True**(65 = 65, 双向成立) |
| normalized_payload > 18 MiB 违规 | **0** |
| 最大 original payload | 86.89 MiB |
| 最大 normalized payload | 17.99 MiB(≤ 18 MiB) |
| triggered: 宽高比保持/禁止放大 | violations = 0 |
| non-triggered: dims 不变 / payload 未被改写 | violations = 0 |

- 非触发(574): original ≤ 18 MiB → 原样发送, 行为与 baseline 完全一致;
- 触发(65): original > 18 MiB → 缩放后 ≤ 18 MiB, 宽高比保持、不放大;
- 所有发送 evidence payload ≤ 18 MiB(最大 17.99 MiB)。

## 10. hard-cap RuntimeError

- 出现次数 = **0**(真实数据全部收敛, 未触发失败路径); 按契约若触发将记为新 SYSTEM FAILURE, 保留错误不重试掩盖——本轮 0 例。

## 11. residual failure 归因

- 无 residual failure(240/240 success)。

## 12. 结论

- SYSTEM RELIABILITY 240 回归通过: 修复根因(超限 evidence 被 normalization)+ 无原成功集回归 + provider cap 逼近 provider 的防护上限维持(18MiB 内部安全线, 距 20MiB decoded / 28M 字符仍有裕量)。
- **8 invalid_test_data(F1/F2/F3/F4 × fishing_022、F2/fishing_021、F4/fishing_010、F4/fishing_025、P3/pollution_030)本轮仍执行 → 8/8 pipeline success → 仅不进入视觉评分。**
- 修复范围仍仅 payload-bounded PNG normalization; 诊断阶段候选方案(JPEG/WebP、relation、timeout/retry 等)未实施。
- 全链路不变量判定: PASS(639 calls / 65 triggered / 574 non-triggered / original>18MiB↔triggered 1:1 / normalized>18MiB violations=0 / hard-cap RuntimeError=0)。
- 未 merge master、未重新视觉评审、未继续优化——等待下一指示(接受 regression → 决定 master 合入与报告分支归档顺序)。
- telemetry 字段单位说明: normalized_payload_bytes 记录 base64 ASCII 字符数(一字符=一字节, 低于 provider 限制), 未改名。

## 文件

- 本报告: `_phase2/SYSTEM_RELIABILITY_REGRESSION_V1_REPORT.md`
- 240 状态: `_phase2/fix_v1_regression_240.json`; 汇总: `_phase2/fix_v1_regression_240_summary.json`
- 全量 result.json: `_phase2/_reg240/`(240 个, 含 qwen_protocol.evidence_payload)