# GENERAL_RGB_BEHAVIOR_RELATION_PRODUCTION_IMPLEMENTATION_CONTRACT_V1

## 状态

`CONTRACT FROZEN`
- 冻结修订：`revision 2`（FORMAL REVIEW = CHANGES REQUIRED；5 个 Blocker 全部收口；revision 1 = `968e8c0` 保持不可变，作为审查轮次证据）
- 阶段性质：`READ-ONLY DESIGN ONLY`
- Production code modification：`NOT AUTHORIZED`
- Model execution：`NOT AUTHORIZED`
- Production merge：`NOT AUTHORIZED`
- GENERAL_RGB_FINAL_ACCEPTANCE_V2：`NOT AUTHORIZED`
- Remote Sensing Water Quality：`BLOCKED`

本阶段只做一件事：把 V2 已确认的两个 policy candidate 精确映射到
`be54f3c89171d8b16f53c82397e9f468fb4b4c97` 的 Production 路径，冻结
"改哪些函数、插入位置、保持哪些原逻辑不变、需要哪些 targeted regression gates"。
本阶段不修改任何 Production 代码，不执行模型，不运行联合 benchmark。
不要改 selection，不要增加 case，不要重新跑模型。

## 0. 依据与锁定

- Formal Production master：`4dac9cb3823e22e90ff3bb8157c6544c6c6b88fd`
- 本次实现目标树（execution base）：`be54f3c89171d8b16f53c82397e9f468fb4b4c97`
- Joint confirmation frozen evidence head：`30fa9cddd851f376831b2bd3d940f6ab1165c084`
- V2 evidence HEAD（revision 1 parent）：`60a1da895dd9f330006adb9362a2a925181e3858`
- Reviewed runner：`a1c61c3b4d38c25bafd841fc3b8c52fecbdbb897`
- Joint decision：`JOINT_POLICY_CANDIDATE = CONFIRMED`（Behavior Gate PASS + Relation Gate PASS，48/48 success，failed_execution_replacement=false）
- 冻结合同/selection SHA：合同候选 `eb2bc508...f4f3ffd780`、selection `383b9742...a6074a2f`、V2 authorization `c3f8c4b0...377f1cc`

实现 diff 的冻结基线（be54f3c 树内 8 个相关文件 SHA-256，与 reviewed runner
`PRODUCTION_FILE_SHA256` 完全一致；实现审批时必须复算，任一不匹配即阻塞）：

| File | SHA-256 |
|---|---|
| visual_agent/pipeline.py | `531903d340e64faa6e745c9fb83d65532d553ff604a87789f2057a57aadb0452` |
| visual_agent/evidence.py | `8dc4f1d6a62f1873b1479a78c08130d0c4d79286a2afcaa24d11f93cb5749747` |
| visual_agent/vlm.py | `a2df5c9605deb3ee9d5e7803eab0effa83e5c6c21cc928633a0460f54ae6d83e` |
| visual_agent/relations.py | `293f2c983f792d541ec0c6021ef49e82ae0d0b8553963bc925424b555286f968` |
| visual_agent/grounding.py | `ac56602ecd1c4d09286784fc17eb79c18fe3ebb4c7f98f62ae96e0167c28f3be` |
| visual_agent/qwen_protocol.py | `89ccd004b9738804ecace48478044af660d5497aafa4d7753bc5e4a4c46ebfb3` |
| visual_agent/vlm_client.py | `a36782166b41fde299cb3cd328fb145bc0597ae8bd49c0510f1eb6d832a82c88` |
| visual_agent/deepseek_agent.py | `cdc6be9cdc4b518734b014ca9e44144d7b4da1895da6bdb74de9fed5290f1f12` |

## 1. 冻结策略语义（V2 已确认，实现必须 1:1 复现）

### 1.1 Behavior deterministic routing

```text
identity_contamination_geometry == true
  → target-anchored 35% local first pass（Arm B 语义）

otherwise
  → current Production isolated + 35% local first pass（Arm A 语义）

satisfied
  → immutable

uncertain + candidate_count == 1
  → immutable

uncertain + candidate_count >= 2
  → one full-scene disambiguation
     identity-risk candidate → target-anchored full scene（Arm C 语义）
     ordinary candidate      → current Production full scene（Arm A 语义）

OBJECT_MEDIATED_SCENE_INTERACTION + not_satisfied
  → one target-anchored full-scene escalation（Arm C 语义）
```

