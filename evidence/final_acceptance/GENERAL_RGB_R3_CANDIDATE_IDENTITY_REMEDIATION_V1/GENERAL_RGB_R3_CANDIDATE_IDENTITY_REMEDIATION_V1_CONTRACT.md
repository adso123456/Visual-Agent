# GENERAL_RGB_R3_CANDIDATE_IDENTITY_REMEDIATION_V1

## 状态

`CONTRACT FROZEN`

- 阶段性质：`READ-ONLY DESIGN ONLY`
- Production code modification：`NOT AUTHORIZED`
- Model execution：`NOT AUTHORIZED`
- Production merge：`NOT AUTHORIZED`
- R2.2 / R2.3：`OUT OF SCOPE`
- Remote Sensing Water Quality：`BLOCKED`
- Current remediation implementation：`general-rgb-final-acceptance-remediation-v1@be54f3c89171d8b16f53c82397e9f468fb4b4c97`（未 merge）

本阶段只回答一个问题：Behavior candidate verifier 在保留动作所需场景上下文时，能否通过 candidate-specific identity anchoring 消除相邻人物的错误归属。不得重新研究 Global Facts，不得改变 Planner、Relation、Detector、SAM、Pipeline、模型参数或评分语义。

## 1. 冻结问题与归因

- `challenge_001`：当前 R3 在 5/5 重复中把旁观者 confident 判为正在钓鱼；属于 candidate overlap + identity anchoring 不足。
- `challenge_003`：视觉证据本身不足，必须保留合法 `uncertain`，不能为了降低 uncertain 而强制二值化。
- `challenge_004`：明确钓鱼的老人应保留；儿童不得被 confident 错误归属。该 case 同时约束长程上下文与候选分离。
- F1 冻结 behavior 子集：约束修复不得以牺牲既有 General RGB behavior 能力换取 challenge 分数。

## 2. 比较对象

三条 Arm 使用完全相同的原图、prompt、candidate bbox、SAM mask、VLM、temperature、timeout、system/user prompt 与 JSON validator。差异只能存在于下述 evidence 像素构造和 uncertain fallback 策略。

### Arm A — CURRENT R3 CONTROL

First pass：

1. 现有 isolated candidate identity；
2. 现有 35% candidate-local crop，仅当前 candidate 使用红色 mask contour。

Fallback：仅 first-pass `uncertain` 时，增加现有 candidate-marked full scene；同一 candidate 最多一次。First-pass `satisfied / not_satisfied` 不可覆写。

### Arm B — TARGET-ANCHORED LOCAL

First pass：

1. 与 A 字节等价的 isolated candidate identity；
2. 同一 35% crop geometry，但执行冻结的 non-target person de-emphasis，再绘制当前 target 红色 contour。

Arm B 不执行 fallback；first-pass `uncertain` 原样保留。

### Arm C — TARGET-ANCHORED LOCAL + TARGET-ANCHORED FALLBACK

First pass 与 B 完全相同。

仅 first-pass `uncertain` 时，增加 target-anchored full scene；同一 candidate 最多一次。First-pass `satisfied / not_satisfied` 不可覆写。

## 3. Target anchoring / de-emphasis 冻结算法

### 3.1 共享输入

- target mask：当前 candidate 的冻结 SAM mask。
- non-target person masks：同图其余冻结 person candidates 的 SAM masks。
- 其他人物不能被删除、裁掉、填充为纯色或从 prompt 中声明不存在。
- 除 person masks 外，水面、鱼竿、渔网、船、岸线等场景像素保持原样。

每张图只允许从冻结 bbox 生成一次 SAM mask cache；A/B/C 与全部 repetitions 必须复用同一 mask bytes。任一 mask 缺失或 SHA-256 不一致记为 `EVIDENCE_CONSTRUCTION_FAILURE`，不得退化为 bbox mask，也不得补跑替换。

### 3.2 Local view

