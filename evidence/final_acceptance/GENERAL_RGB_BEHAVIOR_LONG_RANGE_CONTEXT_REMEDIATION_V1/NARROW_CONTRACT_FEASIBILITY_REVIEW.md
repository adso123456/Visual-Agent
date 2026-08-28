# GENERAL_RGB_BEHAVIOR_LONG_RANGE_CONTEXT_REMEDIATION_V1

## Narrow contract feasibility review

状态：`CONTRACT DESIGN / CHANGES REQUIRED`

本文件只检查合同可满足性。模型调用 0，Production 代码修改 0，补跑 0。

## Proposed A/B as written

- A = Current Production：仅 first-pass `uncertain` 触发 candidate-marked full-scene fallback。
- B = Long-range escalation：`uncertain`，或 `not_satisfied + frozen long-range-interaction class` 触发 fallback。
- `satisfied` 不复核。

## Blocking contradiction 1: challenge_001

当前 Production evidence（R3 Arm A）中，`challenge_001` 旁观者 first-pass 是 `satisfied` 5/5，且 0 次 fallback。B 只增加 `not_satisfied` 的 long-range escalation，不会复核 `satisfied`，因此该旁观者在 B 中机械保持 `satisfied` 5/5。

所以以下两项不能同时成立：

1. B 只扩展 `not_satisfied/uncertain` fallback；
2. `challenge_001` bystander false assignment = 0/5。

这不是模型结果未知，而是策略状态机在执行前已经决定的不可满足条件。

## Blocking contradiction 2: challenge_003

冻结 R3 证据中：

- Arm A：first-pass `uncertain` 5/5；现有 full-scene fallback 返回 `satisfied` 5/5；fallback harm 5/5。
- Arm C：target-anchored first-pass `uncertain` 5/5；target-anchored full-scene fallback 同样返回 `satisfied` 5/5；fallback harm 5/5。
- 只有无 fallback 的 Arm B 保留 `uncertain` 5/5。

因此 B 若继续规定“first-pass uncertain 必须 fallback，并采用 fallback binary 结果”，与 `challenge_003 legitimate uncertainty preserved = 5/5` 的 Gate 直接冲突。

## Recommended minimal correction

为了只回答“long-range escalation 能否救回老人而不新增误归属”，建议把合同改为一个历史 control + 一个增量策略，不重复 first pass：

### A = R3 target-anchored frozen control

- 直接引用 R3 Arm B 已冻结、已验证 SHA 的 first-pass terminal records。
- Evidence：isolated identity + target-anchored 35% local。
- `satisfied`、`uncertain`、`not_satisfied` 均保持历史终态；无新增模型调用。

### B = NOT_SATISFIED LONG-RANGE ESCALATION ONLY

- 与 A 共用完全相同的冻结 first-pass terminal records。
- `satisfied`：immutable。
- `uncertain`：immutable，不执行 fallback，防止再次伤害 `challenge_003`。
- 仅当 `first-pass = not_satisfied` 且任务在调用模型前已标记为 `OBJECT_MEDIATED_SCENE_INTERACTION` 时，执行一次 target-anchored full-scene fallback。
- Fallback 不重试失败记录、不覆盖原始 first pass。

这不是把 challenge_004 写成特例。`OBJECT_MEDIATED_SCENE_INTERACTION` 的冻结定义是：行为是否成立可能依赖目标实例与 35% candidate-local crop 之外的交互物体或环境端点之间的视觉连续性。当前小样本中的“钓鱼”任务统一属于此类；分类在读取 first-pass 结果前由冻结 selection 元数据确定，同一任务语义不得按 case 改变。

## Minimal execution set

基于已冻结 R3 Arm B first-pass records，真正需要新增的 B fallback 只有 8 次：

- `challenge_004` elder：5 个 `not_satisfied` repetitions。
- `F1::fishing_010.jpeg` candidate A/B：2 个已正确为 `not_satisfied` 的 negative controls。
- `F1::fishing_018.jpeg` candidate A：1 个已正确为 `not_satisfied` 的 negative control。

以下安全 control 不新增调用，因为 B 的状态机明确使其 immutable：

- `challenge_001` bystander：R3 Arm B `uncertain` 5/5。
- `challenge_001` true operator：R3 Arm B `satisfied` 5/5。
- `challenge_003`：R3 Arm B `uncertain` 5/5。
- `challenge_004` child：R3 Arm B `uncertain` 5/5。

## Proposed Gate

只有全部满足才确认 B：

1. `challenge_004` elder fallback final `satisfied >= 4/5`。
2. 三个 F1 negative fallback observations 全部保持 `not_satisfied`；`new_false_assignment = 0`。
3. `challenge_001` bystander 继承的 `uncertain = 5/5`，true operator `satisfied = 5/5`。
4. `challenge_003` 继承的 legitimate `uncertain = 5/5`。
5. `challenge_004` child 继承的 `uncertain = 5/5`。
6. Provider/protocol/validator/evidence final failure = 0；failed execution replacement = false。
7. 所有复用记录、selection、evidence 与 source commit 的 SHA-256 必须匹配，否则 preflight 失败且模型调用为 0。

该设计只验证增量的 `not_satisfied + long-range` escalation，不再次比较 identity construction，也不重新测试已由状态机保持不变的 satisfied/uncertain candidates。

## Decision required before freeze

推荐采用上述修正版。若坚持原始 A/B 状态机，则合同应在不调用模型的情况下直接判定 `NOT_FEASIBLE`，不应安排执行。

当前状态：

- `NARROW CONTRACT = NOT FROZEN`
- `CODE MODIFICATION = NOT AUTHORIZED`
- `MODEL EXECUTION = NOT AUTHORIZED`
- `PRODUCTION MERGE = NOT AUTHORIZED`
- `REMOTE_SENSING_WATER_QUALITY = BLOCKED`
