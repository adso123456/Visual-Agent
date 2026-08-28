# GENERAL_RGB_BEHAVIOR_RELATION_JOINT_TARGETED_CONFIRMATION_V1

状态：`CONTRACT FREEZE CANDIDATE / REVIEW REQUIRED`

本阶段只确认两个已经由历史证据合成或确认的 General RGB policy candidate：Behavior deterministic routing 与 Relation hand-conditioned fallback activation。它不再研究新 evidence Arm，不包含 `F4::fishing_020`，不修改 Production，也不执行模型。

## 1. Behavior policy candidate

```text
identity_contamination_geometry == true
  → target-anchored 35% local first pass

otherwise
  → current Production isolated + 35% local first pass

satisfied
  → immutable

uncertain + candidate_count == 1
  → immutable

uncertain + candidate_count >= 2
  → one full-scene disambiguation
     identity-risk candidate → target-anchored full scene
     ordinary candidate      → current Production full scene

OBJECT_MEDIATED_SCENE_INTERACTION + not_satisfied
  → one target-anchored full-scene escalation
```

Identity contamination geometry 必须在 VLM 调用前确定：同一 localization target 至少2个 candidates；当前 candidate 的 35% crop 覆盖任一 non-target candidate bbox `>=70%`；且该 non-target candidate center 位于当前 crop 内。不得根据 case ID、模型文本或输出状态覆盖。

Target anchoring 沿用冻结 R3 算法：不删除其他人物；`non-target mask - target mask` 使用固定 45/55 灰度混合；target overlap 优先；当前 target 保持原 RGB 并绘制固定 5px 红 contour；35% crop 不变。

`OBJECT_MEDIATED_SCENE_INTERACTION` 必须按冻结 task semantic 在 first-pass 结果产生前确定；同一 task 不能按图片或 candidate 改分类。

## 2. Relation activation candidate

只适用于：

```text
relation == held_by_target
AND subject is relation-eligible
AND initial full-scene relation verification has no satisfied binding for subject
AND existing 35% subject-conditioned secondary localization + verification
    has executed once and still has no satisfied binding for subject
```

满足以上全部条件时，每个 subject 最多执行一次 hand-conditioned related-object localization：

1. 复用现有 35% subject context view。
2. 使用 Production Grounding DINO、query=`hand`、threshold=`0.30`。
3. 只保留 bbox center 位于 subject bbox 的 hand detections。
4. 固定排序：confidence desc，然后 x1/y1/x2/y2；最多2个 hand。
5. 每个 hand bbox 四侧按自身宽高扩展100%，并 clamp 到 view。
6. 在该 view 中使用原 `related_object` canonical query 和 threshold `0.30`。
7. remap 到原图坐标；IoU `>=0.80` 稳定去重；不得改 query、阈值或 Detector。
8. 只把新 admission candidates 送入原样 Production `verify_relations()`；不重判旧 candidates，不放宽 `held_by_target`。
9. 新 bindings 进入既有 relation outcome / ownership resolver；不改 resolver。

若 initial 或 existing secondary 已产生 satisfied，hand-conditioned Detector/VLM 调用必须为0。若没有有效 hand 或没有新增 related candidate，则不调用新的 Relation VLM，并保留既有 outcome。

Relation 仍使用 Production full-scene marked JPEG。18 MiB PNG normalization 不适用于当前 Relation 路径。

## 3. Frozen selection

### Behavior

- Challenge：`challenge_001/003/004`，5 repetitions，5 candidate units，共25 observations。
- F1 controls：`fishing_001/005/010/014/004/018`，1 repetition，10 candidate units，共10 observations。
- 合计：9 images、15 candidate units、35 first-pass observations；fallback data-dependent，最大35。

### Relation

| Case | Role | Repetitions | Gate role |
|---|---|---:|---|
| `F4::fishing_017.jpeg` | in-scope positive / activation target | 5 | hand fallback 后 A retained，目标小鱼绑定；桶鱼不得 false bind |
| `F2::fishing_005.jpeg` | frozen negative | 5 | fallback 不得制造拿鱼竿 false positive |
| `F2::fishing_024.jpeg` | existing-path positive | 1 | existing satisfied 必须阻止 hand fallback |
| `core_003` | domain-neutral umbrella positive | 1 | existing satisfied 必须阻止 hand fallback |
| `core_014` | domain-neutral 0-target safety | 1 | 不得制造 target / false binding |

共13 relation policy executions。每个 execution 最多包含 initial、existing secondary、hand-conditioned 三次 Relation verifier logical calls；实际调用数必须按阶段报告，不得隐藏零候选 fast path。

## 4. Gates

### Behavior

- `challenge_001`：bystander satisfied `0/5`；true operator retained `>=4/5`。
- `challenge_003`：legitimate uncertain `5/5`；confident binary `0/5`。
- `challenge_004`：elder retained `>=4/5`；child satisfied `0/5`。
- F1：candidate correct `>=5/10`；task correct `>=3/6`；相对冻结 Production A candidate/task regression 均为0。
- `F1::fishing_004` A 必须 satisfied。
- New false assignment、fallback harm、provider/protocol/validator/evidence final failure 均为0。

### Relation

- `F4::017`：final A retained `>=4/5`；hand-conditioned target fish satisfied `>=4/5`；所有 non-target bucket/bucket-edge fish satisfied = 0；hand fallback 每个 repetition 最多一次。
- `F2::005`：final A retained `0/5`；任何 hand-conditioned candidate satisfied = 0。
- `F2::024`、`core_003`：final positive retained；hand-conditioned Detector calls = 0，Relation VLM fallback calls = 0。
- `core_014`：final target count = 0；任何新增 false binding = 0。
- 所有13 executions final failure = 0；failed execution replacement = false。

### Joint decision

Behavior 与 Relation Gates 必须全部通过，才可写：

`JOINT_POLICY_CANDIDATE = CONFIRMED FOR IMPLEMENTATION REVIEW`

通过仍不等于 Production implementation/merge 或 Final Acceptance V2 已授权。任一 Gate 失败则保留现有 Production policy，并按明确失败模块返回。

## 5. Execution boundary

- Local VLM：`qwen3.8:27b-mtp-q4_K_M`
- Endpoint：`http://192.168.250.9:11434/v1`
- Timeout：120 秒
- Temperature：0（Production verifier）
- Concurrency：1
- Planner calls：0
- Final Response calls：0
- Failed execution replacement：false
- 失败保留，不补跑、不调参、不改 evidence、selection 或 scoring。

当前 `MODEL EXECUTION = NOT AUTHORIZED`，`PRODUCTION MODIFICATION / MERGE = NOT AUTHORIZED`。
