# Phase 5 图片回归测试报告

- 冻结基线：`ead6c49912de4e168398386dfb6ce8b1a3d18b44`
- Core：13/15，通过率 86.67%
- Challenge：5 个，单独报告，不计入 Core 通过率
- 不同图片：10 张
- 正式业务代码修改：否

## Core 指标

- target_object accuracy：86.67%
- action accuracy：100.00%
- constraint semantic accuracy：86.67%
- target selection exact match：100.00%
- negative pass：100.00%
- segmentation visual pass：91.67%（12 个进入 SAM 的 Core）
- action visual pass：100.00%

## Core 失败

### core_004 — PLAN

- 图片：`images/test_images/commons_umbrella.jpg`
- Prompt：把手持雨伞的人单独抠出来
- Expected：`{"target_object": "person", "action": "cutout", "target_count": 1, "target_description": "街上手持黑色雨伞的人", "constraints_semantics": ["手持雨伞"]}`
- Actual：`{"plan": {"target_object": "person with umbrella", "label": "手持雨伞的人", "constraints": ["手持雨伞", "人"], "action": {"type": "cutout"}}, "candidate_count": 1, "target_count": 1}`
- 证据：Plan 错误输出 target_object=person with umbrella、constraints=[手持雨伞, 人]；最终人数正确，但透明抠图仅保留人体，完全漏掉雨伞。
- 次要问题：SEGMENTATION：人体 mask 未包含作为关系证据的雨伞

### core_015 — PLAN

- 图片：`images/test_images/test_family_fishing.jpg`
- Prompt：模糊图中的儿童
- Expected：`{"target_object": "person", "action": "blur_target", "target_count": 2, "target_description": "船上的两名儿童", "constraints_semantics": ["儿童"]}`
- Actual：`{"plan": {"target_object": "child", "label": "儿童", "constraints": [], "action": {"type": "blur_target"}}, "candidate_count": 2, "target_count": 2}`
- 证据：Plan 使用 target_object=child、constraints=[]，违反当前人物统一使用 person 的规划契约；但两名儿童最终均正确模糊。
- 次要问题：无

## Challenge

- **challenge_001 — PASS**：235×156 低分辨率相邻人物场景只保留红帽钓鱼者，白帽人物被拒绝。
- **challenge_002 — PASS**：中央完整人物被保留，左侧两个局部肢体候选均被拒绝。
- **challenge_003 — AMBIGUOUS**：低光远景人物旁有多根架设鱼竿，但无法确认人物当下正在操作；系统保守返回 targets=[]。
- **challenge_004 — AMBIGUOUS**：老人明确钓鱼；儿童与长竿关系存在歧义。系统将两人均保持明亮，可能存在假阳性。
- **challenge_005 — FAIL**：密集红衣场景仅产生 4 个 person candidates、保留并描边 3 人，明显漏掉背景多名红衣人物；主要是远处小目标未进入候选。

## Constraints 冗余

core_004 返回 constraints=[手持雨伞, 人]；同图钓鱼六种 action 均稳定返回 [正在钓鱼]，未出现冗余人。

## Repeatability

- `core_006`：3 次，完全一致
- `core_011`：3 次，完全一致
- `core_012`：3 次，完全一致

## 性能（秒）

| 阶段 | count | min | median | max | p95 |
|---|---:|---:|---:|---:|---:|
| qwen_plan_seconds | 20 | 0.667 | 0.921 | 1.822 | 1.56 |
| grounding_dino_seconds | 20 | 8.906 | 9.834 | 11.749 | 11.562 |
| group_verification_seconds | 20 | 0.0 | 1.812 | 4.8 | 3.346 |
| sam2_load_seconds | 16 | 5.081 | 5.549 | 6.341 | 6.135 |
| sam2_inference_seconds | 16 | 0.172 | 0.414 | 0.573 | 0.529 |
| cli_total_seconds | 20 | 10.538 | 18.614 | 21.897 | 21.87 |

> Grounding DINO timing 按当前 pipeline 口径统计，包含模型初始化/加载，不是纯 inference。

## 已知 Runtime 问题

中文路径预检记录到 9 次 renderer 失败；同字节 ASCII 副本全部成功。未修改正式代码。

## 结论

最可靠：清晰目标、清晰行为/属性、多目标 action、negative handling、重复稳定性。

最薄弱：Plan 复合实体/冗余约束、关系物体随主体抠出、密集小目标召回、Windows 中文路径。

本阶段无外部 blocker；benchmark 目标已完成。
