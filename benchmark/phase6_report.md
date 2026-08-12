# Phase 6 DeepSeek Agent Brain 对照报告

- 模型：`deepseek-v4-flash`
- 数据集：与 Phase 5 完全相同的 15 Core + 5 Challenge

| Metric | Phase 5 | Phase 6 | Delta |
|---|---:|---:|---:|
| Core pass | 86.67% | 93.33% | +6.66% |
| target_object | 86.67% | 100.00% | +13.33% |
| constraints | 86.67% | 100.00% | +13.33% |
| action | 100.00% | 100.00% | +0.00% |
| target selection | 100.00% | 100.00% | +0.00% |
| negative | 100.00% | 100.00% | +0.00% |
| segmentation | 91.67% | 91.67% | +0.00% |
| action visual | 100.00% | 100.00% | +0.00% |

## 重点结果

- core_004：PLAN 已修复；E2E 仍因 SAM 人体 mask 不包含雨伞而失败。
- core_015：PLAN 已修复，target_object=person、constraints=[儿童]，两名儿童均正确模糊。
- challenge_005：仍只产生并保留 3 个前景红衣目标，密集小目标召回问题仍属 GROUNDING。

## Repeatability

- `core_006`：3 次，完全一致
- `core_011`：3 次，完全一致
- `core_012`：3 次，完全一致

## Agent 统计

- Planner contract retry：0/20
- DeepSeek plan latency：{'min': 0.896, 'median': 1.082, 'max': 1.375}
- DeepSeek final latency：{'min': 0.548, 'median': 0.907, 'max': 1.442}

Phase 5 原始产物未覆盖；DINO、Qwen verifier、SAM2 和 Action 实现均未修改。
