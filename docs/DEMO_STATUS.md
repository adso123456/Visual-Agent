# Visual Agent Developer Demo 状态

## 当前结论

`VISUAL_AGENT_V1 = CLOSED / ACCEPTED`

Visual Agent 已具备“开发者打开页面即可上传图片、输入自然语言、等待并查看结果”的完整 Full Chain：

Natural Language → DeepSeek Agent → Grounding DINO Base → configurable Cloud/Local VLM → Relation → SAM2 → deterministic Action

它验证了无需针对每个新视觉任务重新训练专项 Detector，也能通过通用视觉模型组合完成多类真实图片处理任务；这不代表完全替代专项训练或保证所有场景零样本完美识别。

v1 产品范围冻结为 **General RGB static-image visual execution**。F1～F4 fishing 继续作为有效的通用 RGB 研究/验收资产；P1～P4 pollution 仅为历史研究证据，不再代表产品业务需求，也不再作为模型或架构优化 Gate。

## Demo Acceptance Set v1

- Cases：15
- Full Chain：15/15
- PASS：13
- DEGRADED：1
- FAIL：1
- OUT_OF_SCOPE_ASSET：0

已确认：

- Agent Plan errors：0
- Detector usable-target miss：0
- VLM semantic error：0
- Relation error：0
- SAM error：0
- Action error：0
- Runtime error：0

已知限制：

1. 普通多人场景偶发 mixed candidate，可能造成额外错误目标。
2. VLM 对个别清晰但重叠的 candidate 可能返回 `uncertain`。
3. Full Chain 延迟不是实时级。
4. 不承诺密集人群 exhaustive recall。

## 支持范围

- 清晰、正常大小的单人属性
- 普通多人属性
- 明显行为
- 多个清晰目标
- 简单 `held_by_target`
- 普通遮挡
- Negative / 0-target

## Non-goals

- 密集人群 exhaustive recall
- 极小远距离目标
- 严重运动模糊
- 极端遮挡
- 图中所有实例一个不漏
- crowd counting、tracking、video
- 水面垃圾、漂浮塑料瓶、漂浮物和污染区域的水污染 RGB 业务识别
- Sentinel-2 / Landsat `.tif` 水质九参数反演；该方向属于未来独立 Remote Sensing Water Quality 项目

## Benchmark 定位

`benchmark/instance_quality_v1/` 是历史 Detector instance-quality 的 Research / Diagnostic Artifact。其 GT completeness 已知仍有待修订问题，当前不作为 Developer Demo readiness gate；Demo readiness 以正常清晰场景的端到端 Acceptance 结果为准。

后续 scene context、Semantic IR 和 Detector query/recall 实验同样作为历史研究证据保留：

- `SEMANTIC_IR_V1 = ACCEPTED RESEARCH CONTRACT / NOT SCHEDULED FOR V1 PRODUCTION INTEGRATION`
- `DETECTOR_QUERY_AND_RECALL_V1 = COMPLETED AS HISTORICAL RESEARCH / ACCEPTED / CLOSED / NO V1 PRODUCTION ACTION`
- `DETECTOR_REPLACEMENT_BENCHMARK = CANCELLED FOR V1 SCOPE`

Local VLM 已通过协议兼容、完整 Pipeline smoke、240 次执行与 232 条盲评比较，现已通过共享 VLM client/config seam 集成；DeepSeek Planner、Pipeline、Evidence、Detector、SAM、prompt 和 validator 合同保持不变。

最终冻结口径见 [`PROJECT_CLOSURE_V1.md`](PROJECT_CLOSURE_V1.md)。
