# Phase 7 关系组合目标分割报告

- Agent Brain：`deepseek-v4-pro`
- Relation：`held_by_target` only

| Metric | Phase 6 | Phase 7 | Delta |
|---|---:|---:|---:|
| Core pass | 93.33% | 100.00% | +6.67% |
| target_object | 100.00% | 100.00% | +0.00% |
| constraints | 100.00% | 100.00% | +0.00% |
| action | 100.00% | 100.00% | +0.00% |
| target selection | 100.00% | 100.00% | +0.00% |
| negative | 100.00% | 100.00% | +0.00% |
| segmentation | 91.67% | 100.00% | +8.33% |
| action visual | 100.00% | 100.00% | +0.00% |

## Gate

- core_003：person + umbrella composite outline，PASS。
- core_004：关系绑定、双组件批量 SAM、mask OR、composite cutout 与 alpha，PASS。
- core_014：零 verified subject，关系链跳过且未制造 target，PASS。
- Relation Binding：2/2。

## Repeatability

- `core_004`：3 次，业务签名一致；label 一致。
- `core_006`：3 次，业务签名一致；仅 label 文案波动：['钓鱼的人', '正在钓鱼的人', '钓鱼的人']。
- `core_011`：3 次，业务签名一致；仅 label 文案波动：['戴帽子的人', '人', '戴帽子的人']。
- `core_012`：3 次，业务签名一致；label 一致。

## 已知问题

- challenge_004 首次 Qwen verifier 返回错误 JSON 形状并被严格校验拒绝；同输入重跑成功，首次错误已保留。
- challenge_005 仍为密集小目标 Grounding Recall 失败，本阶段未处理。
- Windows 中文路径问题仍未处理。

DINO、原 Qwen verifier、SAM2、Action、Renderer 均未修改；未加入视频或 UI。
