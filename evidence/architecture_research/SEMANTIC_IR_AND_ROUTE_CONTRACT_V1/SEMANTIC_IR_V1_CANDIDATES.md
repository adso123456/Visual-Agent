# Semantic IR V1 候选合同

## Candidate A — Target + Typed Constraints（选择）

最小结构：

```json
{
  "ir_version": "semantic_ir.v1",
  "source_prompt": {"id": "...", "text": "..."},
  "target": {
    "concept_type": "instance|region",
    "semantic_name": "用户真正要求的概念",
    "localization_target": {"canonical_name": "basic entity"}
  },
  "constraints": [
    {"id": "c1", "text": "原子约束", "route": "attribute|behavior"},
    {
      "id": "c2",
      "text": "原子关系约束",
      "route": "object_relation|scene_relation",
      "relation": {
        "predicate": "holding|riding|on_surface_of|floating_on|floating_in|under",
        "reference": {"concept_type": "instance|region", "semantic_name": "...", "localization_target": null}
      }
    }
  ],
  "action": {"type": "box|outline|highlight|..."}
}
```

优点：保留用户语义、目标类型、可定位基础实体和关系reference；没有执行证据、Detector query、阈值或backend字段。约束顺序和原文可审计。复杂度足够表达当前真实任务，但没有引入通用scene graph。

V1冻结以下relation predicate：`holding / riding / on_surface_of / floating_on / floating_in / under`。不允许Planner生成任意snake_case操作符；未实现关系必须明确拒绝，未来通过版本升级扩展enum。

所有relation constraint都遵守同一方向不变量：target始终是语义主语，reference始终是语义宾语或场景上下文，即`target --predicate--> reference`。

## Candidate B — Entity/Region Graph（拒绝）

为所有实体、区域和关系建立node ID与edge数组。

拒绝原因：Phase 1已经观察到全局结构中三个持竿关系折叠到同一实体ID；Phase 1B又证明去掉entity/region/relation多层对象后contract failure从3降到0。Planner只看文本，不需要为尚未观察到的视觉实例创建图身份。

## Candidate C — Execution Plan Shaped IR（拒绝）

在语义计划中加入`use_full_scene`、`evidence_route`、`detector_queries`、`threshold`或`region_backend`。

拒绝原因：这些字段描述系统如何执行，不描述用户要什么；会把Phase 1的实验策略、Phase 3的query策略和未来region backend提前固化进语义合同。

## 冻结选择

选择Candidate A。`localization_target`是基础可定位概念，不是Detector请求列表；`detector_queries`由Phase 3根据该概念另行编译。region的`localization_target`在Phase 2固定为`null`，避免暗中决定region backend。relation predicate采用版本化最小enum，不采用开放snake_case。
