# Visual Agent Perception Contract v1.0

> 同时定义：Visual Agent Detector Evaluation Contract v1.0 与 Instance Quality Benchmark v1.0。

## 1. 文档状态

| 项目 | 内容 |
|---|---|
| 状态 | 正式冻结（Frozen） |
| 版本 | 1.0 |
| 适用范围 | Visual Agent 的 Agent、Detector、VLM、Relation、SAM、Action 与评测体系 |
| 目标 | 为所有本地开放词汇 Detector 提供统一、长期、可维护的评测与生产准入标准 |

本契约不是某个 Phase 或某张测试图片的临时 Gate。以后评估、替换或升级任何 Detector，都必须遵守本契约，不得围绕单个 case 临时修改职责边界或准入标准。

本契约后续只能通过明确的版本化修改维护：

- 文字澄清或兼容性补充：发布 `v1.x`；
- 改变职责边界、核心指标、Hard Gate 或 Benchmark 结构：发布新的主版本；
- Benchmark 图片只能增补并形成 `v1.1`、`v1.2` 等版本，不得为迁就候选模型随意删除失败样本；
- 所有版本变更必须记录原因、影响范围和迁移方式。

## 2. 最终原则

> 上游负责产生可靠的独立视觉实例；VLM 负责理解这些实例；SAM 负责精确描绘这些实例；Agent 负责把用户意图编译成这些能力的组合，而不是让后一个模型修补前一个模型本应解决的问题。

以下边界永久冻结：

```text
Detector 错误
≠ VLM 去重修复
≠ SAM overlap 修复
≠ Python 几何硬修复
```

Detector 必须自己承担实例候选质量。

## 3. 七层职责防线

Visual Agent 的长期职责链固定为：

```text
用户自然语言
  ↓
[防线 1] Agent / Concept Compiler
  ↓
[防线 2] Open-Vocabulary Detector
  ↓
[防线 3] VLM Semantic Verification
  ↓
[防线 4] Relation Verification
  ↓
[防线 5] SAM
  ↓
[防线 6] Deterministic Action Layer
  ↓
[防线 7] User Feedback / Visual Concept Memory
```

### 3.1 Agent / Concept Compiler

只负责把用户表达编译为：

- `target_object`：基础实体；
- `attributes` / `constraints`：属性、行为、状态；
- `relations` / `related_objects`：实体关系；
- `action`：确定性图片操作；
- `visual_reference`：可选的未来视觉参考。

示例：

```json
{
  "target_object": "person",
  "constraints": ["戴黄色安全帽"],
  "related_objects": [
    {
      "object": "tool",
      "relation": "held_by_target"
    }
  ],
  "action": {
    "type": "highlight"
  }
}
```

Detector prompt 只能是 `person` 和 `tool`，不得变成 `yellow helmet worker holding tool`。

### 3.2 Open-Vocabulary Detector

给定基础实体概念，生成能够代表真实、独立物体实例的候选集合。Detector 只负责定位，不负责属性、行为、关系、最终目标或图片操作。

### 3.3 VLM Semantic Verification

只负责判断候选实例的：

- 属性；
- 行为；
- 状态；
- 语义证据归属；
- `satisfied` / `not_satisfied` / `uncertain`。

VLM 不负责实例去重、同实例聚类或 bbox 修复。

### 3.4 Relation Verification

只负责独立实例之间的关系判断，例如 `held_by_target`。关系语义不得下沉到 Detector，也不得由 SAM 推断。

### 3.5 SAM

只接受已经通过 Detector 和 Semantic Verification 的最终目标 bbox，负责：

- mask quality；
- boundary quality；
- object coverage。

SAM 不负责实例身份、Detector duplicate cleanup 或语义判断。

### 3.6 Deterministic Action Layer

只负责描边、高亮、模糊、背景变暗、抠图等确定性执行，不参与感知或语义推断。

### 3.7 User Feedback / Visual Concept Memory

未来可负责参考实例、纠错样本和行业概念适配，但不进入 Detector Benchmark v1。Benchmark v1 必须是 cold-start、zero-shot、无历史纠正。

## 4. Detector 输入契约

Detector 永远只接收：

```text
image + canonical target_object
```

允许示例：

- `person`
- `umbrella`
- `car`
- `dog`
- `excavator`
- `gate`
- `boat`

禁止示例：

- 穿红衣的人；
- 戴安全帽的人；
- 正在钓鱼的人；
- 拿雨伞的人；
- 站在汽车旁的人。

这些信息分别属于 attribute、state/action 或 relation，必须交给下游。

