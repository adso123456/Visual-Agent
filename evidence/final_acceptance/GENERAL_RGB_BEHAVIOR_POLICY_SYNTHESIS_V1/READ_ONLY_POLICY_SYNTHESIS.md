# GENERAL_RGB_BEHAVIOR_POLICY_SYNTHESIS_V1

## Read-only Production Policy Synthesis

状态：`READ_ONLY COMPLETE / PRODUCTION POLICY NOT CONFIRMED`

本阶段只读取冻结 R3 9 张图、15 个 candidates 的 bbox、first/final states 与既有模型结果。模型调用 0，Production/benchmark 代码修改 0，evidence 修改 0。

## Question

是否存在一个在模型调用前、只依赖 Detector candidate geometry 的确定性门控，使 target-anchored de-emphasis 仅用于身份串扰风险，而普通 F1 继续使用当前 Production evidence；再叠加已确认的 long-range not-satisfied escalation 和 uncertain immutable，形成可进入 Production 的整体 behavior policy？

## Candidate-level geometry seam

对每个 target candidate 使用 Production 固定 35% expanded crop，计算同一 localization target 的每个其他 candidate bbox 被该 crop 覆盖的比例：

`neighbor_coverage = area(expanded_target_crop ∩ neighbor_bbox) / area(neighbor_bbox)`

候选规则：

```text
IDENTITY_CONTAMINATION_RISK =
  candidate_count >= 2
  AND max_neighbor_coverage >= 0.70
  AND covered_neighbor_center_inside_target_crop
```

规则是 candidate-level，不是 image-level；不得因同图另一个 candidate 触发而连带触发当前 candidate。

### Frozen-set result

- 触发：3/15 candidates。
- `challenge_001`：A 73.37%，B 77.04%，两者均触发。
- `challenge_004` elder A：74.36%，触发。
- `challenge_004` child B：42.58%，中心不在 crop 内，不触发。
- F1：0/10 触发。
- 所有未触发多候选 unit 的最大 coverage 上界为 42.58%；触发下界为 73.37%，当前冻结集存在 30.79 个百分点的间隔。

该 seam 会把普通 F1 保持在 Production evidence，同时在 `challenge_001` 两个相互严重进入 crop 的人物上启用 target anchoring。它也会在 `challenge_004` 老人上启用 anchoring，随后由已确认的 not-satisfied long-range escalation 救回。

## De-emphasis 与 Arm B F1 回归的拆分

R3 A/B first-pass 对比显示，15 个 candidates 中只有三处状态发生变化：

1. `challenge_001` bystander：`satisfied → uncertain`，有益；几何规则触发。
2. `challenge_004` child：`not_satisfied → uncertain`，安全但非必要；几何规则不触发，组合政策保留当前 `not_satisfied`。
3. `F1::fishing_014.jpeg` candidate C：`uncertain → satisfied`，有害；几何规则不触发，组合政策避免该 false assignment。

因此，geometry-gated de-emphasis 在当前冻结集上可以隔离 `challenge_001` 的 identity 收益并避开 F1 的 de-emphasis harm。

## Mechanical composite-policy simulation

模拟政策：

```text
identity risk true
  → target-anchored first pass

identity risk false
  → current Production first pass

satisfied
  → immutable

uncertain
  → immutable

OBJECT_MEDIATED_SCENE_INTERACTION + not_satisfied
  → one target-anchored full-scene escalation
```

所有状态均来自既有字节锁定结果，不做新的视觉裁决。

### Challenge safety

- `challenge_001` bystander：target-anchored `uncertain` 5/5；false assignment 消失。
- `challenge_001` true operator：`satisfied` 5/5。
- `challenge_003`：`uncertain` 5/5，因 immutable 不再被 full-scene 压成 binary。
- `challenge_004` elder：target-anchored first pass `not_satisfied`，long-range escalation 后 `satisfied` 5/5。
- `challenge_004` child：current first pass `not_satisfied`；同一 target-anchored三图输入的既有 full-scene结果为 `not_satisfied` 5/5，保持安全。

### F1

- Geometry-gated de-emphasis：F1 触发 0/10，因此没有 de-emphasis 回归。
- Long-range not-satisfied escalation：三个已覆盖 negative controls 3/3 保持 `not_satisfied`。
- 但 `F1::fishing_010.jpeg` candidate C 的 current first pass 是 `uncertain`；当前 Production fallback 能将其正确解析为 `not_satisfied`，而组合政策的 uncertain immutable 会保留 `uncertain`。

因此机械评分为：

| Policy | F1 candidate correct | F1 task correct |
|---|---:|---:|
| Current Production A | 5/10 | 3/6 |
| Synthesized candidate | 4/10 | 2/6 |

唯一新增的 F1 score regression source 是 `F1::fishing_010.jpeg` candidate C 的 uncertain immutable，不是 identity de-emphasis。

## Decision

`DETERMINISTIC_IDENTITY_CONTAMINATION_GEOMETRY_SEAM = FOUND AS RESEARCH CANDIDATE`

`GEOMETRY_GATED_DE_EMPHASIS = ROUTABLE ON FROZEN 9-IMAGE / 15-CANDIDATE SET`

`FULL_BEHAVIOR_PRODUCTION_POLICY = NOT CONFIRMED`

理由：在维持既有 F1 non-regression Gate 时，global uncertain immutable 仍造成 1 个 candidate 与 1 个 task 回归。已找到的 geometry seam 解决了 identity evidence 的选择问题，但没有解决“合法 ambiguity 安全”与“可正确解析的 uncertain negative”之间的状态策略冲突。

70% 阈值是在本冻结集上观察到的干净间隔，只能作为 targeted confirmation 候选，不能直接成为 Production 常量。

## Next boundary

在运行任何新模型前，需要先决定：

1. 是否保持 F1 non-regression Gate，并另行寻找同样 pre-model deterministic 的 uncertain routing seam；或
2. 是否接受 `F1 5/10 → 4/10、3/6 → 2/6` 为明确的安全 trade-off 并正式修改 Product Gate。

不得把这个决策伪装成 geometry threshold confirmation。Relation small held-object blocker（F4 017/020）仍独立 pending。

- `PRODUCTION MODIFICATION = NOT AUTHORIZED`
- `PRODUCTION MERGE = NOT AUTHORIZED`
- `GENERAL_RGB_FINAL_ACCEPTANCE_V2 = NOT AUTHORIZED`
- `REMOTE_SENSING_WATER_QUALITY = BLOCKED`
