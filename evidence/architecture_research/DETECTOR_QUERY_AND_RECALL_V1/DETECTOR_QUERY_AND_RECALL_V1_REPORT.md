# DETECTOR_QUERY_AND_RECALL_V1

## 状态

- 阶段：`DETECTOR_QUERY_AND_RECALL_V1`
- 执行范围：离线 benchmark；未修改 Production
- 模型：`IDEA-Research/grounding-dino-base`
- 阈值：`0.3`（Production 默认值）
- 样本：12 个冻结真实案例
- Detector 调用：28 次
- VLM / Cloud API 调用：0

## 冻结问题

本阶段把过去混在一起的失败拆成两个问题：

1. **Lexical grounding**：`localization_target` 加有限 alias，能否提高召回且不显著增加误检？
2. **Detector capability**：query 已经合理时，DINO Base 能否逐实例枚举 dense / small / overlapping objects？

canonical 始终来自 Semantic IR 的 `localization_target`。每个概念只允许预先限定的 1–2 个英文 alias，不按 case 调参。稠密场景不伪造人工精确计数，只审查候选拓扑。

## 结果摘要

### A. Lexical grounding

| 概念 | 事实 | 结论 |
|---|---|---|
| bucket → pail | 三个 bucket 正例共 4 个真实桶；canonical `bucket` 找回 1/4，加入 `pail` 后找回 4/4；alias 未新增误检 | bounded alias 对该概念有确定召回价值 |
| bottle → plastic bottle | 精确双瓶案例两种 query 都只覆盖同一个瓶；canonical 的 2 个框是同一实例的重叠框 | 更具体短语没有提高实例 recall |
| bottle 稠密/普通多实例 | `plastic bottle` 在普通多类垃圾图中候选从 10 增至 12，但没有可证的 precision 改善；在稠密瓶堆中两种 query 都只有 1 个整组大框 | 不能把更具体 query 当作通用提升 |
| 真阴性 | 无瓶场景两种 bottle query 都为 0；无桶场景 `pail` 为 0，但 `bucket` 把鱼网/鱼误框为桶 | alias 本身未破坏两个冻结真阴性；canonical 仍可能 FP |

结论：**bounded aliases 应保留为 query compiler 的受控能力，但必须按 canonical concept 版本化，不应无限扩充同义词。** 现实证据只批准 `bucket → pail` 的召回价值；不批准把 `plastic bottle` 视为对 `bottle` 的普遍增强。

### B. Detector capability

| 稠密案例 | 合理 queries | 实际候选拓扑 |
|---|---|---|
| P1 pollution_002 | garbage / trash / debris | 1 个错误区域或大区域；未枚举岸线/水中大量小垃圾 |
| P1 pollution_004 | garbage / trash / debris | 前两者 0；`debris` 仅返回 1 个垃圾带大框 |
| P2 pollution_012 | bottle / plastic bottle | 两者均返回 1 个覆盖整堆瓶的大框 |
| P3 pollution_012 | object / debris / floating object | 三者均返回 1 个覆盖整堆的大框 |

四个 dense / small / overlapping 冻结案例中，**0/4 产生 exhaustive instance localization；4/4 在合理 aliases 后仍是整组大框、错误区域或无召回。** 这已经把 lexical 问题与 detector 能力上限分开：继续追加同义词不能解决逐实例枚举。

P3 pollution_010 是边界对照：当物体尺寸较大、彼此分离时，三种 query 可返回 8–13 个分离候选，说明模型不是对所有多实例场景都失效；失败集中在稠密、小目标、重叠结构。

## 架构裁决

1. `semantic_name ≠ localization_target ≠ detector_queries` 的三层拆分获得实证支持。
2. Phase 3 可以冻结一个很薄的 query contract：canonical query + 每概念有限、版本化 alias；不把 relation/behavior 无限制塞入 DINO query。
3. Query compiler 需要候选合并/去重边界，因为 P2 pollution_009 的 `bottle=2` 实际是同一瓶的重叠框，不等于 2/2 recall。
4. DINO Base 的 dense/small/overlap 逐实例能力存在结构性缺口，满足进入 `DETECTOR_REPLACEMENT_BENCHMARK` 的证据门槛。
5. 这不授权直接替换 Production Detector，也不授权修改阈值、SAM、evidence、Pipeline 或 region backend。

## 建议 Gate

- `DETECTOR_QUERY_AND_RECALL_V1 = ACCEPTED / CLOSED`
- `BOUNDED_ALIAS_QUERY_CONTRACT = READY_FOR_DESIGN`
- `DETECTOR_REPLACEMENT_BENCHMARK = JUSTIFIED / NEXT`
- `PRODUCTION_INTEGRATION = NOT AUTHORIZED`

## 审查材料

- `raw_results.json`：28 次调用的原始 bbox、confidence、耗时、图片 SHA-256 与几何统计
- `manual_assessment.json`：逐图人工判定与聚合数字
- `overlays/`：28 张由原图原尺寸坐标渲染、仅缩放用于审查的标框图
- `run_detector_query_and_recall_v1.py`：冻结探针脚本副本

原始输入图片没有复制、修改或重新编码；`raw_results.json` 保存其绝对路径和 SHA-256，审查图不替代原始输入。
