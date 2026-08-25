# SEMANTIC_IR_AND_ROUTE_CONTRACT_V1

## 状态

`SEMANTIC_IR_V1 = CHANGES_APPLIED / READY_FOR_REVIEW`

`PRODUCTION_INTEGRATION = NOT_AUTHORIZED`

## 当前代码事实

- Planner纯文本，不看图片。
- 当前`target_object`同时承担业务概念、基础可检测实体和DINO query。
- route只有`attribute / behavior / relation`；relation只支持`held_by_target`。
- 当前真实计划会把水面位置编为behavior、把水中编为attribute，并把region退化为water实例。
- Pipeline根据route直接选择证据与verifier，因此当前语义类型和执行策略仍有耦合。

## 推荐合同

选择“Target + Typed Constraints”最小合同：

- `concept_type`只允许`instance / region`。
- `semantic_name`保存用户真正要求的概念。
- instance必须有单一`localization_target.canonical_name`；它不是Detector query列表。
- region的`localization_target`在Phase 2必须为`null`。
- constraint route只允许`attribute / behavior / object_relation / scene_relation`。
- relation route必须包含`predicate + reference`；attribute/behavior禁止relation对象。
- 所有relation统一为`target --predicate--> reference`：target永远是语义主语，reference永远是语义宾语或场景上下文。
- V1 predicate冻结为`holding / riding / on_surface_of / floating_on / floating_in / under`，拒绝任意snake_case同义操作符。
- IR不包含full-scene、crop、evidence、threshold、model或backend字段。

## 8个冻结真实prompt编译结果

| ID | Concept type | Semantic target | Localization target | Route |
|---|---|---|---|---|
| F1 | instance | 人 | person | behavior |
| F2 | instance | 人 | person | object_relation: holding → 鱼竿 |
| F3 | instance | 桶 | bucket | none |
| F4 | instance | 人 | person | object_relation: holding → 鱼 |
| P1 | instance | 垃圾 | garbage item | scene_relation: on_surface_of → 水面 |
| P2 | instance | 塑料瓶 | bottle | scene_relation: floating_on → 水面 |
| P3 | instance | 漂浮物 | object | scene_relation: floating_in → 水体 |
| P4 | region | 污染区域 | null | scene_relation: on_surface_of → 水面 |

P3的`object`只表示当前最小localization concept仍弱；IR保留了`漂浮物 + floating_in(水体)`的完整业务语义。如何从它生成更好的bounded detector queries属于Phase 3，不在本合同中解决。

## 跨域反例验证

另外编译6个非fishing/pollution探针：红色汽车、奔跑的狗、骑自行车的人、桥下的船、道路积水区域、戴帽且跑步的人。它们覆盖普通实体、region、四类route和混合约束，全部通过同一个validator，没有领域关键词分支。

5个负向合同全部按预期拒绝：

- 顶层`use_full_scene`
- target内`detector_queries`
- target内`region_backend`
- region携带instance localization target
- 未支持的relation predicate `near`

## Relation direction invariant

旧Production名称`held_by_target`描述的是related object相对target的方向，不能直接进入统一IR。V1将F2/F4规范为：

- `person --holding--> fishing rod`
- `person --holding--> fish`

其他关系使用相同方向：

- `person --riding--> bicycle`
- `garbage item --on_surface_of--> water surface`
- `pollution region --on_surface_of--> water surface`
- `bottle --floating_on--> water surface`
- `floating object --floating_in--> water body`
- `boat --under--> bridge`

执行器不需要为某个predicate交换subject/object。自然语言细节保留在constraint `text`中；机器操作符只表达已冻结、已实现的稳定语义。

## Global Context边界

Global Context不进入Semantic IR，也不是最终裁决。它未来只能提供task-level observable facts；最终三态仍由route verifier依据对应证据产生。

## 未决定事项

- 不决定Detector query扩展、alias数量或阈值。
- 不决定region定位模型或SAM引导方式。
- 不决定scene_relation具体使用single-marker full scene还是其他证据组合。
- 不修改Planner tool schema、Pipeline或任何Production文件。

## 结论

最小IR能够不依赖fishing/pollution特例表达普通实体、行为、对象关系、场景关系和region。relation方向和6项predicate enum已按审查意见固定。合同适合重新人工审查；在审查通过前，不授权Production集成或Phase 3实现。