- 每次 candidate 只允许最多一次 fallback（disambiguation 或 escalation），与 V2 相同。
- fallback 只允许从 first-pass `uncertain`（multi-candidate）或
  `not_satisfied`（OBJECT_MEDIATED 任务）进入；first-pass `satisfied` 与
  `uncertain + candidate_count==1` 一律不可覆写。
- fallback 的 evidence 序列与 V2 runner 完全一致：`(isolated, local_of_first_pass_arm, fallback_full_scene)`。
  `isolated` 与 `local` 永远是 first-pass 已构造并验证过的同一对象：
  **不得重建、不得替换、不得重新 SAM**；只按路由替换第 3 张 `fallback_full_scene` 的来源——
  multi-candidate disambiguation：identity-risk → target-anchored 全图；ordinary → 现有 Production 全图；
  OBJECT_MEDIATED escalation：一律 target-anchored 全图。
  对 risk=false 的 F1 case，escalation 将 first-pass Arm A local 原样复用（与 V2 完全相同），
  绝不产生"target-anchored local + target-anchored full"这一未经确认的新请求形态。

### 1.2 Object-mediated 语义判定（冻结 predicate）

`OBJECT_MEDIATED_SCENE_INTERACTION` 只按冻结 task semantic 在 first-pass 结果产生前
按 plan 判定一次；同一 task 的所有 candidate、所有 repetition、所有图片不得改变分类。

- 冻结 marker：normalized behavior constraint text 与 `"正在钓鱼"` 精确相等。
- 该冻结 set 来自 R3 frozen selection 与 joint V2 的唯一 behavior task semantic
  （F1 6 条与 challenge 3 条全部为 `正在钓鱼`）。不得使用关键词、模糊匹配、
  模型文本或 case id 扩展该集合。
- 实现必须提供单一纯函数 `_object_mediated_behavior_constraint_indices(plan) -> tuple[int, ...]`：
  返回 behavior route 约束列表中 normalized text 与 `"正在钓鱼"` 精确相等的 positions；
  每个 plan 在 first-pass 前计算一次并固化；任何 map/filter 不得按图片或 candidate 覆盖。
- 冻结 activation guard：escalation 只有在该 plan 的 behavior route 恰有一个约束
  且返回 indices == `(0,)`（即 escalation 位置集 == 该 route 全部 positions）时才 arming。
  多 behavior constraint 的 plan（indices 为真子集）视为 `OUT OF CONFIRMED SCOPE`：
  对该 plan 不开启 escalation 路径，仅保留 identity-risk first-pass 与 multi-candidate
  disambiguation；单一约束 world 是 V2 唯一确认形态，禁止在实现中发明混合约束的
  escalation 语义。

### 1.3 Identity contamination geometry（冻结 predicate）

在 VLM 调用前对同一 localization target 的候选集合确定：

```text
candidate_count >= 2
AND 当前 candidate 的 35% crop 覆盖任一 non-target candidate bbox >= 70%
    （intersection(neighbor, crop) / area(neighbor)）
AND 该 non-target candidate center ((x1+x2)/2, (y1+y2)/2) 位于当前 crop 内
```

- crop 使用现有 `expanded_candidate_bbox`（35% margin、floor/ceil、image-boundary
  clamp），与 R3/R2 共用；不得改尺度。
- "non-target" 的定义与 reviewed runner 完全一致：按 candidate ID 排除当前 candidate
  （`neighbor["id"] == candidate_id` 时跳过），不依赖 bbox equality；
  API 冻结为 `identity_contamination_risk(image_size, candidate_id, candidates)`。
- 裁决完全由 bbox 几何确定，不得根据 case ID、模型文本或输出状态覆盖。
- 冻结向量表（R3 frozen_selection bbox + 实际图像尺寸计算，实现单测必须逐格复现）：

