# REAL_WORLD_BATCH_ACCEPTANCE_V1 — PHASE 1: ACCEPTANCE CONTRACT FREEZE (v3, audited + original-image checks)

版本: REAL_WORLD_BATCH_ACCEPTANCE_V1_PHASE1_CONTRACT_v3
说明: 完成 F2/F4/P2 静态审计, 并对 F4/fishing_019 与 P2/pollution_025 两张原图做直接目检后定稿; 矩阵冻结, 不再回改。

## 1. 冻结测试指令与正负样本划分（每类别 union=30, inter=0 全覆盖）

| test_id | prompt | 类别 | 正样本 | 负样本 |
|---|---|---|---|---|
| F1 | 框出正在钓鱼的人 | fishing | 20 | 10 |
| F2 | 把拿着鱼竿的人描边 | fishing | 18 | 12 |
| F3 | 框出桶 | fishing | 3 | 27 |
| F4 | 把拿着鱼的人标出来 | fishing | 8 | 22 |
| P1 | 框出水面上的垃圾 | water_pollution | 17 | 13 |
| P2 | 高亮漂浮的塑料瓶 | water_pollution | 6 | 24 |
| P3 | 描边水中的漂浮物 | water_pollution | 26 | 4 |
| P4 | 标出水面污染区域 | water_pollution | 20 | 10 |

## 2. 审计修正记录（全部已固化）

- F2: fishing_022 原为抛网场景(无鱼竿), 换为双人冰面持竿垂钓图(15521411); 正样本 18 张逐张为持竿垂钓人物。
- F4: 原草案含 fishing_019; 经检查原图, 画面仅见人腿脚站在桶旁, 无人手拿/托/递鱼, 已移入负样本 => F4 = 8 正 + 22 负。
- P2: 原草案含 pollution_008(瓶在沙滩)与 pollution_015(无瓶)与 pollution_025; 经检查原图, pollution_025 中塑料瓶全部搁浅在沙滩上、由地面承托, 无漂浮瓶, 已移入负样本 => P2 = 6 正 + 24 负。

## 3. 结果判定标准（冻结四档）

- PASS: 目标选择基本正确、动作执行正确、无影响业务的多选/漏选。
- DEGRADED: 主体方向正确, 少量漏检/多检/边界偏差, 结果仍具业务可用性。
- FAIL: 主要目标错误/明显漏掉主要目标/错误目标占主导/任务无法完成。
- OUT_OF_SCOPE: 输入超出冻结能力边界; 必须给出明确原因, 禁止用 OOS 掩盖普通失败。

## 4. 失败分类（强制分开记录）

- SYSTEM FAILURE: API/job/artifact/runtime/Pipeline 异常(系统层异常)。
- VISION FAILURE: 系统完整运行但视觉结果错误(能力层失败)。
两类分别计数, 不得合并为单一失败率。

## 5. 计分规则（冻结, 防止总体率美化）

每条指令不得只报整体通过率, 必须分开报告:

- Positive subset（正样本）: PASS / DEGRADED / FAIL; 衡量“找得到、选得对”。
- Negative subset（负样本）: True Negative / False Positive; 衡量“会不会乱报”。

示例(F3): Positive: 3 images, PASS 2, DEGRADED 0, FAIL 1; Negative: 27 images, TN 25, FP 2。
禁止输出 “F3 = 27/30 PASS” 这类整体单数。

## 6. P4 专项（标出水面污染区域）

正样本含油膜/藻华/异常水色/成片漂浮覆盖/成片垃圾水域等区域型污染; 即使大量 FAIL 也不回改 Detector/SAM 或阈值硬补, 先如实记录。负样本为零散点状垃圾/单瓶/滩涂散落/潮线堆积/干净水面。

## 7. 冻结声明

acceptance_contract_v1.json 为一阶段唯一事实源(含逐 test 的 applicable/negative image_ids 与 reason)。经人工审阅确认后, 方可进入下一阶段 60 图端到端 Batch 验收。