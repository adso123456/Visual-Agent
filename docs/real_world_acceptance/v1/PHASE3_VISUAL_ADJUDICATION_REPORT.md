# REAL_WORLD_BATCH_ACCEPTANCE_V1 — PHASE 3 (v3, FINAL lab): VISUAL ADJUDICATION REPORT

状态: REAL_WORLD_BATCH_ACCEPTANCE_V1_PHASE3 = FINAL_REVIEW_HOLD (等待人工复审)。
本版处理于 v2 全量修正之外残留的 4 个测试数据/合同语义无效 case; 不改 prompt、不改 positive/negative 冻结划分、不重跑任何模型与管线; 36 条 SYSTEM FAILURE baseline 未动; 4 条 fishing_022 invalid 保持不变。

## 新增 invalid_test_data（4 条，均为测试数据/合同语义完整性，非 Production 问题）

| test_id | image | 依据 |
|---|---|---|
| F2 | fishing_021 | positive 标签与实际图不符: 图中2人均未持竿(评审明确'实际无人拿竿')，不满足冻结正样本'拿着鱼竿的人'。原 DEGRADED 撤销。 |
| F4 | fishing_010 | negative 标签错误: 评审明确'一人手中明确持一鱼'，prompt 为'把拿着鱼的人标出来'，不能作为无持鱼者负样本; 系统多标属标签先行错误，不计 FP。 |
| F4 | fishing_025 | negative 标签错误: 原始评审'图中人物手持鱼'且系统高亮准确匹配指令; 合同标签错误，非模型 FP。 |
| P3 | pollution_030 | 语义冲突: 水面2条明确漂浮船只，'船'字面上即水中漂浮物; prompt'描边水中的漂浮物'未表达'污染物'隐含语义，不能以运行后隐藏语义判 FP。 |

以上 4 条: visual_verdict=INVALID_TEST_DATA, failure_type=null, evaluation_validity=invalid_test_data, 原始执行证据与 raw 判定保留。

## 最终口径（机械推导，与台账一致）

204 success cases
├─ valid scored          196
└─ invalid_test_data       8  (F1/F2/F3/F4 × fishing_022 + F2/fishing_021 + F4/fishing_010 + F4/fishing_025 + P3/pollution_030)

Positive:  PASS 52 / DEGRADED 8 / FAIL 31
Negative:  TN 95 / FP 10
VISION_FAILURE = 31 + 10 = 41
OOS = 0

## 逐测试（valid subset 内，由台账机械汇总）

| test_id | Positive | Negative | invalid | SYSTEM FAILURE(未评审) |
|---|---|---|---|---|
| F1 | 15 PASS / 0 DEG / 3 FAIL | TN 6 / FP 3 | 1 | 2 |
| F2 | 11 PASS / 4 DEG / 1 FAIL | TN 9 / FP 1 | 2 | 2 |
| F3 | 1 PASS / 0 DEG / 2 FAIL | TN 25 / FP 1 | 1 | 0 |
| F4 | 6 PASS / 1 DEG / 1 FAIL | TN 18 / FP 1 | 3 | 0 |
| P1 | 6 PASS / 1 DEG / 8 FAIL | TN 8 / FP 0 | 0 | 7 |
| P2 | 2 PASS / 2 DEG / 2 FAIL | TN 22 / FP 0 | 0 | 2 |
| P3 | 8 PASS / 0 DEG / 10 FAIL | TN 1 / FP 2 | 1 | 8 |
| P4 | 3 PASS / 0 DEG / 4 FAIL | TN 6 / FP 2 | 0 | 15 |

## 一致性核验

- failure_type=VISION_FAILURE 恰好 41 条 = FAIL(31) + FP(10)，与 visual_verdict 一一对应，无缺失/多余。
- final_reason 与 visual_verdict 无矛盾(程序化核对 0 冲突)。
- 每条含: raw_adjudicator_verdict / raw_reason / reconciliation_note / evaluation_validity / case_no。
- 8 条 invalid 不进入任何 PASS/TN/FP/FAIL / SYSTEM / VISION / OOS 统计。

## 文件

- 权威台账: `_phase2/adjudication.json` (终版, 204 条)
- 历史: `adjudication.v1.json`; 复审集合: `_review_43.json`; 原始判定: `_work_F1..P4.json`; 证据卡: `_phase2/cards/`
- 报告: 本文件 PHASE3_VISUAL_ADJUDICATION_REPORT.v3.md

## 待办

- 等待人工复审。未开启系统可靠性修复阶段; 不因评审结果回改 Detector/SAM/阈值/合同。