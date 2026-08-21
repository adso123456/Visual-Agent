# REAL_WORLD_BATCH_ACCEPTANCE_V1 — 阶段总览 (正式归档)

状态机:

| 阶段 | 名称 | 状态 |
|---|---|---|
| PHASE 0 | REAL_WORLD_TESTSET_COLLECTION_V1 | COMPLETE |
| PHASE 1 | ACCEPTANCE CONTRACT FREEZE | CLOSED (FROZEN, v3) |
| PHASE 2 | END_TO_END_EXECUTION | CLOSED / BASELINE CAPTURED |
| PHASE 3 | VISUAL ADJUDICATION | ACCEPTED / CLOSED |
| NEXT | SYSTEM_RELIABILITY_FIX_V1 | 未开始 |

## 总口径

240 submitted
├─ 204 pipeline success
│  ├─ 196 valid scored
│  └─   8 invalid_test_data (F1/F2/F3/F4 × fishing_022 数据不一致 + F2/fishing_021、F4/fishing_010、F4/fishing_025、P3/pollution_030 合同语义/标签问题)
└─  36 SYSTEM FAILURE (冻结 baseline, 未重跑)

## 视觉最终统计 (valid scored = 196)

- Positive valid = 91: PASS 52 (57.1%), DEGRADED 8 (8.8%), FAIL 31 (34.1%); PASS+DEGRADED = 60/91 = 65.9%
- Negative valid = 105: TN 95 (90.5%), FP 10 (9.5%)
- VISION_FAILURE = 41 (31 FAIL + 10 FP); OOS = 0

## 结论

1. 当前系统未达'真实场景验收通过'状态: 视觉层正样本仍有 31/91 明确 FAIL, 污染方向明显弱于钓鱼方向 (P1/P3/P4 正样本 FAIL 占比高)。
2. 下一优先级 blocker = SYSTEM RELIABILITY: 冻结 baseline 36/240 = 15% 系统失败率 (provider 载荷上限 ~载荷24 + 连接错误12), 先解决系统层再优化视觉, 否则视觉数据被执行失败严重干扰。

## 数据完整性问题 (已发现并排除, 不重跑/不改合同/不改代码)

- fishing_022 磁盘文件为黑白撒网图 (31803434), 与合同元数据 15521411 不符 → 4 case 排除。
- F2/fishing_021 (正样本无持竿)、F4/fishing_010、F4/fishing_025 (负样本实际持鱼)、P3/pollution_030 (船属漂浮物, prompt 语义歧义) → 4 case 排除。

## 本目录文件

- ACCEPTANCE_CONTRACT_V1.md / acceptance_contract_v1.json : Phase1 冻结合同
- PHASE2_EXECUTION_REPORT.md : 执行与 SYSTEM FAILURE 报告
- PHASE3_VISUAL_ADJUDICATION_REPORT.md : 视觉评审报告 (v3 终版)
- PHASES_OVERVIEW.md : 本文件

详细台账与原始审计中间件 (adjudication.json、ledger.json、_work_*.json、cards、outputs 等) 按归档约定不入库, 保留在 E:\3\_visual_agent_real_world_acceptance\v1\_phase2\ 供追溯。