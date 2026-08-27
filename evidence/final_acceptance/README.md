# Visual Agent Final Acceptance Evidence

本目录保存最终 Product Acceptance 的冻结合同、执行原始结果、人工评分与裁决。Architecture Research 的历史实验仍保存在 `evidence/architecture_research/`，不得替代最终 Production 验收。

## Stages

- `GENERAL_RGB_FINAL_ACCEPTANCE_V1/`
  - 当前状态：`FAIL`。
  - Production baseline：`master@4dac9cb3823e22e90ff3bb8157c6544c6c6b88fd`。
  - 140/140 Pipeline success；System 与 Core Gate 通过，Real-world Vision 与 Challenge Safety Gate 未通过。
  - Remote Sensing Water Quality 继续保持 `BLOCKED`。
- `GENERAL_RGB_FINAL_ACCEPTANCE_FAILURE_ATTRIBUTION_V1/`
  - 当前状态：`READ-ONLY ATTRIBUTION COMPLETE / REVIEW REQUIRED`。
  - 未调用模型、未补跑、未修改 Production。
  - 固化 F2/F4 三个 non-regression blocker 与 `challenge_001`、`challenge_004` 的逐层根因。
- `GENERAL_RGB_FINAL_ACCEPTANCE_REMEDIATION_V1/`
  - 当前状态：`CONTRACT FROZEN / TARGETED GATES NOT PASSED / EXECUTION CONTRACT DEVIATION DOCUMENTED`。
  - 冻结合同：`919fcf2`；implementation：`1960505b`（R1/R2/R3 + planner seam，本地 qwen3.8:27b 规划器/VLM）；seam 安全收口 `be54f3c`。
  - Targeted Gates 证据见 `targeted_gates/`；总裁决、失败逐案证据与远程审查结论见 `targeted_gates/GENERAL_RGB_FINAL_ACCEPTANCE_REMEDIATION_V1_GATES_REPORT.md`。
  - 合同执行偏差（failed_execution_replacement 违规补跑）已在该报告记录，原始 execution evidence 未改动；PASS 侧可靠性指标不作合同合规口径。
  - 失败归因对下一轮 remediation design 有效；Production 修改仍未授权（不 merge、不建 V2 批次）；REMOTE_SENSING_WATER_QUALITY = BLOCKED。
- `GENERAL_RGB_R3_CANDIDATE_IDENTITY_REMEDIATION_V1/`
  - 当前状态：`CONTRACT FROZEN / BUILDER CODE REVIEW APPROVED / HARNESS AUDIT FIX IMPLEMENTED / NARROW RE-REVIEW REQUIRED`。
  - Builder implementation：`general-rgb-r3-candidate-identity-benchmark-v1@0b32695d`；实现与离线测试记录见 `BENCHMARK_EVIDENCE_BUILDER_IMPLEMENTATION_REPORT.md`。
  - Harness implementation：同分支 `9a9e8f7`；实现与 stub/mock 测试记录见 `MODEL_EXECUTION_HARNESS_IMPLEMENTATION_REPORT.md`。
  - 4 个 harness audit Blocking 的修复：`b35bde5` + review-lock `22b2257`；见 `MODEL_EXECUTION_HARNESS_AUDIT_FIX_REPORT.md`。
  - 只比较 current R3、target-anchored local、target-anchored local + fallback 三种 candidate-specific behavior evidence；不使用 Global Facts。
  - 冻结 3 个 challenge（各 5 次）与既有 6 条 F1 behavior 子集；固定 bbox、共享 SAM mask cache、A/B/C 顺序与 failure-retention 规则。
  - 当前只读设计；Production code、模型执行、merge、R2.2/R2.3 与 Final Acceptance V2 均未授权。
