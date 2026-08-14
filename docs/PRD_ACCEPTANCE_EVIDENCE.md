# Visual Agent Demo v1 产品验收证据（PRD §29 逐条对照）

> 本文档把 PRD §29 的十条最终验收定义映射到当前仓库的具体实现与证据。
> 证据以代码路径、测试、脚本和已生成产物为准；标注「待人工」的项表示需要
> 人工确认或外部 API Key 才能最终完成，不属于代码缺陷。

## 1. 用户能只通过自然语言完成多种不同图片操作任务

- 完整链路：`visual_agent/deepseek_agent.py`（DeepSeek Planner）→ `grounding.py`
  （本地 Grounding DINO Base）→ `vlm.py`（Qwen3-VL 语义验证）→ `relations.py`
  （held_by_target）→ `segmentation.py`（SAM2.1）→ `actions.py`（确定性 OpenCV）。
- 五种操作全部实现：highlight / outline / blur_target / dim_background / cutout
  （`visual_agent/actions.py`，已逐一用 vision 复核输出）。
- Segmentation（§23）：SAM mask 明显优于纯 bbox —— 对比图见
  `docs/SAM_VS_BBOX_EVIDENCE.md`（outline 与 dim_background 各一对并排图，
  vision 复核确认右侧 mask 轮廓严格贴合人物、无背景溢出）。
- Demo UI（`demo_ui/`）提供图片输入 + 自然语言指令 + 执行按钮 + 结果图片。
- 可运行示例：`python demo_showcase.py`（本地栈，无 Key）。

## 2. 新任务不要求重新训练一个专项 Detector

- Detector 只接收 `image + canonical target_object`（PRD §9），开放词汇
  Grounding DINO Base 无需为“红衣服的人”“钓鱼的人”等分别训练。
- 职责边界由 `VISUAL_AGENT_PERCEPTION_CONTRACT_V1.0.md` 冻结（§3/§4）。

## 3. Agent、Detector、VLM、Relation、SAM、Action 职责边界清晰且可独立替换

- 每个组件是独立模块，仅通过 `pipeline.py` 的 `run_pipeline` 编排；
  契约文档明确禁止下游修补上游（§2/§20）。
- `models.py` 提供进程内复用注册表，Detector/Segmenter 可独立替换。

## 4. 系统能够处理单目标、多目标、零目标与 uncertain

- 多目标：`commons_red_shirts.jpg` 描边得到 4 个目标（vision 复核确认多人描边）。
- 零目标（Negative Case）：全链路结果 `result_094/112/113/126` 等均为 0 targets
  0 verified_subjects，返回“未找到满足条件的目标”（PRD §16）。
- uncertain：`vlm.py` 三态协议（satisfied/not_satisfied/uncertain）为正式状态，
  不进性强制归并（PRD §17）。

## 5. Detector/VLM/SAM 的失败能够被明确归因

- 结果 JSON 区分：Detector miss（candidates=0）、Mixed candidate（MIXED_INSTANCE）、
  VLM semantic failure、Relation failure（binding_*）、Segmentation failure、
  No matching target、Uncertain（PRD §23 Failure Transparency）。
- 基准评测将候选细分为六类 + 4 档 completeness（`schema.py`）。

## 6. 通用评测体系可以公平比较不同本地 Detector

- `benchmark/instance_quality_v1/`：24 Test + 5 Calibration，八类场景，
  manifest 校验（SHA/尺寸/split 隔离）、frozen GT、官方评测脚本
  `scripts/evaluate.py`，输出 `reports/grounding_dino_base_v1.json/.md`。
- 基线条目：Instance Recall 0.733 / Purity 0.660 / Mixed 0.093 / Dup 0.072。
- 契约要求：同一 GT/同一 VLM/同一 SAM 下 A/B，禁止 Tile/SAHI/下游修补（§13）。

## 7. 核心 Demo 回归稳定

- 回归体系：`benchmark/` 下 phase6~11 测试脚本 + `instance_quality_v1/tests`
  （当前全部通过），`run_benchmark.py` 冻结结果基线，`measure_latency.py` 计时。
- `benchmark/results/` 保存冻结 case 副本，可回归比对。

## 8. 不依赖案例特定的隐藏规则或大量 if/else 补丁

- 无 per-case 分支：pipeline 仅按 plan 契约执行；失败归因是结构化状态而非补丁。
- 历史结论（契约 §20）：Phase 9/10 尝试的 VLM 去重、SAM consolidation 均因
  违反职责边界被终止，未进入生产。

## 9. 不通过下游模型掩盖上游感知错误

- 契约 §2/§20 冻结：Detector 错误 ≠ VLM 去重 ≠ SAM overlap 修复 ≠ 几何硬修复。
- Detector 候选质量由 Detector Benchmark 独立度量（见 §6）。

## 10. 具备向 Visual Reference + Few-shot Concept 扩展的架构空间

- 契约 §17 已定义未来拆分为 Zero-shot Text Benchmark 与 Few-shot Visual Prompt
  Benchmark；PRD §26 定义 Zero-shot / Visual Reference / Adaptive 三种模式。
- Agent plan 结构预留 `visual_reference` 字段扩展位（PRD §8）。

## 当前待人工 / 待外部能力项

| 项 | 状态 | 说明 |
|---|---|---|
| Candidate Review 人工确认 | 草稿已就绪 | `reviews/grounding_dino_base.json` 为
  assistant_vision_draft，需在 annotation_tool 复核后改 reviewed_by=human |
| Downstream Usability probe | 未运行 | 需 DASHSCOPE_API_KEY 的语义探针 |
| 全链路（DeepSeek+Qwen）回归 | 需要 API Key | 本地栈（DINO+SAM2+Action）已验证 |

## 一句话叙事（PRD §27）

> Visual Agent 是一个自然语言驱动的通用视觉执行系统。它利用通用视觉基础模型
> 和 Agent，把用户的视觉意图动态编译成定位、语义验证、关系判断、精确分割与
> 图片操作，从而减少针对每一个新业务需求重新收集数据、标注和训练专项模型的
> 需求。
