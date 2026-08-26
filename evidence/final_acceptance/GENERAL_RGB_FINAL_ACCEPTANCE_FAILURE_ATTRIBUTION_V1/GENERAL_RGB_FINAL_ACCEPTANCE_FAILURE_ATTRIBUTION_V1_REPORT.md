# GENERAL_RGB_FINAL_ACCEPTANCE_FAILURE_ATTRIBUTION_V1

## 状态

`READ-ONLY ATTRIBUTION COMPLETE / REVIEW REQUIRED`

- 模型调用：0
- 重跑：0
- Production 修改：0
- 分析对象：F2/F4 三个 non-regression blocker、`challenge_001`、`challenge_004`

## 总结论

最终验收暴露了两个不同的根因边界，不能统一归因成“35% crop 不合适”。

1. F2/F4 的三个 Gate 回归全部发生在 Planner 将同一需求从历史 `behavior` 改为最终验收 `relation` 后。输入相同，相关 Production 代码 blob 完全相同，subject Detector 候选数量相同且 bbox 最大偏差仅 `0.01 px`。共同直接根因是 **Planner semantic-route variability**，随后分别触发三种 relation-path 脆弱点。
2. 两个 challenge 保持 `behavior` route。`challenge_001` 是低分辨率多人场景中的 **candidate overlap + identity anchoring 不足**；`challenge_004` 是 Detector 已找到老人后，35% crop 未保留长鱼竿与场景关系的 **context starvation**。

因此：这次失败既不是 Local VLM provider/protocol 问题，也不是一次简单扩大 crop 就能整体修复的问题。

## A. F2 / F4 non-regression

### 共同事实

- 历史执行 commit：`c2a784573dea313c3f80e714fbc4b7007563f9fa`
- 最终验收 commit：`4dac9cb3823e22e90ff3bb8157c6544c6c6b88fd`
- `deepseek_agent.py`、`pipeline.py`、`relations.py`、`vlm.py`、`evidence.py`、`qwen_protocol.py` 在两个 commit 间 blob 完全一致。
- 23 个重新盲审的有效输出中，14 个 plan payload 发生变化；route 变化包括 `behavior→relation` 7 条和 `relation→behavior` 2 条。
- 真正影响 F2/F4 Gate 的三条均为 `behavior→relation`。
- 当前 Planner prompt 明确要求“手持、拿着”生成 `held_by_target` relation；历史 `behavior` plan 虽通过结构 validator，但与该文字规则不一致。当前 validator 只验证结构，不能保证同一句自然语言稳定编译到同一 route。

| Case | 历史 → 最终 | Subject Detector | 最终失败机制 | 归因 |
|---|---|---|---|---|
| F2::fishing_001 | TN → FP；behavior → relation | 1 → 1，bbox 最大差 0.01 px | `fishing rod` grounding 实际落在渔获附近，relation verifier 错判持有，最终把人物和鱼一起描边 | Planner route variability；related grounding FP + relation false assignment |
| F2::fishing_024 | PASS → FAIL；behavior → relation | 1 → 1，bbox 最大差 0.01 px | R1/R4 被 verifier 明确描述为同一根鱼竿的不同部分，但 resolver 把两个 satisfied binding 计为冲突，输出 `binding_conflict` | Planner route variability；related duplicate consolidation 缺失 |
| F4::fishing_017 | PASS → FAIL；behavior → relation | 1 → 1，bbox 最大差 0.01 px | Detector 返回桶内 4 个 fish，未返回手中小鱼；四个 binding 全为 not_satisfied | Planner route variability；relation route 的 related-object recall 缺口 |

`F2::fishing_027` 从 DEGRADED 变为 PASS，是改善，不是 blocker。

### 裁决

三条下降不是 Production 代码 regression，也不是 subject Detector candidate variation；它们是相同代码、相同输入下的 Planner route 非确定性暴露出的 relation-path 结构脆弱性。不能只归因成 Qwen 推理随机，也不能据此直接重构整个 relation architecture。

## B. challenge_001

- Detector 正常返回两个人物候选，不是漏检。
- 原图仅 `235×156`。
- A 的 35% crop 为 `69×126`，覆盖相邻 B bbox 的 `73.37%`。
- B 的 35% crop 为 `86×156`，覆盖相邻 A bbox 的 `77.04%`。
- 证据只用当前 SAM mask 的红色 contour 标识身份；在低分辨率、候选高度重叠且人物服饰相近时，该锚点不足。
- A 的最终 evidence 直接把白帽候选描述成“戴红帽”，说明邻近候选语义已经跨入当前候选判断。
- Context Hardening 的独立 Arm A 也得到 A/B 均 `satisfied`，说明该失败可复现，不是本次单次协议偶然。

裁决：`candidate overlap + insufficient identity anchoring`。主要不是 Detector，不是 protocol，也不能靠 candidate-agnostic Global Facts 修复。

## C. challenge_004

- Detector 已返回老人 A 与儿童 B，因此不是 Detector candidate failure。
- 老人 A 的 35% crop 为 `[445,20,571,398]`，尺寸 `126×378`；长鱼竿主体向画面左侧延伸，大部分不在 crop 内。
- 该 crop 同时覆盖儿童 bbox 的 `74.36%`，保留了邻人但丢失了关键长程交互对象。
- 最终 VLM 对老人给出 `uncertain`，理由明确是“未见鱼竿、鱼线或水域”。Context Hardening Arm A 对同一老人也为 `uncertain`。
- 儿童被判 `not_satisfied`，没有 false assignment；Gate 失败仅因明确老人未保留。

裁决：主因是 `35% behavior context starvation`，候选重叠是次因；不是 Detector failure。

## 最小根因边界

后续修复合同至少要分别处理：

1. 同一显式手持语义必须稳定编译到同一路由，不能让 Planner 在 `behavior` / `relation` 间漂移。
2. relation route 若保留，需明确处理 related duplicate、related recall 与 false grounding；三者不是一个问题。
3. behavior evidence 必须同时保持 candidate identity anchoring 与必要的长程交互上下文；单独扩大固定 margin 会加剧 `challenge_001` 的跨候选污染。

本阶段不选择实现方案，不授权 Production 修改。下一步应先冻结一个最小 remediation contract，再做 targeted regression；上一轮 140 结果保持不可变。
