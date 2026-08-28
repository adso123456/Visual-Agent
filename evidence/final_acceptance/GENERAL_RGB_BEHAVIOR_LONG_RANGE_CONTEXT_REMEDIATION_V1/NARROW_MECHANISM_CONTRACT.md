# GENERAL_RGB_BEHAVIOR_LONG_RANGE_CONTEXT_REMEDIATION_V1

## Narrow mechanism contract

状态：`NARROW MECHANISM CONTRACT APPROVED / FROZEN`

本合同只确认 `not_satisfied + long-range interaction` 的一次 full-scene escalation 是否具有独立价值，不确认任何完整 Production policy。

## Frozen source

- Evidence branch source commit：`8e3bd28a86342b35bcab5d8600be4aa858712599`
- R3 builder implementation：`0b32695dcd46d13cf22987f5347b2b212e7132c1`
- R3 reviewed harness head：`22b22570c5f9ac6bd5249dae8f70782f500fb810`
- R3 `results.jsonl` SHA-256：`70ffbd79bd562dfe00cff10191c60a89e58021f7fd067b4fdce33ec3dd00715e`
- R3 preflight receipt SHA-256：`4eb00894b6fb566c7fb22b612fb762391e03badac670fd1bbf9958d6d36bdad7`
- R3 selection SHA-256：`37fb7fcb97e5a324a4d76d81abe805e947e220420c97102eb6d690cc64c44563`
- R3 execution artifact manifest SHA-256：`1726e0bff1613a1cf132c6842e0b7ccced0b12a35010a938246180184c2a7905`

任一 source、record 或 evidence SHA 不一致时，preflight 必须在 0 次模型调用下失败。

## Base control

`BASE CONTROL = FROZEN R3 ARM B TARGET-ANCHORED FIRST PASS`

- `satisfied`：immutable。
- `uncertain`：immutable。
- `not_satisfied`：只有任务在读取 first-pass 结果前已被冻结为 `OBJECT_MEDIATED_SCENE_INTERACTION` 时，允许一次 escalation。
- 不重新执行历史 first pass，不重新解释历史状态。

## Long-range class

唯一 V1 enum：`OBJECT_MEDIATED_SCENE_INTERACTION`。

定义：行为是否成立可能依赖目标实例与 35% candidate-local crop 之外的交互物体或环境端点之间的视觉连续性。

分类必须由冻结任务语义在读取 first-pass 结果前确定，不得按 case、candidate 或运行结果覆盖。当前 selection 中所有任务的 semantic constraint 均为“正在钓鱼”，统一标记为该类别。

## Escalation evidence and verifier

每个新 slot 只调用一次现有 Production `verify_candidate_constraints()` behavior contract；不复制、不修改 prompt、validator、retry 或 evidence normalization。

输入顺序固定为：

1. R3 Arm C `isolated`（字节与 Arm B isolated 相同）；
2. R3 Arm C `target-anchored local`（字节与 Arm B local 相同）；
3. R3 Arm C `target-anchored full_scene`。

本合同中的一次 escalation 是一次 logical verifier call；协议内部 attempts/retry 继续按 Production telemetry 原样记录。失败 terminal 保留，不补跑、不替换。

## Frozen execution denominator

- `challenge_004` elder：5 calls。
- `F1::fishing_010.jpeg` candidate A/B：2 calls。
- `F1::fishing_018.jpeg` candidate A：1 call。
- `TOTAL NEW LOGICAL MODEL CALLS = 8`。
- Concurrency = 1。

确切顺序、source record SHA 与三图 evidence SHA 见 `frozen_long_range_slots.json`；执行时不得调整。

## Inherited immutable safety controls

以下记录由完整 source `results.jsonl` SHA 与 slot IDs 锁定，不新增调用：

- `challenge_001` R3 Arm B bystander：`uncertain` 5/5。
- `challenge_001` R3 Arm B true operator：`satisfied` 5/5。
- `challenge_003` R3 Arm B legitimate ambiguity：`uncertain` 5/5。
- `challenge_004` R3 Arm B child：`uncertain` 5/5。

## Confirmation Gate

只有全部满足才确认机制：

1. `challenge_004` elder escalation status `satisfied >= 4/5`。
2. 三个 F1 negative escalation observations 全部为 `not_satisfied`。
3. `new_false_assignment = 0`。
4. 上述 inherited controls 的 source slots、status 与 source file SHA 全部一致。
5. Provider/protocol/validator/evidence final failure = 0。
6. Terminal records = 8；logical verifier calls = 8；failed execution replacement = false。
7. 实际模型、endpoint、timeout 必须分别为 `qwen3.8:27b-mtp-q4_K_M`、`http://192.168.250.9:11434/v1`、120 秒。

通过时唯一允许的裁决名称：

`LONG_RANGE_NOT_SATISFIED_ESCALATION_MECHANISM = CONFIRMED`

禁止写成 `PRODUCTION POLICY = CONFIRMED`。R3 Arm B 已知 F1 总体回归仍然有效，任何 Production 集成必须另行授权。

## Prohibitions

- 不修改 Production、benchmark builder、harness、prompt、validator、evidence、模型或参数。
- 不重跑 first pass。
- 不补跑失败 slot。
- 不新增 case、candidate 或 repetition。
- 不按运行结果改变 long-range class。
- 不 merge Production。

`REMOTE_SENSING_WATER_QUALITY = BLOCKED`