| Case | A | B | C |
|---|---|---|---|
| challenge_001 | True | True | — |
| challenge_003 | False | — | — |
| challenge_004 | True | False | — |
| F1::fishing_001.jpeg | False | — | — |
| F1::fishing_005.jpeg | False | — | — |
| F1::fishing_010.jpeg | False | False | False |
| F1::fishing_014.jpeg | False | False | False |
| F1::fishing_004.jpeg | False | — | — |
| F1::fishing_018.jpeg | False | — | — |

### 1.4 Target anchoring（冻结像素算法，与 R3 evidence builder 字节级同语义）

- target mask：当前 candidate 的 SAM mask；non-target person masks：同图其余全部
  runtime candidate 的 SAM masks（与 R3 builder `person_masks` 一致，含全部候选，
  不因 subject validity 过滤）。
- 只允许每图一次 SAM mask cache（现有 `ensure_masks` 已保证），本实现不再
  新增 SAM 调用。
- 像素公式（RGB 每 channel，uint8 → uint16 计算后写回）：

  `output = floor((45 * original + 55 * 128 + 50) / 100)`

  即 `(45 * original + 55 * 128 + 50) // 100`，禁止默认 banker rounding。
- de-emphasis 区域 = `union(non_target masks) & ~target_mask`；target mask 内像素
  保持原 RGB（target overlap 优先）。
- local 视图：先对全图做 de-emphasis，再按 `expanded_candidate_bbox` 裁剪；
  full-scene 视图：不裁剪、不预缩放。
- 最后仅为 target 绘制 `(255, 0, 0)`、5 px 的 mask contour（复用现有
  `_draw_mask_contour`），不给 non-target 添加文字/ID/bbox/第二种 contour。
- 其他人物不能被删除、裁掉、填充为纯色或从 prompt 中声明不存在；水面、鱼竿、
  渔网、船、岸线等场景像素保持原样。这是 de-emphasis，不是 context deletion。

### 1.5 Relation hand-conditioned fallback activation

只适用于：

```text
relation == held_by_target
AND subject 是 relation-eligible
AND initial full-scene stage 已结束且 subject 无 satisfied binding
AND 现有 35% subject-conditioned secondary localization 已尝试恰好一次
AND 现有 secondary 阶段结束后 subject 仍无 satisfied binding
```

- 现有 secondary 仅在 secondary candidates 非空时执行（保持 R2.3 不变）；secondary
  返回 0 个 candidate 时仍满足"secondary 已完成"，因此仍可进入 hand fallback。
- 每个 incomplete subject 最多一次 hand-conditioned related-object localization：

  1. 复用现有 35% subject context view（`build_subject_conditioned_grounding_view`）。
  2. 使用 Production Grounding DINO，query=`hand`，threshold=`0.30`。
  3. 只保留 bbox center 位于 subject bbox 内的 hand detections。
  4. 固定排序：confidence desc，然后 x1/y1/x2/y2；最多 2 个 hand。
  5. 每个 hand bbox 四侧按自身宽高扩展 100%（floor/ceil），并 clamp 到 view。
  6. 在该 hand view 中使用原 `related_object` canonical query 和 threshold `0.30`。
  7. hand-conditioned detections 经 view/base 偏移 remap 回原图坐标。
  8. 与 initial full-scene + existing subject-conditioned secondary 的全部旧 relation
     candidates（以及此前 subject 已新增的 hand candidates）比较；IoU `>=0.80`
     即视为已有 candidate，不得重新 admission。
  9. 剩余 hand candidates 按固定顺序（confidence desc，然后 bbox）彼此执行稳定
     IoU `>=0.80` 去重；不得改 query、阈值或 Detector。
  10. 只有真正新增的 candidates 才分配新 ID（接续现有 R 编号，全局唯一）。
  11. 只把这些 admission candidates 送入原样 Production `verify_relations()`；
      不重判旧 candidates，不放宽 `held_by_target`。
  12. 新 bindings 进入既有 relation outcome / ownership resolver；不改 resolver。

- per-subject 规则：已 satisfied 的 subject 不执行 hand-conditioned localization
  （该 subject 的 hand Detector 调用 = 0，hand Relation 调用 = 0）。
