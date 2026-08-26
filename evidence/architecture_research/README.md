# Visual Agent Architecture Research Evidence

本目录保存高准确率视觉架构研究的只读实验报告与原始结构化结果。

## 阶段

- `TASK_CONDITIONED_SCENE_CONTEXT_BENCHMARK_V1/`
  - 比较 Current、Global Structured Context、Context + Candidate Local、Full Marked Group。
  - 阶段结论：`SCENE_CONTEXT_ARCHITECTURE = NEEDS_MORE_EVIDENCE`。
- `SCENE_CONTEXT_GROUNDING_AND_CONTRACT_V1B/`
  - 验证精简 Global Context 合同及 Single-candidate Full-scene Grounding。
  - 阶段结论：精简合同接受；Single-candidate Full-scene 不接受为通用 behavior evidence。
- `SEMANTIC_IR_AND_ROUTE_CONTRACT_V1/`
  - 设计并离线验证 `instance / region` 与四类 constraint route 的最小 Semantic IR。
  - 阶段结论：`ACCEPTED / CLOSED`；Production integration 未授权。
- `DETECTOR_QUERY_AND_RECALL_V1/`
  - 分离验证 bounded lexical aliases 与 Grounding DINO Base 的 dense/small/overlap 实例枚举能力。
  - 阶段建议：bounded alias contract 可进入设计；Detector replacement benchmark 已具备证据基础。
- `CONTEXT_EVIDENCE_POLICY_HARDENING_V1/`
  - 在 25 个冻结 General RGB 案例上比较 Current、全量 Global Facts 与 uncertain-only lazy fallback。
  - 阶段裁决：attribute/behavior 保持 Current；relation 的 Global Facts 方向正面但证据不足，保留为待确认研究候选，Production 修改未授权。

所有 JSONL 均为模型调用或离线评分的原始逐条记录；Markdown 报告不替代这些原始数据。

Phase 3 归档包含冻结探针脚本与 28 张标框审查图，不包含 Production 代码或模型文件；审查图不替代由路径和 SHA-256 标识的原始输入。
