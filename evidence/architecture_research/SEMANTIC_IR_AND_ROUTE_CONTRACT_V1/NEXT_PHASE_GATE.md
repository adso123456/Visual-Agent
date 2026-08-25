# NEXT_PHASE_GATE

`SEMANTIC_IR_AND_ROUTE_CONTRACT_V1 = CHANGES_APPLIED / READY_FOR_REVIEW`

`PRODUCTION_MODIFICATION = NOT_AUTHORIZED`

`PHASE_3_DETECTOR_QUERY_AND_RECALL_V1 = NOT_STARTED`

Phase 2只完成候选合同和离线编译验证。需要人工审查以下事项后才能关闭：

1. `semantic_name`与`localization_target`分离是否足够清晰。
2. `instance / region`二分是否保持最小且无遗漏。
3. `object_relation / scene_relation`边界是否可审计。
4. relation direction是否始终满足`target --predicate--> reference`。
5. 6项predicate enum是否与validator、JSON Schema和全部fixtures一致。
6. P3的弱localization concept是否明确留给Phase 3，而没有污染Semantic IR。

审查前不得修改Production，也不得开始Detector query实现或region backend benchmark。