- 全局 matrix 规则（与 reviewed runner 一致）：当任何 incomplete subject 产生
  admission 时，全部 admitted candidates 必须对全部 relation-eligible subjects
  建立完整 binding matrix——**含先前已 satisfied 的 subject**；已 satisfied subject
  只参与 new-candidate matrix（且不触发 hand Detector）。
- case 级 gate：`F2::024` / `core_003` 的 "hand Detector = 0 且 hand Relation VLM = 0"
  是这两个单主体 positive control case 的整案 gate（案内无 incomplete subject ⇒ 无
  admission ⇒ 无 matrix），**不得提升为所有 satisfied subject 的通用规则**。
- 若没有有效 hand 或没有新增 related candidate，则不调用新的 Relation VLM，
  并保留既有 outcome（可能是 not_satisfied / uncertain）。
- Relation 仍使用 Production full-scene marked JPEG；18 MiB PNG normalization
  不适用于当前 Relation 路径（`_marked_scene_data_url` 保持不变）。

## 2. 实现面 — 要改的文件与函数

### 2.1 `visual_agent/evidence.py`（纯新增，不改任何现有函数）

| 新增函数 | 规格 | 依据 |
|---|---|---|
| `identity_contamination_risk(image_size, candidate_id, candidates) -> bool` | §1.3 冻结 predicate；`candidates` 为带 `{id, bbox}` 的序列，按 ID 排除当前 candidate（不依赖 bbox equality）；复用 `expanded_candidate_bbox`；`len(candidates) < 2` 时返回 False；P1 调用方传入 runtime_candidates | joint runner `identity_contamination_risk`（a1c61c3） |
| `blend_non_target_people(source, target_mask, person_masks) -> np.ndarray` | §1.4 冻结公式；mask 尺寸校验；`de_emphasis = union(people) & ~target`；target-wins | R3 benchmark `evidence_builder.py::blend_non_target_people` |
| `build_target_anchored_behavior_evidence(image_path, bbox, target_mask, person_masks) -> Image.Image` | 全图 de-emphasis 后按 35% crop 裁剪 + target 5px 红 contour | R3 builder `build_target_anchored_evidence(full_scene=False)` |
| `build_target_anchored_full_scene_evidence(image_path, target_mask, person_masks) -> Image.Image` | 全图 de-emphasis + target 5px 红 contour，不裁剪 | R3 builder `build_target_anchored_evidence(full_scene=True)` |

保持不变（字节级，不动）：`ISOLATED_BACKGROUND_RGB`、`BEHAVIOR_MARGIN`、
`BEHAVIOR_CONTOUR_RGB`、`BEHAVIOR_CONTOUR_WIDTH`、`_load_image_and_mask`、
`build_isolated_instance_evidence`、`build_behavior_evidence`、
`expanded_candidate_bbox`、`build_subject_conditioned_grounding_view`、
`_draw_mask_contour`、`build_candidate_marked_full_scene_evidence`。

### 2.2 `visual_agent/pipeline.py`（两处插入 + 四个新 helper）

插入点 P1 — Behavior route（现 `run_pipeline` 内 candidate loop 的
`if route == "behavior":` 块，be54f3c 行 494–533 起）：

1. 在 first-pass VLM 之前、candidate loop 内确定每 candidate：
   - `identity_risk = evidence.identity_contamination_risk(image_size, candidate["id"], runtime_candidates)`；
     图像尺寸在 run_pipeline 顶部用 PIL 打开一次取得（不增加任何 VLM/SAM/DINO 调用）。
   - first-pass 证据：`(isolated, local)`，其中
     `local = build_target_anchored_behavior_evidence(...)`（risk 为 True）或
     `build_behavior_evidence(...)`（risk 为 False）；person_masks 取自现有
     `mask_cache[("subject", other_id)]["mask"]`（其他全部 runtime candidates）。
