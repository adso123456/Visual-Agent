# GENERAL_RGB_BEHAVIOR_UNCERTAIN_ROUTING_SYNTHESIS_V1

## Read-only mechanical simulation

状态：`READ_ONLY COMPLETE / BEHAVIOR PRODUCTION POLICY CANDIDATE SYNTHESIZED`

本阶段只复用冻结 R3 A/B/C、identity geometry metrics 和 long-range 8-call 结果。模型调用 0，Production/benchmark 代码修改 0，evidence construction 修改 0。

## Simulated policy

```text
identity_contamination_geometry == true
  → R3 target-anchored first pass

otherwise
  → current Production first pass

satisfied
  → immutable

uncertain + candidate_count == 1
  → immutable

uncertain + candidate_count >= 2
  → one full-scene disambiguation
     identity-risk candidate → target-anchored full scene
     ordinary candidate      → current Production full scene

OBJECT_MEDIATED_SCENE_INTERACTION + not_satisfied
  → confirmed target-anchored full-scene escalation
```

`candidate_count` 使用同一 localization target 的冻结 Detector candidate 集，在模型调用前确定；不得根据 case 名、first-pass evidence 文本或结果覆盖。

## Byte-locked provenance mapping

- Identity risk first pass：R3 Arm B records。
- Ordinary first pass：R3 Arm A records。
- Identity-risk multi-candidate uncertain：R3 Arm C fallback records；输入是 target-anchored isolated/local/full-scene。
- Ordinary multi-candidate uncertain：R3 Arm A fallback records；输入是 current Production isolated/local/full-scene。
- Long-range not-satisfied：已确认的 8-call records；`challenge_004` child 使用既有 R3 Arm C 的相同三图请求结果。
- Single-candidate uncertain：不调用 fallback，直接保留 first-pass uncertain。

所有复用请求均为独立 stateless chat completion；`challenge_004` child 的合成 escalation 与既有 R3 C fallback 的三张输入图片字节完全一致，不依赖前一请求的会话状态。

## Mechanical result

### Challenge safety

| Case / candidate | Result | Gate |
|---|---:|---:|
| challenge_001 bystander | `uncertain` 5/5 | false assignment 0/5 |
| challenge_001 true operator | `satisfied` 5/5 | retained 5/5 |
| challenge_003 legitimate ambiguity | `uncertain` 5/5 | preserved 5/5 |
| challenge_004 elder | `satisfied` 5/5 | retained 5/5 |
| challenge_004 child | `not_satisfied` 5/5 | false assignment 0/5 |

### F1

| Case | Synthesized task status | Frozen expected | Correct |
|---|---|---|---:|
| fishing_001 | satisfied | not_satisfied | no |
| fishing_005 | satisfied | not_satisfied | no |
| fishing_010 | not_satisfied | not_satisfied | yes |
| fishing_014 | satisfied | not_satisfied | no |
| fishing_004 | satisfied | satisfied | yes |
| fishing_018 | not_satisfied | not_satisfied | yes |

- Candidate correct：5/10。
- Task correct：3/6。
- Current Production A：5/10、3/6。
- F1 regression：0 candidate、0 task。

`F1::fishing_010.jpeg` candidate C 现在走 multi-candidate uncertain → current Production full-scene，复用既有正确 `not_satisfied`，因此消除了 global uncertain immutable 造成的唯一回归。

## Call/provenance counts

本阶段新增模型调用为 0。35 个 candidate observations 的合成来源为：

- No escalation：14。
- Confirmed long-range 8-call records：8。
- R3 target-anchored full-scene uncertain disambiguation：5。
- R3 target-anchored full-scene long-range child control：5。
- R3 current Production full-scene uncertain disambiguation：3。

## Decision

`SINGLE_CANDIDATE_UNCERTAINTY = IMMUTABLE` 在当前冻结集上保住 challenge_003。

`MULTI_CANDIDATE_UNCERTAINTY = ONE FULL_SCENE DISAMBIGUATION` 在当前冻结集上恢复 fishing_010 C，并且 challenge_001、fishing_014 未产生新 false assignment。

`BEHAVIOR_PRODUCTION_POLICY_CANDIDATE = SYNTHESIZED WITH NO KNOWN FROZEN-SET REGRESSION`

但仍不得写成 `PRODUCTION POLICY CONFIRMED`，原因是：

1. 70% identity geometry threshold 来自同一冻结集，尚无独立 confirmation。
2. uncertain routing 的关键有效样本数量很小：single safety source 为 challenge_003；multi resolution source 为 fishing_010 C，另有 challenge_001/fishing_014 safety controls。
3. 当前只是既有结果的机械组合，没有执行最终整体策略代码路径。

- `PRODUCTION MODIFICATION = NOT AUTHORIZED`
- `PRODUCTION MERGE = NOT AUTHORIZED`
- `GENERAL_RGB_FINAL_ACCEPTANCE_V2 = NOT AUTHORIZED`
- `RELATION SMALL HELD-OBJECT BLOCKER = PENDING`
- `REMOTE SENSING WATER QUALITY = BLOCKED`
