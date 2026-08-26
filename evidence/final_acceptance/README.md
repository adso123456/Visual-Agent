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