2. 结果路由（按 §1.1；`object_mediated_indices` 由 §1.2 的
   `_object_mediated_behavior_constraint_indices(plan)` 提供，plan 级一次固化）：
   - `satisfied` → 不 fallback；
   - 首个 check 为 `uncertain` 且 `len(runtime_candidates) == 1` → 不 fallback；
   - `uncertain` positions 存在且 `len(runtime_candidates) >= 2` →
     一次 disambiguation fallback，evidence = `(isolated, SAME first-pass local, full_scene)`：
     risk → `build_target_anchored_full_scene_evidence`；否则现有
     `build_candidate_marked_full_scene_evidence`；
   - escalation arming（§1.2 guard 成立）且对应 first-pass 状态为 `not_satisfied` →
     一次 escalation fallback，evidence = `(isolated, SAME first-pass local, build_target_anchored_full_scene_evidence(...))`；
     **不得重建或替换 first-pass `local`，也不得把 first-pass local 换成 target-anchored local**；
   - 每 candidate 最多一次 behavior fallback：在 §1.2 guard 下 disambiguation 与
     escalation 对同一 candidate 互斥（armed ⇒ 单一约束 ⇒ 单状态），不会同时触发。
   - 保持现有批量语义：fallback 调用传入的 route items 只包含被该次 fallback 覆盖的 positions。
3. 机械 write-back（显式冻结，替代模糊的"仅 uncertain positions"）：
   - disambiguation：对 `uncertain` positions（fallback_items 与之 1:1 zip）写回；
   - escalation：对 arming 位置集中 first-pass 为 `not_satisfied` 的 positions 写回；
   - 两种写回均沿用现有 `checks[position] = fallback_check` 的 1:1 zip 语义；
   - protocol 合并沿用现有 `_merge_protocol_metadata([protocol, fallback_protocol])`。
4. 新增 module-level 纯函数 `_object_mediated_behavior_constraint_indices(plan) -> tuple[int, ...]`
   （§1.2，含 activation guard 常量）；第一次使用前由 run_pipeline 对当前 plan 计算一次并固化。

插入点 P2 — Relation hand fallback（现有 R2.3 secondary ownership 块结束、
`if relation_protocols:` merge 之前，be54f3c 行 704–706 之间）：

1. 新增 module-level helper `_stable_hand_candidate_admission(hand_candidates, old_candidates)`：
   按 `(-dino_confidence, *bbox)` 排序；任一 `IoU(box, old) >= 0.80` 拒绝
   （old = initial + secondary 全部候选 + 此前 subject 已 admitted）；再与已保留
   候选按同样顺序做稳定 IoU `>=0.80` 去重；剩余项接续 `R{len(relation_candidates)+1}`
   分配全局唯一新 ID。与 joint runner `stable_admit` 完全同语义。
2. 新增 module-level helper `_hand_conditioned_candidates(image_path, subject,
   related_object, old_candidates, detector)`：§1.5 全部几何/排序/top-2/100% 扩展/
   clamp/view 裁剪临时 PNG/remap/稳定 admission；返回 `(admitted, telemetry)`。
   Detector 使用 run_pipeline 已创建的同一实例；临时 view 保存沿用 R2.3 的
   `tempfile.TemporaryDirectory(prefix="visual_agent_relation_")` 模式。
3. 新增 module-level `_run_hand_conditioned_fallback(...)` 编排（§1.5 门 1–12）：
   - incomplete subject 集合 = relation_subjects 中在 initial + secondary
     全部 bindings（含 focused ownership 替换后的 bindings）仍无 `satisfied` 者；
   - 每个 incomplete subject 恰好一次；`admitted` 全局累积（后一个 subject 必须看到
     前一个已新增的全局候选）；
   - 已 satisfied subject：不执行 hand localization（该 subject hand Detector=0），
     但当其他 incomplete subject 产生 admissions 时，仍以 `verify_relations` 参与
     new-candidate binding matrix（含该 subject 对 admitted 的新 bindings，可进入
     focused ownership 的 `only_related_ids=new_ids` 裁决）；
   - 无有效 hand 或无新增 → 0 次新 Relation VLM 调用，全部 subject 保留既有 outcome；
   - 有新增：对全部 relation-eligible subjects 以 `verify_relations` 建立完整
     binding matrix（与 reviewed runner 一致，每次仍只传一个 subject），protocol 追加进
     `relation_protocols`；然后调用现有 `_resolve_focused_ownership(..., only_related_ids=new_ids)`。
