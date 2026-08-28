# GENERAL_RGB_F4_SMALL_HELD_OBJECT_LOCALIZATION_V1 — Gate L 执行报告

## 状态

- `GATE_L_DETECTOR_EXECUTION = COMPLETE / PASS`
- `LOCALIZATION_MECHANISM = FOUND`
- `RELATION_VLM_CALLS = 0`
- `GATE_R = NOT AUTHORIZED / NOT STARTED`
- `PRODUCTION_MODIFICATION = 0`

## 冻结输入

- Case：`F4::fishing_017.jpeg`
- Evidence contract：`local-vlm-quality-evidence-v1@cad109b37b119b159644967a10b6fb143d229432`
- Benchmark runner：`general-rgb-f4-small-held-object-localization-v1@984d882dd3f9246403cb10a0be4d738840511963`
- Production reference：`be54f3c89171d8b16f53c82397e9f468fb4b4c97`
- Detector：`IDEA-Research/grounding-dino-base`
- Query：`fish`；Arm C hand discovery 使用冻结的 `hand`
- Threshold：`0.30`
- Reference bbox：`[820, 690, 945, 780]`
- Reference center：`[885, 735]`

Gate L 的机械成功条件保持冻结值：候选框必须同时包含 reference center、候选中心位于 reference bbox 内、且与 reference bbox 的 IoU `>= 0.10`。

## 执行结果

| Arm | Detector calls | Target localized | 最佳有效候选 | Confidence | IoU |
|---|---:|---|---|---:|---:|
| A — current base view | 1 | 否 | 无 | — | 0 |
| B — fixed overlapping tiles | 4 | 是 | `[814.11, 688.52, 963.71, 799.0]` | 0.5126 | 0.680671 |
| C — deterministic hand-conditioned view | 3 | 是 | `[815.61, 689.04, 964.03, 798.15]` | 0.4539 | 0.694697 |

总 Detector 调用数为 8。A 仍只定位到桶内/桶边鱼；B 与 C 都把 subject A 手中目标小鱼带入 candidate universe。冻结 Gate L 因此得到：

`B_OR_C_SUCCESS = true`

`DECISION = LOCALIZATION_MECHANISM_FOUND`

## 可靠性与执行边界

- Terminal status：`success`
- Detector final failure：0
- VLM/provider/protocol/validator call：0
- Relation VLM：未调用
- 失败替换/补跑：0
- Detector、query、threshold、A/B/C 视图与 reference 坐标均未在执行中调整

第一次 shell 命令使用脚本文件路径启动，在 Python import 阶段因 `visual_agent` 不在模块搜索路径而退出；该尝试发生于 preflight 和 Detector 加载之前，Detector 调用为 0，且没有创建 Gate L 输出目录。随后使用同一已审 runner 的等价模块入口 `python -m benchmark.f4_small_held_object_localization_v1.run_gate_l` 完成唯一一次 Gate L Detector 执行。此启动事实保留在报告中，不计为模型失败或 Detector 补跑。

## 证据

- `gate_l_execution/preflight.json`：冻结合同、selection、runner 和禁止 Relation VLM 的执行前收据。
- `gate_l_execution/raw_result.json`：所有原始与原图坐标系 detection、置信度、耗时和机械判定。
- `gate_l_execution/artifact_manifest.json`：本次输出的逐文件 SHA-256 与字节数。
- `gate_l_execution/overlay.png`：reference 与各 Arm detection 的可视化叠加。
- `gate_l_execution/views/`：A/B/C 实际 Detector 输入视图，保持生成字节。

## 裁决边界

Gate L 只证明：在不换 Detector、不降 threshold、不改 query 的情况下，改变确定性观察尺度可以把 `F4::fishing_017` 手中小鱼定位出来。

本报告不证明 held relation binding 已通过，也不授权 Relation VLM、Production 修改、merge 或 General RGB Final Acceptance V2。下一步如需 Gate R，必须单独授权，并将成功定位的 candidate 原样送入现有 held verifier。