1. 使用当前 Production 的 35% bbox margin、floor/ceil 与 image-boundary clamp 规则；不得改变 crop 尺度。
2. 对 `union(non-target person masks) - target mask` 内每个 RGB channel 执行：

   `output = floor((45 * original + 55 * 128 + 50) / 100)`

   上式对 8-bit integer channel 精确定义 `round_half_up(0.45 * original + 0.55 * 128)`，实现不得改用不确定的默认 banker rounding。

3. target mask 内像素保持原始 RGB；target 优先级高于任何重叠 non-target mask。
4. 最后仅为 target 绘制 `(255, 0, 0)`、5 px 的 mask contour。
5. 不给 non-target 添加文字、候选 ID、bbox 或第二种彩色 contour。

该规则保留 non-target 的姿态和人际上下文，但降低其视觉显著性；不是 context deletion。

### 3.3 Full-scene fallback

Arm C 在完整原图上使用与 §3.2 相同的 de-emphasis、target-wins-overlap 与红色 5 px contour 规则，不裁剪、不预缩放。后续 PNG data-uri、18 MiB normalization 与 4 MP first pass 继续使用现有 Production contract。

## 4. 冻结评测集

详见 `frozen_selection.json`。共 9 张唯一图片、15 个冻结 candidate units：

- Safety：`challenge_001`、`challenge_003`、`challenge_004`，5 个 candidate units。
- F1 behavior subset：沿用 `CONTEXT_EVIDENCE_POLICY_HARDENING_V1/frozen_selection.json` 的 6 条，不增不减，共 10 candidate units：
  - `F1::fishing_001.jpeg`
  - `F1::fishing_005.jpeg`
  - `F1::fishing_010.jpeg`
  - `F1::fishing_014.jpeg`
  - `F1::fishing_004.jpeg`
  - `F1::fishing_018.jpeg`

候选身份与期望：

- `challenge_001`：红帽真实操作者 B=`satisfied`；右侧白帽/旁观候选 A 不得为 `satisfied`。
- `challenge_003`：A=`uncertain`；任一 confident binary 均为 safety harm。
- `challenge_004`：老人 A=`satisfied`；儿童 B 不得为 `satisfied`。
- F1：使用既有 frozen selection 的 unit-level expected 与 task-level expected，不重新解释 ground truth。

## 5. 执行单位与固定顺序

详见 `frozen_schedule.json`。

- 三个 challenge：每 Arm 每 case 5 次独立 repetitions。
- F1 六条：每 Arm 每 case 1 次。
- Scheduled arm-image slots：`3 × 3 × 5 + 6 × 3 = 63`。
- Scheduled first-pass candidate calls：`105`。
- Fallback calls：A/C 数据依赖，只有 first-pass uncertain 才发生；每 candidate 每 repetition 最多 1 次，最大 70 次。B=0。
- concurrency=`1`。
- 未来获批执行时固定：Local VLM=`qwen3.8:27b-mtp-q4_K_M`，OpenAI-compatible endpoint=`http://192.168.250.9:11434/v1`，temperature=`0`，timeout=`120s`；Planner 与 Final Response 均不调用。
- A/B/C 总体 first/second/third position 均衡；执行顺序在 schedule 中预先写死，禁止按中间结果调整。
- provider/protocol/validator/evidence failure 保留原始记录，不补跑、不替换、不从 denominator 删除。

## 6. 指标

每 Arm 必须分别报告：

- candidate status 与 task aggregation；
- challenge 每 repetition 的 true-target retention / false assignment / legitimate ambiguity；
- F1 candidate-unit correct、task correct、false assignment、uncertain；
- first-pass uncertain、fallback count、uncertain→correct、uncertain→uncertain、fallback harm；
- logical calls、HTTP attempts、retry/recovered、provider/protocol/validator/evidence final failure；
- prompt/completion/total tokens、warm latency、evidence payload bytes、normalization count。

Task aggregation 固定为：任一 candidate `satisfied` → task `satisfied`；否则任一 `uncertain` → task `uncertain`；否则 `not_satisfied`。

`new false assignment` 定义为：相同 paired observation 中，Arm A 未对 expected-non-satisfied candidate 输出 `satisfied`，但 B/C 输出 `satisfied`。既有错误与新增回归必须分开报告。