4. 结果扩展（additive，不改既有字段）：
   - `result["relation_hand_fallback"]`：每 subject `{attempted, hand_detector_calls,
     admitted_count, new_candidate_ids, hand_relation_calls}` + 聚合
     `{attempts, detector_calls, admitted_count, hand_relation_calls, max_per_subject=1}`；
   - `result["behavior_routing"]`：每 candidate `{identity_risk, first_pass_arm,
     route, fallback_arm, fallback_attempted, write_back_positions}`；
   - `qwen_protocol.relation_verification` 自动经现有 `_merge_protocol_metadata`
     覆盖 hand fallback protocols（relation_protocols 追加后 merge，无需改 merge 本身）。

保持不变（字节级，不动）：`_union_bbox`、`_local_summary`、`_relation_evidence`、
`_merge_protocol_metadata`、`_resolve_focused_ownership`、`resolve_relation_outcomes`、
`_build_semantic_groups`、`_merge_sam_metrics`、`run_pipeline` 的 subject
validity / attribute route / relation full-scene、R2.3 secondary 块、final_subjects /
targets / save_results / final response / timings 结构（仅新增 additive key）。

### 2.3 不改的文件（字节级不变）

`visual_agent/vlm.py`（含 `verify_candidate_constraints` 行为 route 指令文字——
B/C evidence 仍是"第 2 张带红色当前候选轮廓的 35% 局部图；第 3 张仅标记同一候选的
完整场景 fallback 图"，语义依旧成立，禁止改 prompt）、`visual_agent/relations.py`
（verifier/focused ownership 原样）、`visual_agent/grounding.py`、
`visual_agent/vlm_client.py`、`visual_agent/qwen_protocol.py`、
`visual_agent/deepseek_agent.py`（plan schema / router / prompts 原样）、
`visual_agent/segmentation.py`、`visual_agent/models.py`、
`visual_agent/renderer.py`、`visual_agent/actions.py`、`api/*`、`demo_ui/*`、
`demo_showcase.py`、`main.py`。

## 3. Targeted regression gates（实现阶段必须全部满足）

### 3.1 既有测试全部保持绿色

以下 be54f3c 既有测试在实现 diff 后必须全部 PASS（实现合同审批前先在 be54f3c 上跑通
作为 baseline）：

- `benchmark/test_planner_config.py`、`test_router_plan_contract.py`、
  `test_vlm_client_config.py`、`test_evidence_builders.py`、
  `test_evidence_payload_limit.py`、`test_box_action.py`
- `benchmark/test_pipeline_router.py`、`test_relation_router.py`、
  `test_relation_identity_contract.py`、`test_phase7_relations.py`、
  `test_phase7_composite.py`
- `benchmark/test_phase6_planner.py`、`test_phase7_planner.py`、
  `test_phase8_candidate_contract.py`、`test_phase8_protocol_retry.py`、
  `test_router_vlm.py`

唯一允许的既有测试改动（测试桩，不是生产逻辑）：

1. 既有 stub Detector 的 `detect(image, target_text, threshold)` 增加分支：
   `target_text == "hand"` 返回 `[]`；其余 query 保持原行为。
   这使得 hand-fallback 在旧场景中零新增、零新 Relation VLM 调用，旧断言继续成立。
2. 若既有断言检查 `detector.calls` 的精确内容，允许按顺序追加 "hand" 或改为
   过滤掉 "hand" 后比对；不得放宽 candidate/binding/verifier 计数断言。

### 3.2 新增 targeted 单测（全部 stub，禁止真实模型调用）

