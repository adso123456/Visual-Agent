# Visual Agent Demo v1 产品验收证据（PRD §29 逐条对照）

> 本文档把 PRD §29 的十条最终验收定义映射到当前仓库的具体实现与证据。
> 证据以代码路径、测试、脚本和已生成产物为准；标注「待人工」的项表示需要
> 人工确认或外部 API Key 才能最终完成，不属于代码缺陷。
>
> ## 验证状态口径（三态）
>
> 每条证据必须标注以下三态之一，不得混用：
>
> - `CURRENT RUN VERIFIED` —— 在可用环境中实际重新运行并验证。
> - `HISTORICAL VERIFIED` —— 仓库中既有的历史运行结果（含早期全链路结果），
>   作为历史证据保留，不代表最新环境重新运行过。
> - `NOT RUN` —— 代码/工具已就绪但因缺 Key 或需人工尚未运行。
>
> 状态说明：本环境已配置 DASHSCOPE_API_KEY（用户级）与 DEEPSEEK_API_KEY
> （系统级）。2026-08-14 已在本环境**重新跑通完整链路回归**（见 §1/§4），
> 该回归结果存放在 `images/output_images/full_chain_regression/`。

## 1. 用户能只通过自然语言完成多种不同图片操作任务

- `CURRENT RUN VERIFIED`（完整链路回归，2026-08-14）：
  `images/output_images/full_chain_regression/result_001.json`（描边，4 目标）、
  `result_002.json`（雨伞抠图，关系组合目标）、`result_003.json`（钓鱼高亮，
  3 候选经 Qwen 过滤为 1 目标）。vision 复核输出图确认：4 红衣人描边、
  人+伞透明抠图、仅 1 名钓鱼者高亮。
- `CURRENT RUN VERIFIED`（本地栈）：五种确定性操作 highlight / outline /
  blur_target / dim_background / cutout（`visual_agent/actions.py`）逐一用
  vision 复核输出正确。
- `CURRENT RUN VERIFIED`：Demo UI（`demo_ui/`）图片输入 + 自然语言指令 +
  执行按钮 + 结果图片 + 调试面板，本地栈模式端到端跑通（`demo_showcase.py`）。
- `CURRENT RUN VERIFIED`：Segmentation（§23）SAM mask 优于纯 bbox —— 对比图
  `docs/SAM_VS_BBOX_EVIDENCE.md`，vision 复核确认 mask 轮廓严格贴合人物。
- 完整链路代码：`visual_agent/deepseek_agent.py`（DeepSeek Planner）→
  `grounding.py`（DINO）→ `vlm.py`（Qwen3-VL）→ `relations.py` →
  `segmentation.py` → `actions.py`。

## 2. 新任务不要求重新训练一个专项 Detector

- `CURRENT RUN VERIFIED`：Detector 只接收 `image + canonical target_object`（PRD §9），
  开放词汇 Grounding DINO Base 无需为“红衣服的人”“钓鱼的人”等分别训练。
- 职责边界由 `VISUAL_AGENT_PERCEPTION_CONTRACT_V1.0.md` 冻结（§3/§4）。

## 3. Agent、Detector、VLM、Relation、SAM、Action 职责边界清晰且可独立替换

- 每个组件是独立模块，仅通过 `pipeline.py` 的 `run_pipeline` 编排；
  契约文档明确禁止下游修补上游（§2/§20）。
- `models.py` 提供进程内复用注册表，Detector/Segmenter 可独立替换。

## 4. 系统能够处理单目标、多目标、零目标与 uncertain

- `CURRENT RUN VERIFIED`（完整链路回归，2026-08-14）：
  多目标描边 4 目标（result_001）；语义过滤 3→1（result_003）。
- `CURRENT RUN VERIFIED`（本地栈）：多目标 `commons_red_shirts.jpg` 描边 4 目标
  （vision 复核确认多人描边）。
- `HISTORICAL VERIFIED`：零目标（Negative Case）全链路结果 `result_094/112/113/126`
  等 0 targets / 0 verified_subjects（PRD §16）。
- `CURRENT RUN VERIFIED`（协议层）：`vlm.py` 三态协议（satisfied/not_satisfied/
  uncertain）为正式状态，不强制归并（PRD §17）；单测覆盖校验逻辑。

## 5. Detector/VLM/SAM 的失败能够被明确归因

