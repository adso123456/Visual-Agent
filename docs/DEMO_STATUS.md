# Visual Agent 当前项目状态

## 当前结论

```text
CANONICAL BRANCH = master
PRODUCTION BASELINE INCLUDED THROUGH = e44abeeac18d6e1e009928b70383b58a4c58068e
VISUAL_AGENT_V1 = CLOSED / ACCEPTED
PRODUCT SCOPE = General RGB static-image visual execution
```

当前 Full Chain：

```text
Natural Language
→ Local Qwen Planner
→ Grounding DINO Base
→ Local Qwen VLM / Relation
→ SAM 2.1 Base Plus
→ deterministic Action
→ Local Qwen Final Response
```

Planner、Final Response、VLM 和 Relation VLM 均使用本地 `qwen3.8:27b-mtp-q4_K_M`。Production 实现包含显式 transport retry、严格 contract correction、Final Response 产物解耦、hand-conditioned Detector 大图缩放与单候选 object-mediated behavior 的 uncertain fallback。

## 正式部署

| 项目 | 正式值 |
|---|---|
| Ollama endpoint | `http://192.168.250.9:11434/v1` |
| Agent / Planner | `qwen3.8:27b-mtp-q4_K_M` |
| Final Response | `qwen3.8:27b-mtp-q4_K_M` |
| VLM / Relation VLM | `qwen3.8:27b-mtp-q4_K_M` |
| GPU | 物理 GPU1 + GPU2 |
| `OLLAMA_NUM_PARALLEL` | `1` |
| `OLLAMA_KEEP_ALIVE` | `-1` |
| API job concurrency | `MAX_CONCURRENT_JOBS=1` |
| Cloud credentials | `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY` 均不需要 |

完整启动命令和应用侧环境变量见根目录 [`README.md`](../README.md#正式本地模型部署)。

## 当前验证证据

Merge 前在相同 Production commit 上完成：

- 完整 pytest：`166 passed`
- 正式 GPU1+GPU2 Ollama Runner：代表性端到端 smoke `5/5 PASS`
- 所有 smoke 均满足 Final Response `success` 且 `agent_response` 非空

| 场景 | 目标数 | Wall time | 结果 |
|---|---:|---:|---|
| 清晰钓鱼 | 1 | 40.6s | PASS |
| 双人钓鱼 | 1 | 58.2s | PASS |
| 雨伞抠图 | 1 | 26.8s | PASS |
| 红衣钓鱼负例 | 0 | 133.2s | PASS，正确拒绝 |
| 低光钓鱼 | 1 | 32.0s | PASS |

这些 smoke 是 merge 前工程回归，不是新的 Final Acceptance，也不会把历史 V4 FAIL 改写成 PASS。

## 已知限制

1. 当前安全延迟下限来自 candidate isolation 与串行 27B VLM calls。多候选负例可能需要每个候选分别执行 first pass 与 fallback，Full Chain 不是实时系统。
2. Aggregate fallback 已因跨候选身份污染否决；同 Runner 并发没有吞吐收益；轻量 VLM、降分辨率和压缩输出合同没有同时满足质量与收益要求。当前不再继续从既有 Pipeline 挤延迟。
3. 普通多人场景仍可能产生 mixed candidate；为保护身份归属，不能把多个候选合并成一份共享视觉判断。
4. VLM 对遮挡、低光或局部证据不足的候选可能返回 `uncertain`。单候选 fallback 仅覆盖“单候选 + 单 object-mediated behavior + first pass uncertain”，不会扩展到普通 attribute、多人其他分支或 Relation。
5. Final Response 连续空内容时，图片与 JSON 会保留，但该 unit 的正式 System Gate 仍应判失败，不能因为 `run_pipeline()` 正常返回而冒充成功。
6. 不承诺密集人群 exhaustive recall、极小远距离目标、严重运动模糊、极端遮挡或图中所有实例一个不漏。

## 支持范围

- 清晰、正常大小的单人属性
- 普通多人属性
- 明显行为
- 多个清晰目标
- 简单 `held_by_target`
- 普通遮挡
- Negative / 0-target
- `highlight`、`outline`、`blur_target`、`dim_background`、`cutout`

## Non-goals

- crowd counting、tracking、video
- 密集人群与极小目标的 exhaustive recall
- 水面垃圾、漂浮塑料瓶、漂浮物和污染区域的水污染 RGB 业务识别
- Sentinel-2 / Landsat `.tif` 水质九参数反演；该方向属于未来独立 Remote Sensing Water Quality 项目

## 验收与历史证据

历史 Final Acceptance V4 保持：

```text
GENERAL_RGB_FINAL_ACCEPTANCE_V4 = FAIL / CLOSED
```

其正式 evidence lineage 由 Git tag `archive/local-vlm-quality-evidence-v1` 固定。其他 diagnostic、acceptance 和实验历史同样通过 `archive/*` tags 保存，不应 merge 或 cherry-pick 回当前 Production。

`benchmark/instance_quality_v1/` 是历史 Detector instance-quality Research / Diagnostic Artifact；其 GT completeness 已知仍有待修订问题，不作为当前 Demo readiness gate。

最终产品范围冻结口径见 [`PROJECT_CLOSURE_V1.md`](PROJECT_CLOSURE_V1.md)。
