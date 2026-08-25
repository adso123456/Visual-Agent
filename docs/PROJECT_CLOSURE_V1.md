# Visual Agent v1 项目收尾冻结

## 最终状态

```text
VISUAL_AGENT_V1
= CLOSED / ACCEPTED

PRODUCT SCOPE
= General RGB static-image visual execution
```

Visual Agent v1 已完成自然语言任务编译、开放词汇目标定位、VLM 语义验证、简单关系验证、SAM2 分割与确定性图片操作的完整 Developer Demo。支持的操作为 `highlight`、`outline`、`blur_target`、`dim_background` 和 `cutout`。

## 正式范围

```text
General RGB Vision
├─ 自然语言任务编译
├─ Grounding DINO
├─ Cloud / Local VLM semantic verification
├─ simple relation
├─ SAM2
└─ highlight / outline / blur / dim / cutout
```

- F1～F4 fishing 是有效的 General RGB 研究/验收资产。
- v1 处理静态 RGB 图片，不承诺 video、tracking、crowd counting、密集小目标 exhaustive recall 或所有实例一个不漏。

## Local VLM

```text
LOCAL VLM
= QUALIFIED
= INTEGRATED INTO PRODUCTION
```

Local VLM 已通过 subject 与 relation 两类 OpenAI-compatible 协议边界、完整 Production Pipeline smoke、240 次冻结执行以及 232 条 Cloud/Local 盲评比较。Production 使用一个最小共享 VLM client/config seam，使 `vlm.py` 与 `relations.py` 共同读取：

- `VLM_MODEL`
- `VLM_BASE_URL`
- `VLM_API_KEY`
- `VLM_TIMEOUT`

默认配置保持 Cloud Qwen 行为；自定义 endpoint 必须显式提供 `VLM_API_KEY`，不会静默继承 DashScope credential。DeepSeek Planner、Pipeline、Evidence、Detector、SAM、prompt、validator、三态与 relation 合同均未改变。

## 移出产品范围

```text
WATER-POLLUTION RGB RECOGNITION
= REMOVED FROM PRODUCT SCOPE

P1–P4 POLLUTION
= HISTORICAL RESEARCH ONLY
= NOT A PRODUCT REQUIREMENT
= NOT A FUTURE OPTIMIZATION GATE
```

水面垃圾、漂浮塑料瓶、漂浮物和污染区域等 RGB 图片识别不再推动 Visual Agent v1 Production 架构。既有实验结论仍是合法历史研究证据，不删除、不重写，也不因范围调整追溯修改原始结果。

## 研究合同归档

```text
SEMANTIC_IR_V1
= ACCEPTED RESEARCH CONTRACT
= NOT SCHEDULED FOR V1 PRODUCTION INTEGRATION

DETECTOR_QUERY_AND_RECALL_V1
= COMPLETED AS HISTORICAL RESEARCH
= ACCEPTED / CLOSED
= NO V1 PRODUCTION ACTION

DETECTOR_REPLACEMENT_BENCHMARK
= CANCELLED FOR V1 SCOPE
```

Semantic IR V1 的通用研究结论继续保留：

- `semantic_name ≠ localization_target ≠ detector_queries`
- `concept_type = instance | region`
- `attribute | behavior | object_relation | scene_relation`
- `target --predicate--> reference`

Detector Query / Recall V1 已证明 bounded lexical alias 对部分概念有召回价值，也记录了 Grounding DINO Base 在 dense/small/overlap 逐实例枚举上的能力边界。但这些结果不再触发 v1 Detector replacement 或 Production 重构。

## 未来独立项目

```text
REMOTE-SENSING WATER QUALITY
= FUTURE SEPARATE PROJECT
= Sentinel-2 / Landsat .tif
= 九参数反演
= NOT PART OF VISUAL AGENT V1
```

遥感水质业务未来应以独立数据合同、模型后端和验收体系开展。本次收尾不加入 `.tif` 处理、遥感反演或九参数代码。

## 收尾约束

- 不删除历史 evidence。
- 不继续 Detector replacement benchmark。
- 不重新运行 240/232 大型评测。
- 不重构 Pipeline。
- 不因移除 pollution 产品需求而删除通用 `region`、`scene_relation` 或其他研究概念。
- evidence 分支继续保留，最终审查完成后再单独决定是否删除。
