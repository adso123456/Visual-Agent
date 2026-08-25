# Scene Context Schema Candidates

本文件只冻结 Phase 1 benchmark 候选，不是 Production contract。

## S1 — Minimal fact list

```json
{
  "task_relevant_facts": [
    {"fact": "可观察事实", "confidence": "observed|uncertain"}
  ],
  "task_status": "satisfied|not_satisfied|uncertain",
  "evidence": "简短证据"
}
```

优点是小、易验证；缺点是缺少实体、区域和关系 identity，容易把 global fact 错归候选。

## S2 — Typed task-conditioned scene context（本轮 Method B 采用）

```json
{
  "case_id": "...",
  "task_relevant_facts": [
    {"fact": "可观察事实", "confidence": "observed|uncertain"}
  ],
  "scene_entities": [
    {
      "id": "E1",
      "type": "可见实体类型",
      "observable_state": "当前可见状态",
      "task_relevance": "与任务的直接关系"
    }
  ],
  "scene_regions": [
    {"id": "R1", "type": "可见区域类型", "description": "区域可见状态"}
  ],
  "task_relevant_relations": [
    {
      "subject": "E1",
      "relation": "可观察关系",
      "object_or_region": "E2|R1",
      "confidence": "observed|uncertain"
    }
  ],
  "task_status": "satisfied|not_satisfied|uncertain",
  "evidence": "简短证据"
}
```

选择原因：能区分 task fact、entity、region 与 relation，仍不要求自由 caption、bbox、mask 或 exhaustive instance enumeration。字符串 relation/type 只用于 benchmark 观察，不作为正式 enum。

## S3 — Candidate-neutral scene graph

```json
{
  "nodes": [{"id": "N1", "kind": "entity|region", "observable_state": "..."}],
  "edges": [{"source": "N1", "relation": "...", "target": "N2"}],
  "task_query_result": "satisfied|not_satisfied|uncertain"
}
```

优点是统一；缺点是 Phase 1 样本下结构成本较高，且容易诱导模型生成伪精确 scene graph。本轮不执行。

## 共同约束

- task-conditioned，不生成长篇 caption。
- 只写可观察事实；不得推断不可见状态。
- 不产生 bbox/mask，不替代 Detector/SAM。
- 不使用浮点 confidence。
- animal/rock/plant 位于水中不自动等于垃圾或污染。
- task status 只表示目标语义是否存在，不检查编辑动作是否已执行。
