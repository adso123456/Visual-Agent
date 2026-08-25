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
  - 阶段状态：`READY_FOR_REVIEW`；Production integration 未授权。

所有 JSONL 均为模型调用或离线评分的原始逐条记录；Markdown 报告不替代这些原始数据。

本次归档不包含 Production 代码、诊断脚本、模型文件或新增二进制证据。
