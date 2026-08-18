# Visual Agent Developer Demo 状态

## 当前结论

`DEMO_READY_WITH_MINOR_LIMITATIONS`

Visual Agent 已具备“开发者打开页面即可上传图片、输入自然语言、等待并查看结果”的完整 Full Chain：

Natural Language → DeepSeek Agent → Grounding DINO Base → Qwen3-VL-Flash → Relation → SAM2 → deterministic Action

它验证了无需针对每个新视觉任务重新训练专项 Detector，也能通过通用视觉模型组合完成多类真实图片处理任务；这不代表完全替代专项训练或保证所有场景零样本完美识别。

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

## Benchmark 定位

`benchmark/instance_quality_v1/` 是历史 Detector instance-quality 的 Research / Diagnostic Artifact。其 GT completeness 已知仍有待修订问题，当前不作为 Developer Demo readiness gate；Demo readiness 以正常清晰场景的端到端 Acceptance 结果为准。