例如“只给穿红衣的人描边”：

```text
Agent:
  target_object = person
  constraints = [穿红色衣服]
  action = outline

Detector:
  person

VLM:
  穿红色衣服？
```

不得因为 Detector 能力不足而破坏这一职责边界。

## 5. Detector 输出契约

所有 Detector 进入 Visual Agent 前必须归一化为：

```json
{
  "id": "A",
  "bbox": [10.0, 20.0, 100.0, 200.0],
  "confidence": 0.91,
  "text_label": "person"
}
```

要求：

- `bbox` 使用原图像素坐标 `[x1, y1, x2, y2]`；
- bbox 必须 clip 到图片边界；
- `x2 > x1` 且 `y2 > y1`；
- 坐标和 confidence 必须为有限数值；
- ID 必须按稳定顺序生成；
- label 只表达基础实体类别或等价文本。

Detector 不得直接提供：

- semantic status；
- action；
- relationship；
- final target。

## 6. Detector 七项核心指标

传统 AP/mAP 可以作为参考，但不是 Visual Agent 选型的主要指标。正式核心指标为：

| 指标 | 核心问题 | 方向 |
|---|---|---|
| Instance Recall | 每个真实实例是否至少有一个可用候选 | 越高越好 |
| Instance Purity | bbox 是否主要只覆盖一个真实实例 | 越高越好 |
| Instance Completeness | bbox 是否保留足够完整、可识别的实例信息 | 越高越好 |
| Duplicate Rate | 同一个真实实例是否产生多个候选 | 越低越好 |
| Mixed-box Rate | 一个 bbox 是否同时覆盖多个同类实例 | 越低越好 |
| Small/Occluded Recall | 小、远、遮挡目标能否被独立发现 | 越高越好 |
| Downstream Usability | 候选是否足以让冻结 VLM 可靠判断语义 | 越高越好 |

同时必须报告：

- false detection rate；
- latency；
- model load time；
- VRAM peak；
- model size；
- batch support；
- CUDA requirement；
- dependency complexity；
- license。

不得用一个总分掩盖结构性风险。

## 7. Ground Truth 契约

Visual Agent Benchmark 的 Ground Truth 不仅包含 bbox 和 class，还必须包含：

```text
instance_id

visibility:
  full
  partial
  heavily_occluded

scale:
  large
  medium
  small

crowding:
  isolated
  adjacent
  dense

semantic_visibility:
  sufficient
  insufficient
```

这些字段只用于 benchmark，不得进入 production runtime。评测目标是判断候选能否成为 Agent 的独立视觉对象，而不只是 GT IoU 是否超过某个阈值。

## 8. Candidate 人工分类契约

每个 Detector candidate 必须归为以下六类之一：

### 8.1 `VALID_INSTANCE`

主要对应一个真实实例，视觉信息足够完整，可以作为后续 VLM 候选。

### 8.2 `PARTIAL_INSTANCE`

明确属于一个真实实例，但只覆盖局部并明显损害语义判断能力，例如只有腿、半个身体或局部服装区域。

### 8.3 `DUPLICATE_INSTANCE`

同一 GT instance 已存在更合适候选，当前候选属于重复检测。

### 8.4 `MIXED_INSTANCE`

一个候选明显同时覆盖两个或以上同类真实实例，不能作为独立实例。

### 8.5 `FALSE_DETECTION`

候选没有对应真实 `target_object`。

### 8.6 `AMBIGUOUS`

人工也无法可靠判断。它不计为明确 FP，但必须单独统计，防止 Detector 通过制造大量模糊框“刷 recall”。

## 9. Instance Completeness 契约

Completeness 不得被纯 bbox IoU 替代，人工评价分为：

- `COMPLETE`：目标视觉主体完整；
- `USABLE_PARTIAL`：虽不完整，但保留了足够的目标视觉证据；
- `UNUSABLE_PARTIAL`：缺失严重，无法可靠支撑语义判断。

核心问题是：候选是否保留足够证据，让 VLM 判断用户约束。

例如对“是否穿红衣”：包含头部、上身和大部分衣物，即使没有腿，也可能是 `USABLE_PARTIAL`；只包含一只脚则是 `UNUSABLE_PARTIAL`。

## 10. 指标计算契约

### 10.1 Instance Recall

按 GT instance 计算，不按 candidate 数量计算：

```text
Instance Recall
= 至少有一个 VALID_INSTANCE candidate 的 GT instances
  / 全部可评价 GT instances
```

真实有 7 人、Detector 输出 20 个框，但只有 5 人拥有独立有效候选，则 Instance Recall 为 `5/7`，不是 `20/7`。