| 新测试文件 | 覆盖 |
|---|---|
| `benchmark/test_behavior_policy_implementation.py` | §1.3 冻结向量表 15/15 逐格（新 API `identity_contamination_risk(image_size, candidate_id, candidates)`，含同 bbox 双 ID 只能按 ID 排除的用例）；`_object_mediated_behavior_constraint_indices` 仅对 `"正在钓鱼"` 命中、单一约束 plan 返回 `(0,)`、多约束 plan 返回真子集且 escalation 不 arming、同 plan 恒定；§1.4 公式 byte-exact（合成像素：`(45p+55·128+50)//100`、target-wins、contour 位置/颜色/宽度、non-target 保留场景像素）；routing 决策（stub verifier 返回 satisfied/uncertain-single/uncertain-multi/not_satisfied，断言 first_pass_arm、fallback_arm、fallback_attempted、evidence 图像选择）；**fallback 复用 first-pass isolated/local 同一对象（断言对象身份或字节一致、不得重建 local）**；disambiguation 只写回 uncertain positions、escalation 只写回 arming 集内 not_satisfied positions（stub 返回 satisfied 时断言对应 check 被替换）；satisfied 与 uncertain-single 不可覆写；每 candidate 至多一次 fallback |
| `benchmark/test_relation_hand_fallback_implementation.py` | hand 中心过滤 / 排序 / top-2 / 100% 扩展与 clamp / remap；vs 全部旧候选与跨 subject 全局去重 IoU≥0.80；ID 接续全局唯一；新增候选只对 admitted 验证且矩阵覆盖全部 relation-eligible subjects；**mixed-status 用例：一 satisfied subject + 一 incomplete subject 产生 admission → satisfied subject 不触发 hand Detector、但仍参加 new-candidate matrix**；**case 级单主体 positive control（F2::024/core_003 语义）：整案 hand Detector=0 且 hand Relation VLM=0**；每 subject 最多一次；无新增 → 0 new Relation VLM 且 outcome 保留；F2::005 负例（admitted 后仍 0 satisfied）；core_014 0 target / 0 new false binding |
| `benchmark/test_production_implementation_contract_preflight.py` | **两时点分离**：BEFORE implementation——当前 worktree 8/8 生产文件 == §0 冻结 SHA（implementation preflight）；AFTER implementation——6 个不变文件 == 冻结 SHA，`pipeline.py` / `evidence.py` 允许变化但必须证明 parent/base == `be54f3c` 且 diff scope 仅含合同允许内容（或改为对 `git show be54f3c:<path>` 复算旧 SHA，而不是对修改后的当前文件复算）；断言合同 status / authorized 标志；断言 `relation_hand_fallback` 与 `behavior_routing` additive key 存在性 |

### 3.3 门条件

- 全部既有 + 新增测试 PASS；provider/protocol/validator/evidence final failure 概念
  不适用于 stub 单测（无模型调用）。
- 实现 diff 不得改变以下行为的输出：非 behavior 路由、R2.3 secondary 时序、
  focused ownership、resolve_relation_outcomes 三态映射、final_subjects/targets/
  save_results schema、Planner/Final Response。
- Behavior fallback 计数上限：每 candidate 至多一次（disambiguation 或 escalation 互斥）；
  write-back 位置集机械确定（见 §2.2 P1 第 3 条）。
- hand fallback 计数上限：每 incomplete subject 1 次 localization；每 subject 最多 2 个 hand、
  每 hand 一次 related-object Detect；new-admission 存在时新 Relation VLM 调用为
  `len(relation_eligible_subjects)` 次（每次一个 subject，含已 satisfied subject）；
  已 satisfied subject 自身的 hand Detector 恒为 0。

## 4. 后续授权边界

- 本合同的实现（§2 diff）需要另行单独授权；授权时必须按 §3.2 preflight 两时点规则
  复核代码状态（BEFORE：8/8 SHA；AFTER：6/8 SHA + base/diff-scope 证明）。
- 实现完成后允许运行的仍是 stub 单测；真实模型 targeted regression 与
  GENERAL_RGB_FINAL_ACCEPTANCE_V2 另行授权。
- 本合同冻结提交（revision 2）经窄审查后仍不构成 Production modification、merge 或
  Final Acceptance V2 授权。

## 5. 当前禁止项

- 不改任何 Production 文件、测试、prompt 或模型参数（本阶段）。
- 不调用 Planner、VLM、DINO、SAM。
- 不启动/停止模型服务。
- 不重跑联合 benchmark、不重新研究 Behavior/F4 policy、不新增 evidence Arm、
  不把 `F4::fishing_020` 或任何新 case 加入评估。
- 不改 selection / frozen schedule / gate 数量。
- 不 merge 任何分支，不建立 GENERAL_RGB_FINAL_ACCEPTANCE_V2。