### 6.1 fallback_harm 冻结定义

Fallback 只允许从 first-pass `uncertain` 进入。根据 candidate 的冻结 expected，状态变化必须机械归类为：

| Frozen expected | Final status | Classification |
|---|---|---|
| `satisfied` | `satisfied` | `correctly_resolved` |
| `satisfied` | `uncertain` | `still_uncertain` |
| `satisfied` | `not_satisfied` | `fallback_harm` |
| `not_satisfied` | `not_satisfied` | `correctly_resolved` |
| `not_satisfied` | `uncertain` | `still_uncertain` |
| `not_satisfied` | `satisfied` | `fallback_harm` |
| `uncertain` | `uncertain` | `correctly_preserved` |
| `uncertain` | `satisfied` 或 `not_satisfied` | `fallback_harm` |

对于 `challenge_001/A`、`challenge_004/B` 这类冻结为 `allowed=[not_satisfied, uncertain]`、`forbidden=[satisfied]` 的 candidate：

- first-pass `uncertain` → final `satisfied`：`fallback_harm`；
- first-pass `uncertain` → final `uncertain` 或 `not_satisfied`：`non_harm`。

不得根据 evidence 文本、task aggregation 或最终图片对以上分类作人工改写。Arm 口径固定为：

- Arm A：报告 `fallback_harm`，仅作为 control observation，不作为 A 的 Confirmation Gate；
- Arm B：无 fallback，`fallback_harm = N/A`；
- Arm C：进入 Confirmation Gate，要求 `fallback_harm = 0`。

## 7. Confirmation Gate

某候选 Arm（B 或 C）只有同时满足全部条件才可成为下一步 implementation candidate：

1. `challenge_001`：旁观者 false assignment=`0/5`；真实操作者 retained `>=4/5`。
2. `challenge_003`：合法 ambiguity safe=`5/5`，即 A candidate 保持 `uncertain`；confident binary=`0/5`。
3. `challenge_004`：老人 retained `>=4/5`；儿童 confident false assignment=`0/5`。
4. F1 frozen subset：candidate-unit correct 不低于同批 Arm A，且不得低于历史冻结 Arm A 的 `4/10`；task correct 不低于同批 Arm A，且不得低于历史 `2/6`；`F1::fishing_004/A` 必须为 `satisfied`。
5. 所有评测：new false assignment=`0`；Arm C fallback harm=`0`。Arm A 仅报告，Arm B=`N/A`。
6. provider/protocol/validator/evidence final failure=`0`；不得通过补跑获得 5/5。
7. 输入 image/bbox/mask/evidence manifest 完整，所有声明 SHA-256 可复核。

Arm A 是 control，不因单批随机通过而自动成为新政策。B/C 必须修复 challenge_001 且不触发上述回归 Gate。

若 B、C 均通过，按以下确定性顺序裁决：

1. F1 candidate-unit correct 较高者；
2. F1 task correct 较高者；
3. uncertain 正确保持/正确解决数量较高者；
4. logical calls 较少者；
5. total tokens 较少者；
6. warm latency 较低者。

若无候选 Arm 全部通过：

`R3 CANDIDATE IDENTITY REMEDIATION = NOT CONFIRMED / NO PRODUCTION CHANGE`

## 8. 当前禁止项

- 不改任何 Production 文件、测试或 prompt。
- 不调用 Planner、VLM、DINO、SAM。
- 不启动/停止模型服务，不调整本地模型参数。
- 不碰 R1、R2.2、R2.3、Relation、Detector query、Semantic IR、Global Facts 或遥感代码。
- 不按 case 改 margin、alpha、灰色值、contour、candidate 列表或 fallback 触发条件。
- 不把 non-target person 从视觉上下文删除。
- 不 merge remediation branch，不建立 Final Acceptance V2。

本合同冻结提交经窄审查确认后，才允许另行授权实现 benchmark-only evidence builder；模型对照仍需单独授权，且两者均不等于 Production modification authorization。