- 结果 JSON 区分：Detector miss、Mixed candidate、VLM semantic failure、
  Relation failure（binding_*）、Segmentation failure、No matching target、
  Uncertain（PRD §23 Failure Transparency）。
- 基准评测将候选细分为六类 + 3 档 completeness（`schema.py`）。

## 6. 通用评测体系可以公平比较不同本地 Detector

- `CURRENT RUN VERIFIED`（评测管线）：`benchmark/instance_quality_v1/` 24 Test +
  5 Calibration，八类场景，manifest 校验（SHA/尺寸/split 隔离）、frozen GT、
  官方评测脚本 `scripts/evaluate.py`。
- `CURRENT RUN VERIFIED`：Human Candidate Review 122/122 COMPLETE；用户明确接受
  Codex 逐候选视觉复核作为最终人工确认。Grounding DINO Base Baseline v1 已冻结：
  Recall 0.744186 / Purity 0.752941 / Mixed 0.141176 / Duplicate 0.058824 / False 0。
- `CURRENT RUN VERIFIED`：Downstream Usability 使用冻结的预声明语义约束，
  不是 generic object recognizability。结果为 43 VLM Correct / 4 VLM Semantic
  Limit / 75 Detector Downstream Unusable，正式指标 0.914894；artifact 同时绑定
  semantic spec、Frozen GT、raw candidates 和 human review SHA-256。
- 契约要求：同一 GT/同一 VLM/同一 SAM 下 A/B，禁止 Tile/SAHI/下游修补（§13）。

## 7. 核心 Demo 回归稳定

- `CURRENT RUN VERIFIED`：`instance_quality_v1/tests` 全部通过；
  `benchmark/test_phase10_geometry.py`、`test_phase11_instance_contract.py` PASS。
- `HISTORICAL VERIFIED`：`benchmark/results/` 保存历史冻结 case 副本与 phase6~11
  报告；`measure_latency.py` 历史延迟报告在 `benchmark/latency_report*.json`。

## 8. 不依赖案例特定的隐藏规则或大量 if/else 补丁

- 无 per-case 分支：pipeline 仅按 plan 契约执行；失败归因是结构化状态而非补丁。
- 历史结论（契约 §20）：Phase 9/10 尝试的 VLM 去重、SAM consolidation 均因
  违反职责边界被终止，未进入生产。

## 9. 不通过下游模型掩盖上游感知错误

- 契约 §2/§20 冻结：Detector 错误 ≠ VLM 去重 ≠ SAM overlap 修复 ≠ 几何硬修复。
- Detector 候选质量由已冻结的 Detector Benchmark 独立度量（见 §6）。

## 10. 具备向 Visual Reference + Few-shot Concept 扩展的架构空间

- 契约 §17 已定义未来拆分为 Zero-shot Text Benchmark 与 Few-shot Visual Prompt
  Benchmark；PRD §26 定义 Zero-shot / Visual Reference / Adaptive 三种模式。
- Agent plan 结构预留 `visual_reference` 字段扩展位（PRD §8）。

## 当前状态汇总（正式口径）

| 项 | 正式状态 | 说明 |
|---|---|---|
| Demo UI | 功能实现完成，待远端代码核对 | 已 push（master=3ea2a95） |
| PRD Local Stack Evidence | 基本完成 | 本地栈 + vision 复核 + 单测 |
| 完整链路回归 | CURRENT RUN VERIFIED（2026-08-14） |
  images/output_images/full_chain_regression/（描边4/抠图1/高亮3→1） |
| Candidate Review | COMPLETE / HUMAN CONFIRMED | 122/122；provenance 已固化 |
| Grounding DINO Base metrics | FROZEN / OFFICIAL | Detector-only 七项正式基线 |
| Downstream Usability | CURRENT RUN VERIFIED | 预声明语义约束，0.914894 |
| Phase 12 | COMPLETE | Grounding DINO Base Baseline v1 已冻结 |
| Local Detector A/B readiness | YES | 可在相同冻结契约下启动 |
| PRD overall acceptance | NOT YET | 见上表各待办 |

## 一句话叙事（PRD §27）

> Visual Agent 是一个自然语言驱动的通用视觉执行系统。它利用通用视觉基础模型
> 和 Agent，把用户的视觉意图动态编译成定位、语义验证、关系判断、精确分割与
> 图片操作，从而减少针对每一个新业务需求重新收集数据、标注和训练专项模型的
> 需求。