### 10.2 Duplicate Rate

正式记录两个值：

```text
Duplicate Candidate Rate
= DUPLICATE_INSTANCE candidates / all non-ambiguous candidates

Duplicate Multiplicity
= recalled instances 对应的 candidate 数量均值
```

理想状态为一个真实实例约等于一个候选。

### 10.3 Mixed-box Rate

```text
Mixed-box Rate
= MIXED_INSTANCE candidates / all non-ambiguous candidates
```

Mixed box 会破坏 VLM 语义证据归属，因此是一级风险，不只是 bbox 不够准确。

### 10.4 Instance Purity

```text
Instance Purity
= VALID_INSTANCE candidates / all non-ambiguous candidates
```

报告中必须同时列出 partial、duplicate、mixed 和 false detection，不能只给 purity。

### 10.5 Downstream Usability

Detector-only 评价完成后，使用冻结 VLM 进行第二层测试：

- 候选框过小、只含无用局部或混入邻人，导致 VLM 失败：`DETECTOR_DOWNSTREAM_UNUSABLE`；
- 候选人工确认清晰、独立且证据充分，但 VLM 判断错误：`VLM_SEMANTIC_LIMIT`。

该边界必须在所有评测报告中明确区分。

## 11. Instance Quality Benchmark v1.0

Benchmark v1 固定覆盖八类场景：

1. `Sparse / Easy`：稀疏、完整、大目标；
2. `Adjacent Instances`：两个或多个同类目标相邻；
3. `Dense Instances`：密集同类目标；
4. `Small / Distant`：远距离、小目标；
5. `Occlusion`：部分遮挡、严重遮挡；
6. `Scale Variation`：前景大目标与背景小目标并存；
7. `Cross-object Interference`：人与车、伞、设备等相互遮挡；
8. `Domain / Long-tail Objects`：水利设施、工业设备和专业对象。

### 11.1 最小规模

- 每类至少 3 张，共至少 24 张；
- 推荐每类 5 张，共约 40 张；
- v1 达到 24 张即可建立 Base baseline并开始后续 Detector A/B。

### 11.2 图片组成

Benchmark 不得全部来自同一数据集、同一类别、同一分辨率或简单网络图。至少覆盖：

- person；
- common objects；
- relation objects；
- domain objects。

第一版建议约 50% person、25% common objects、25% domain/relation objects，不要求机械精确。

### 11.3 challenge_005 的角色

`challenge_005` 固定为 `Dense Crowd Stress Case`，用于评估极端密集、小目标、多尺度人物表现，但不得单独决定整个 Detector 架构。

若它暴露大量 mixed boxes、严重重复或背景小目标完全漏检，则作为结构性风险进入 Hard Gate 和分类报告。

## 12. Calibration 与 Test 隔离

必须建立独立 Calibration Set：

- 至少 5～10 张；
- 不进入正式排行榜；
- 只用于冻结 confidence threshold、NMS threshold、输入 resolution和模型官方建议参数。

每个 Detector 首先使用官方推荐或 default inference setting。需要校准时，只能在 Calibration Set上进行一次参数冻结；不得查看 Benchmark Test结果后继续调参。

## 13. Detector A/B 单变量契约

评估任何新 Detector时：

```text
A = 当前正式 Detector
B = 候选 Detector
```

必须冻结：

- 相同图片；
- 相同 canonical `target_object`；
- 相同人工 GT；
- 相同 VLM；
- 相同 SAM；
- 相同 Action。

禁止同时更换 Detector、VLM、prompt、Tile或其它关键变量。

Detector benchmark禁止：

- Tile；
- SAHI；
- SAM dedup；
- Qwen duplicate verification；
- geometry instance merging；
- 人工 drop candidates；
- case-specific postprocessing。

只允许 Detector自身官方标准的预处理、confidence filtering和NMS。否则评估的是“Detector + 修补系统”，不是 Detector。

## 14. Detector Hard Safety Gates

不论任何辅助总分多高，以下问题都禁止进入生产：

### Gate 1 — Catastrophic Mixed

普通非极端场景频繁出现一个 candidate包含多个明确实例：FAIL。

### Gate 2 — Catastrophic Duplication

普通场景中一个真实实例频繁产生2～4个重复 candidates：FAIL。

### Gate 3 — Basic Recall Regression

简单/正常目标的 Instance Recall明显低于当前正式 Base：FAIL。

### Gate 4 — False Detection Explosion

通过大量低质量候选换取 recall：FAIL。

