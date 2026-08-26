# GENERAL_RGB_FINAL_ACCEPTANCE_REMEDIATION_V1

## 状态

`CONTRACT FROZEN`

- Production modification：`NOT AUTHORIZED`
- Model execution：`NOT AUTHORIZED`
- Remote Sensing Water Quality：`BLOCKED`
- 基础归因：`GENERAL_RGB_FINAL_ACCEPTANCE_FAILURE_ATTRIBUTION_V1 = ACCEPTED / CLOSED`

本合同只处理已经由最终验收失败证实的三个边界。不得为了恢复历史分数把 F2/F4 强制退回 behavior；显式受支持的“手持 / 拿着 / 撑着”继续以 `relation + held_by_target` 为 canonical route。

## R1 — Planner route determinism

### 必须行为

显式 supported held-by 语义必须在进入 Pipeline 前稳定成为：

```text
constraint.route = relation
related_objects[0].relation = held_by_target
```

- Planner 返回 `behavior` 时，不得因 JSON 结构合法而直接放行。
- 必须触发 semantic contract rejection/correction；最终 validated plan 必须符合 canonical route。
- 不要求重写 Planner，不引入 Semantic IR Production integration。
- 不得使用 case ID、图片名、F2/F4、鱼竿或鱼的专用例外。
- 现有 plan JSON 外部结构保持不变。

## R2 — Relation correctness

### R2.1 Subject-level existential semantics

`held_by_target` 对 subject 是存在性语义：

```text
subject has >= 1 satisfied related binding
→ subject relation status = satisfied
```

- 同一 subject 持有多个 distinct related objects 不是 conflict。
- 同一物体的重复 related detections 产生多个 satisfied binding，也不得使 subject 失败。
- 真正需要 ownership conflict resolution 的情况仅为：同一个 related candidate 同时对多个 subjects 为 satisfied。
- 现有 focused ownership 继续只处理上述跨 subject 冲突。

### R2.2 Requested-object identity

Relation verifier 只有同时满足以下两点才允许输出 `satisfied`：

1. 蓝框对象确实是请求的 `related_object`；
2. 蓝框对象明确由指定红框 subject 持有。

对象仅靠近 subject、对象类别不符、或者归属不明确时，不得输出 `satisfied`；继续使用现有 `not_satisfied / uncertain` 三态。

### R2.3 Bounded subject-conditioned secondary grounding

执行顺序：

```text
full-scene related grounding
→ relation verification
→ 某 relation-eligible subject 没有任何 satisfied binding
→ 对该 subject 最多执行一次 secondary related-object grounding
```

限制：

- 使用相同 Grounding DINO。
- 使用相同 related-object query。
- 不替换 Detector。
- 不按 case 调 threshold。
- 不按 case 增加 alias。
- 每个 subject 最多一次 secondary pass。
- secondary view 必须由 subject bbox 与图像边界确定性生成；所有案例使用同一冻结规则。
- secondary candidates 继续经过同一 relation validator 与 resolver，不得绕过关系验证。

本阶段不预先指定某个 case 的 secondary detection 结果。

## R3 — Behavior evidence safety

### First pass

同一次 candidate verifier 必须同时接收：

1. isolated candidate identity view；
2. 现有 35% candidate-local context view。

目标是让 verifier 同时知道“当前判断的是谁”与“该候选附近发生了什么”。现有 35% view 不删除，attribute evidence policy 不改变。

### Fallback

仅当 first pass 为 `uncertain` 时，允许对该 candidate 执行一次 candidate-marked full-scene fallback：

- fallback 必须保持 candidate-specific identity marking。
- 只重判该 uncertain candidate。
- first-pass `satisfied / not_satisfied` 不得被第二次调用推翻。
- 每个 candidate 最多一次 fallback。
- 禁止 candidate-agnostic Global Facts。
- 禁止 `task_status`。
- 禁止 Global answer leakage。

这不是重新开启此前的 Global Context B/C 实验。

## 必须保持不变

- Detector 型号及主检测阈值
- SAM2 与 renderer
- VLM provider seam 与 Local VLM 配置合同
- PNG/JPEG evidence transport、18 MiB normalization、4 MP first pass
- `qwen_protocol` validate/retry 合同
- `valid / invalid / uncertain` 与 `satisfied / not_satisfied / uncertain` 三态
- relation bindings JSON contract
- Pipeline 输出结构与 telemetry
- `MAX_CONCURRENT_JOBS=1`
- F1–F4 冻结评分规则、invalid 名单和验收阈值

## Targeted Remediation Gate

所有执行必须基于同一 implementation commit、同一冻结配置、`concurrency=1`。不得中途调参；protocol/system failure 保留原始结果，不补跑替换。

### Gate 1 — Planner stability

只调用 Planner，不调用视觉模型：

- F2 prompt × 10 次独立 planning calls
- F4 prompt × 10 次独立 planning calls

必须全部满足：

```text
20/20 final validated plan
→ route = relation
→ related_objects[0].relation = held_by_target
behavior route = 0
```

### Gate 2 — Blocker stability

每条执行 5 次正式 targeted Production path：

| Case | Gate |
|---|---|
| F2::fishing_001 | 5/5 TN；false assignment = 0/5 |
| F2::fishing_024 | target retained = 5/5；`binding_conflict = 0/5` |
| F4::fishing_017 | target retained ≥ 4/5 |
| challenge_001 | false assignment = 0/5 |
| challenge_004 | elder retained ≥ 4/5；confident child false assignment = 0/5 |
| challenge_003 | legitimate ambiguity safety = 5/5；confident false assignment = 0/5 |

共 30 个 scheduled targeted executions；失败不替换。

### Gate 3 — F2/F4 full targeted regression

```text
F2 × 30
F4 × 30
= 60 system units
```

- frozen invalid：F2 2 条、F4 3 条，名单不增不减。
- visual denominator：F2 28 + F4 27 = 55。
- F2 positive usable ≥ 11/16。
- F2 TN ≥ 10/12。
- F4 positive usable ≥ 7/8。
- F4 TN ≥ 18/19。
- new invalid = 0。
- SYSTEM / provider / protocol / validator final failure = 0。

### Gate 4 — Core relation controls

- `core_003 = PASS`
- `core_004 = PASS`
- `core_014 = PASS`

## 总裁决

Gate 1–4 必须全部通过，才允许：

1. 合入 Production；
2. 单独冻结 `GENERAL_RGB_FINAL_ACCEPTANCE_V2`；
3. 重新执行完整 140-unit Final Acceptance。

任一 Gate 失败：不得 merge，不得建立 V2 执行批次，必须保留失败证据并回到对应的 R1/R2/R3 边界。

只有 V2 完整 140 最终通过，`REMOTE_SENSING_WATER_QUALITY` 才可解除阻塞。

## 禁止项

- 不换 Detector
- 不集成 Semantic IR
- 不重新研究 Global Facts
- 不引入 P1–P4
- 不修改评分标准或门槛
- 不按 case 调 prompt、threshold、alias、margin 或模型参数
- 不删除或重写 V1 最终验收失败证据
- Contract Freeze 阶段不改任何 Production 文件、不运行模型
