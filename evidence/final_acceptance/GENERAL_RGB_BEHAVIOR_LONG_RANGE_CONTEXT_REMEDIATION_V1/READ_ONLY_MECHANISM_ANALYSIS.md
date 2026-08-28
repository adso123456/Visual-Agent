# GENERAL_RGB_BEHAVIOR_LONG_RANGE_CONTEXT_REMEDIATION_V1

## Read-only mechanism analysis

状态：`READ_ONLY_MECHANISM_ANALYSIS_COMPLETE`

本阶段只读取 `challenge_004` 已冻结的 R3 A/B/C 原始执行记录与 evidence；模型调用 0，Production 代码修改 0，参数调整 0，补跑 0。

## Denominator clarification

- 老人候选 A：3 arms × 5 repetitions = 15 个 terminal records，是本次主要归因对象。
- 儿童候选 B：另有 15 个 terminal records，用作同图归属与 full-scene 可见性证据。
- 因此 `challenge_004` 在原始 `results.jsonl` 中共有 30 个 candidate terminal records，不应把“15 次老人执行”误写成整张图只有 15 个 candidate calls。

## Mechanical execution facts

### Elder candidate A

| Arm | First pass | Fallback calls | Final |
|---|---:|---:|---:|
| A | `not_satisfied` 5/5 | 0/5 | `not_satisfied` 5/5 |
| B | `not_satisfied` 5/5 | 0/5 | `not_satisfied` 5/5 |
| C | `not_satisfied` 5/5 | 0/5 | `not_satisfied` 5/5 |

三臂的老人 first pass 都稳定认为：人物双手在身前，局部画面没有足够的钓竿、水面或钓鱼场景证据。因为 fallback 合同只接受 first-pass `uncertain`，这 15 条 `not_satisfied` 全部被视为不可变结果，老人从未获得 full-scene verifier 调用。

### Child candidate B

- Arm A：first/final `not_satisfied` 5/5。
- Arm B：first/final `uncertain` 5/5；B 无 fallback。
- Arm C：first `uncertain` 5/5，因此触发 full-scene fallback 5/5；final `not_satisfied` 5/5，全部为 `non_harm`。
- C fallback 的 VLM evidence 5/5 稳定指出：儿童没有接触钓竿，手持钓竿并钓鱼的是旁边成年男性。

这证明同一模型在同一图的 full-scene evidence 中能够看见水域、长鱼竿和成年男性，并能把钓鱼行为从儿童排除、归给成年人。文本把成年人外套写成灰色而实际更接近蓝色，但不影响人物身份与行为归属结论。

## Evidence visibility

- `isolated.png`：只保留老人实例，鱼竿、水域与长程行为上下文全部被移除。
- A `local.png`：126×378；能看到老人和儿童，但仅保留手部附近极短杆段，没有水域，也没有鱼竿延伸到水面的完整几何关系。
- B/C `local.png`：同为 126×378；仅增加非目标人物 de-emphasis，没有增加上下文范围，因此仍缺失水域与完整鱼竿。
- A/C `fallback_full_scene.png`：598×406；老人、儿童、水域以及从老人手部延伸到水面的长鱼竿均清晰可见，但老人候选从未进入这一视图的模型调用。

关键 evidence SHA-256：

- Elder isolated：`ee83a9661f90af90821e91f51061a9d46a442d9428d16133ef3b476f7d9329cb`
- Arm A elder local：`01165bb151c0e4cdfdbeeb7db304173a4f4bcf7e5afc23d50fadbfec7cce7054`
- Arm B/C elder local：`217f611ed7eb2ce6688376d44ef2fc6e25baeb3b112818cb7bddb4a21ae07df4`
- Arm A elder full scene：`33530e89de81c98ab0510df5c27da6c91408bef9addd4f397c883ebaa56317bc`
- Arm C elder full scene：`fc5f9ac0cfc05de8dba4cb6adfc916e5fdc34915e8a8524447bd4782dc57ea6f`

## Attribution decision

`PRIMARY_FAILURE_CLASS = CONTEXT_NOT_VISIBLE_IN_FIRST_PASS`

`SECONDARY_MECHANISM = BINARY_NOT_SATISFIED_PREVENTS_FALLBACK`

`CONTEXT_VISIBLE_BUT_SEMANTIC_REASONING_FAILED = NOT_SUPPORTED_BY_CURRENT_EVIDENCE`

当前证据不支持把失败归因为“模型在 full scene 已看见老人和鱼竿但仍拒绝归属”：老人根本没有获得 full-scene 模型调用。相反，儿童的 full-scene 调用 5/5 正确看见并识别成年钓鱼者，说明 full-scene 中的关键语义是可见且可被当前模型理解的。

严格边界：由于本阶段禁止模型调用，尚未直接验证“以老人作为红色目标锚点的 full-scene 输入”是否会返回 `satisfied`。因此这是一项值得进入窄合同设计的最小 remediation hypothesis，而不是已经证明可修复的 Production 方案。

## Next decision

`GENERAL_RGB_BEHAVIOR_LONG_RANGE_CONTEXT_REMEDIATION_V1 = WORTH_NARROW_CONTRACT_DESIGN`

下一步如获授权，只应设计一个针对“candidate-local binary rejection 但行为可能依赖长程物体/场景线索”的确定性升级条件；不得重新打开 Global Facts、Detector、Relation、R2 或大型 benchmark。Production 修改与模型执行仍未授权。

`REMOTE_SENSING_WATER_QUALITY = BLOCKED`

## Source evidence

- `../GENERAL_RGB_R3_CANDIDATE_IDENTITY_REMEDIATION_V1/execution/results.jsonl`
- `../GENERAL_RGB_R3_CANDIDATE_IDENTITY_REMEDIATION_V1/execution/gate_evaluation.json`
- `../GENERAL_RGB_R3_CANDIDATE_IDENTITY_REMEDIATION_V1/execution/evidence/45cc200746762868a2a51afafa362fb212cbfbeaa350f523f7d0a353aa044a79/`
- Frozen input image SHA-256：`45cc200746762868a2a51afafa362fb212cbfbeaa350f523f7d0a353aa044a79`
