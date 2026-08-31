# Joint Targeted Confirmation — Adjudication Clarification

状态：`ADJUDICATION CLARIFIED / NO MODEL CALLS`

本文件只修正联合确认 runner 的判分语义，不修改冻结合同、selection、模型输出、terminal records 或原始 `summary.json`。`469914a...` 继续作为不可变的首次执行记录。

## 冻结 Behavior baseline

判分基线来自执行前已存在的 `GENERAL_RGB_BEHAVIOR_UNCERTAIN_ROUTING_SYNTHESIS_V1/mechanical_simulation.json`，其 F1 aggregate 为：

- candidate correct：`5/10`
- task correct：`3/6`
- Production A candidate/task regression：`0 / 0`

候选级冻结状态用于识别“新增”错误：

```text
challenge_001 A=uncertain, B=satisfied
challenge_003 A=uncertain
challenge_004 A=satisfied, B=not_satisfied
F1::fishing_001 A=satisfied
F1::fishing_005 A=satisfied
F1::fishing_010 A=not_satisfied, B=not_satisfied, C=not_satisfied
F1::fishing_014 A=satisfied, B=uncertain, C=uncertain
F1::fishing_004 A=satisfied
F1::fishing_018 A=not_satisfied
```

## 机械定义

`new_false_assignment`：当前策略产生错误的 `satisfied`，且同一 case/candidate 的上述冻结 baseline 不是 `satisfied`。已有 baseline false positive 重新出现不计为 new。

`fallback_harm`：该 slot 实际执行 fallback，并且冻结 baseline 对该 candidate 是合法/正确状态，而当前 final 状态不再合法/正确。仅仅“fallback 后仍保持既有错误或不确定状态”不构成 harm。

`F1_candidate_regression`：`max(0, 5 - current_F1_candidate_correct)`。

`F1_task_regression`：`max(0, 3 - current_F1_task_correct)`。

Relation existing-positive 必须分开判定：

- `F2::fishing_024` 必须存在唯一成功 observation 且 final positive retained；
- `core_003` 必须存在唯一成功 observation 且 final positive retained。

任何 observation 缺失或 terminal failure 都不能因对空集合执行 `all()` 而得到 true。

## 对首次批次的影响

首次批次 Behavior 35/35 raw execution 有效；但原 summary 对 `new_false_assignment`、`fallback_harm` 和 F1 regression 的实现与上述冻结语义不一致。因此：

```text
BEHAVIOR RAW EXECUTION = 35/35 VALID
BEHAVIOR POLICY ADJUDICATION = INVALID / PENDING CORRECTED RUNNER
RELATION ACTIVATION POLICY = INCONCLUSIVE_EXECUTION_FAILURE
JOINT POLICY CANDIDATE = NOT CONFIRMED
```

本澄清不追溯把首次 joint batch 改判为 PASS，也不授权模型执行、Production 修改或 merge。
