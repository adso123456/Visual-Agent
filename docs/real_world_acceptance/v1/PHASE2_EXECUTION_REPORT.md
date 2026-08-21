# REAL_WORLD_BATCH_ACCEPTANCE_V1 — PHASE 2: END_TO_END_EXECUTION REPORT

环境: 当前云端模型配置不变, MAX_CONCURRENT_JOBS=1, 无并发/模型改动; 60 张唯一原图(重复组成 240 个 image×instruction 执行单元)经 Production Batch API (api/server.py, run_pipeline) 执行。
说明: 本报告只记录执行结果与 SYSTEM FAILURE; 视觉结论见 PHASE3 报告, 按冻结合同分开判定。

## 1. 执行规模与总体结果

- 8 个 Batch × 30 张 = 240 image×instruction 执行单元, 全部提交完成。
- 任务级 success = 204; 任务级 failed = 36 (全部为 SYSTEM FAILURE, 系统层未完成, 不进入视觉判定)。

## 2. 每测试执行结果 (raw, subset 拆分, 仅执行层)

| test_id | prompt | 正样本成功/总数 | 负样本成功/总数 | 该测试 failed(系统层) |
|---|---|---|---|---|
| F1 | 框出正在钓鱼的人 | 19/20 | 9/10 | 2 |
| F2 | 把拿着鱼竿的人描边 | 18/18 | 10/12 | 2 |
| F3 | 框出桶 | 3/3 | 27/27 | 0 |
| F4 | 把拿着鱼的人标出来 | 8/8 | 22/22 | 0 |
| P1 | 框出水面上的垃圾 | 15/17 | 8/13 | 7 |
| P2 | 高亮漂浮的塑料瓶 | 6/6 | 22/24 | 2 |
| P3 | 描边水中的漂浮物 | 18/26 | 4/4 | 8 |
| P4 | 标出水面污染区域 | 7/20 | 8/10 | 15 |

## 3. SYSTEM FAILURE 归因（36 条, 6 个原始错误类, 聚合为 3 个原因族）

原因族 A — 输入载荷与云 provider 大小上限不匹配（24 条）:
  - data-uri 20 MiB 上限 (15 条): 大分辨率原图(如 5152x7728)与 64MB PNG 在 VLM 环节被 provider 400 拒绝 (`Exceeded limit on max bytes per data-uri item: 20971520`)。
  - string length ~28MB 上限 (9 条): 另一 provider 的字符串长度上限 (`String value length ... exceeds the maximum`), 同为超大 base64 载荷触发。

原因族 B — 云端连接层错误（12 条）: `APIConnectionError: Connection error.`, 与具体图片无稳定绑定, 属传输层瞬时失败。

原因族 C — 其他（0 条）: 无。

按合同: SYSTEM FAILURE 单独计数, 与 VISION FAILURE 分离; 以上 36 条不进入视觉正确性判定。本轮不修 Detector/SAM/阈值, 不加重试策略, 保持冻结系统原样。

## 4. 产物清单

- 240 执行台账: `_phase2/ledger.json`
- SYSTEM FAILURE 逐条归因: `_phase2/system_failure_attribution.json`
- 每测试结果: `_phase2/results/F1.json ... P4.json`
- 每测试汇总: `_phase2/per_test_summary.json`
- 产物文件清单: `_phase2/artifact_inventory.json`
- 可视化产物: `_phase2/outputs/<test_id>/<image_stem>/`

## 5. 下一步

视觉评审结论见 PHASE3_VISUAL_ADJUDICATION_REPORT.md。系统可靠性修复为独立后续阶段, 不以本报告结论反推。