### Gate 5 — Downstream Breakage

候选数量增加，但冻结 VLM usability或relation usability明显下降：FAIL。

## 15. 辅助 Instance Quality Score

允许定义 IQS（Instance Quality Score）用于候选排序：

- Recall、Purity、Completeness、Small/Occluded Recall和Downstream Usability加分；
- Duplicate、Mixed-box和False Detection扣分。

IQS只能用于排序，不能覆盖 Hard Gate。即使 IQS很高，只要 Mixed-box Hard Gate失败，仍不得进入 Production。

## 16. 本地部署 Hard Constraint

候选 Detector必须：

- 模型权重可下载到本机；
- 推理完全在本地；
- 图片无需上传云端；
- 不依赖在线 API；
- 不需要第三方 Token；
- 无强制 telemetry；
- 支持离线运行。

DDS / `GroundingDino-1.6-Pro` 不再作为候选，结论为：

```text
DEPLOYMENT_CONSTRAINT_MISMATCH
```

这不是模型技术能力失败，而是部署方式不符合 Visual Agent长期约束。

## 17. Visual Reference 与反馈扩展

未来允许：

```text
target_object + visual_reference
```

但它属于 Few-shot / Visual Concept Mode，不得混入当前 Text-only Detector Benchmark。未来评测必须拆分为：

- Zero-shot Text Benchmark；
- Few-shot Visual Prompt Benchmark。

用户删除误检、补框漏检、确认 uncertain等行为属于 Adaptive / Active Learning Layer，也不进入 Detector Benchmark v1。

## 18. Detector Production Admission Gate v1

新 Detector替换正式 Grounding DINO Base前，至少必须满足：

1. Sparse/Easy Instance Recall不低于 Base；
2. Aggregate Instance Recall明显优于 Base；
3. Small-object Recall明显优于 Base；
4. Occluded Recall不低于 Base；
5. Instance Purity不低于 Base；
6. Duplicate Rate不高于 Base；
7. Mixed-box Rate不高于 Base；
8. Downstream Usability不低于 Base；
9. Core `15/15`不回归；
10. Relation cases不回归；
11. Negative cases不回归；
12. 完全本地运行。

v1.0 暂不写死统一绝对百分比。必须先建立24～40张正式 Benchmark并获得 Grounding DINO Base分布，再在后续版本中冻结合理绝对阈值，避免依据单张图片猜测 Gate。

## 19. 标准评测报告

每次 Detector A/B必须同时报告：

- 每类场景和聚合 Instance Recall；
- Instance Purity；
- Completeness分布；
- Duplicate Candidate Rate；
- Duplicate Multiplicity；
- Mixed-box Rate；
- False Detection Rate；
- Small-object Recall；
- Occluded Recall；
- Downstream Usability；
- VLM / Relation回归；
- model size；
- VRAM peak；
- model load time；
- single-image latency；
- batch support；
- CUDA requirement；
- dependency complexity；
- license；
- 每个 Hard Gate 的 PASS/FAIL与证据；
- 辅助 IQS（如使用）。

禁止只给单一总分后直接宣布胜者。

## 20. 历史决策依据

### Phase 1～8

现有 Visual Agent主链完成并通过验收。

### Phase 9

Dense Recall与下游去重探索失败。bbox geometry、Qwen全局实例解析和Qwen局部pairwise identity均不能安全修复Detector错误。

结论：Detector错误不能依赖VLM或几何规则做下游实例修复。

### Phase 10

SAM mask consolidation失败。同一真实实例的不同bbox prompt可能产生不同像素区域，无法稳定完成实例身份归一化。

结论：SAM不承担Detector duplicate cleanup或instance identity。

### Phase 11 DDS

云端Detector路线与本地部署Hard Constraint不一致。

结论：`DEPLOYMENT_CONSTRAINT_MISMATCH`，终止DDS / GroundingDino-1.6-Pro云API候选路线。

## 21. 下一正式工作

下一正式工作不是立即选择新模型，而是建立统一的尺子：

```text
Detector Evaluation Infrastructure
+
Instance Quality Benchmark v1（至少24张图）
↓
Grounding DINO Base正式Baseline v1
↓
Local Detector Candidate A
↓
Local Detector Candidate B
↓
统一A/B
↓
选择适合作为Visual Agent perception front-end的本地模型
```

第一轮只运行 Grounding DINO Base，得到它在 Sparse、Adjacent、Dense、Small、Occlusion、Scale、Cross-object和Domain八类场景的正式Baseline。建立Baseline后，才允许启动本地候选Detector A/B。
