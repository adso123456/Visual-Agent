# SCENE_CONTEXT_GROUNDING_AND_CONTRACT_V1B

## 结论

- `SIMPLIFIED_GLOBAL_CONTEXT_CONTRACT = ACCEPTED`
- `SINGLE_CANDIDATE_FULL_SCENE_AS_GENERAL_BEHAVIOR_EVIDENCE = REJECTED`
- `SINGLE_CANDIDATE_FULL_SCENE_FOR_SCENE_RELATION_OR_REGION_RESEARCH = RETAIN_AS_HYPOTHESIS`
- `PRODUCTION_INTEGRATION = NOT_AUTHORIZED`

## 冻结边界

复用 Phase 1 的36条选择集和60个既有DINO candidates；模型、endpoint、temperature、人工语义均不变。没有运行Detector、SAM或Pipeline，没有修改Production。

## 结果

| Prompt | Current | Complex B | Simplified B | Single Full Scene |
|---|---:|---:|---:|---:|
| F1 | 3/6 | 3/6 | 4/6 | 2/6 |
| F2 | 4/6 | 4/6 | 5/6 | 4/6 |
| F4 | 3/6 | 5/6 | 5/6 | 4/6 |
| P1 | 3/6 | 5/6 | 5/6 | 4/6 |
| P3 | 2/6 | 3/6 | 4/6 | 4/6 |
| P4 | 3/6 | 3/6 | 2/6 | 5/6 |
| **Overall** | **18/36** | **23/36** | **25/36** | **23/36** |

### 问题一：精简合同

精简为 `task_status + facts[string] + evidence` 后：

- contract attempts：44 → 36
- retries：8 → 0
- final contract failures：3 → 0
- semantic correctness：23/36（63.89%）→ 25/36（69.44%）
- recorded elapsed：1310.997s → 843.367s
- recorded tokens：209439 → 157950

相对复杂B，3条错误变正确（F1::014、F2::008、P3::001），1条正确变错误（P4::025）。P1::001虽然由protocol failure变成合法JSON，但语义仍错误。合同简化达成稳定性目标且总体语义不降。

逐类仍不均衡：P4从3/6降到2/6，所以结论只批准“精简合同作为后续contract候选”，不批准直接Production接入。

### 问题二：Single-candidate full-scene

- 60个candidate requests全部一次通过：60 attempts、0 retry、0 failure。
- 总体23/36，高于Current 18/36，但不高于Simplified B 25/36。
- 关键F1/F2合计：Current 7/12，Single Full Scene 6/12。F1为2/6，低于Current的3/6；F2为4/6，与Current相同。
- 因此“它在F1/F2明显超过35% crop”的假设不成立，不能作为通用behavior evidence。
- P3/P4合计9/12，显著高于Current 5/12；说明它可能对scene relation或region/phenomenon空间接地有价值，但这需要未来独立route contract，不能在本阶段外推为Production方案。

## 架构含义

1. Global task understanding 应使用小而严格的观察合同，不需要模型生成entity ID或多层scene graph。
2. Global Context按 `image + prompt` 一次缓存仍成立。
3. Single-candidate full-scene不应替换当前所有behavior local evidence。
4. attribute/fine appearance仍应保持isolated/local detail；scene relation与region可保留full-scene single marker作为后续研究假设。
5. 不支持Caption-first，不允许由本轮直接进入Production integration。
