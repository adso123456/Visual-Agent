# REAL_WORLD_BATCH_ACCEPTANCE_V1 — 阶段总览 (正式归档)

状态机:

| 阶段 | 名称 | 状态 |
|---|---|---|
| PHASE 0 | REAL_WORLD_TESTSET_COLLECTION_V1 | COMPLETE |
| PHASE 1 | ACCEPTANCE CONTRACT FREEZE | CLOSED (FROZEN, v3) |
| PHASE 2 | END_TO_END_EXECUTION | CLOSED / BASELINE CAPTURED |
| PHASE 3 | VISUAL ADJUDICATION | ACCEPTED / CLOSED |
| — | SYSTEM_FAILURE_DIAGNOSIS_V1 | **ACCEPTED / CLOSED** |
| — | SYSTEM_RELIABILITY_FIX_V1 | **APPROVED / VALIDATED** (tested commit = 6ce8533d8a55b52e01d7daa30bce43139b5070b4) |
| — | SYSTEM_RELIABILITY_REGRESSION_V1 | **ACCEPTED / CLOSED** |
| NEXT | PRODUCTION MERGE | 未开始 (fast-forward master@5075ab5 → 6ce8533, --ff-only) |

## 系统可靠性最终口径

240 submitted → 240 pipeline success → 0 SYSTEM FAILURE

- baseline 36 failure → 36/36 recovered
- baseline 204 success → 204/204 preserved
- 8 invalid_test_data 本轮仍执行 → 8/8 pipeline success → 仅不进入视觉评分

## Telemetry(完整 240 回归)

- 639 Qwen PNG evidence calls
- 65 triggered / 574 non-triggered
- original >18 MiB ↔ triggered = 1:1 (65↔65)
- normalized >18 MiB violations = 0
- hard-cap RuntimeError = 0

## 视觉统计(定格, 见 PHASE3 报告)

- 可计分 196: Positive PASS 52 / DEGRADED 8 / FAIL 31; Negative TN 95 / FP 10; VISION_FAILURE 41; OOS 0; invalid_test_data 8。

## 文件

- ACCEPTANCE_CONTRACT_V1.* : 冻结合同
- PHASE2_EXECUTION_REPORT.md / PHASE3_VISUAL_ADJUDICATION_REPORT.md : 执行与视觉评审
- SYSTEM_FAILURE_DIAGNOSIS_V1.md / system_failure_attribution.v2.json : 根因诊断
- SYSTEM_RELIABILITY_FIX_V1_REPORT.md : 修复实施(PNG payload normalization, 候选方案未实施)
- SYSTEM_RELIABILITY_REGRESSION_V1_REPORT.md / fix_v1_telemetry_summary.json / fix_v1_regression_240_summary.json : 240 回归证据

详细台账与原始中间件(_fix36/_reg240/result 全量/cards/outputs 等)不入库, 保留在 E:\3\_visual_agent_real_world_acceptance\v1\_phase2\ 供追溯。