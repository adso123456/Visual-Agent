# LOCAL_VLM_QUALITY_COMPARISON_V1 — CONTRACT FREEZE

状态：`FROZEN / READY_FOR_LOCAL_EXECUTION`

本合同只冻结 Cloud Qwen 与 Local Qwen3.8 的系统可靠性及视觉质量比较口径。冻结期间不运行模型，不修改 Production 代码、prompt、Detector、SAM、evidence、validator 或评分规则。

## 1. 比较对象

### A — Cloud Qwen

- Production commit：`master@6ce8533d8a55b52e01d7daa30bce43139b5070b4`
- VLM：`qwen3-vl-flash`
- 执行来源：现有 SYSTEM RELIABILITY full-240 regression，不重新运行 Cloud
- 状态台账：`_phase2/fix_v1_regression_240.json`
- 结果 JSON：`_phase2/_reg240/{test_id}_{image_stem}.json`
- 渲染图：每条结果 JSON 的 `action_result.image_path`
- 已核验：240 result JSON、240 个互异且存在的渲染图、240/240 pipeline success、0 SYSTEM FAILURE

### B — Local Qwen3.8

- Production commit：`local-model-integration-v1@c2a784573dea313c3f80e714fbc4b7007563f9fa`
- VLM：`qwen3.8:27b-mtp-q4_K_M`
- OpenAI-compatible endpoint：`http://192.168.250.9:11434/v1`
- `VLM_API_KEY` 必须显式配置；不得回退或发送 DashScope credential
- `VLM_TIMEOUT=120`
- 待执行；必须使用正式 API/Batch/`run_pipeline()` Production path
- 禁止逐 case 修改模型参数或 prompt

## 2. 冻结测试矩阵

- 数据根目录：`E:\3\_visual_agent_real_world_acceptance\v1`
- 唯一图片：60 张，其中 fishing 30 张、water_pollution 30 张
- Prompt IDs：`F1/F2/F3/F4/P1/P2/P3/P4`
- 每个 F prompt 运行 30 张 fishing 图片；每个 P prompt 运行 30 张 water_pollution 图片
- Execution units：`8 × 30 = 240`
- 这里不是 60 张图片与 8 个 prompt 的全笛卡尔积；禁止扩成 480 条
- `MAX_CONCURRENT_JOBS=1`

Prompt 原文：

| ID | Prompt | Positive | Negative |
|---|---|---:|---:|
| F1 | 框出正在钓鱼的人 | 20 | 10 |
| F2 | 把拿着鱼竿的人描边 | 18 | 12 |
| F3 | 框出桶 | 3 | 27 |
| F4 | 把拿着鱼的人标出来 | 8 | 22 |
| P1 | 框出水面上的垃圾 | 17 | 13 |
| P2 | 高亮漂浮的塑料瓶 | 6 | 24 |
| P3 | 描边水中的漂浮物 | 26 | 4 |
| P4 | 标出水面污染区域 | 20 | 10 |

冻结事实源：

- `acceptance_contract_v1.json` SHA-256：`08ea636fd3335599ddb219653b3a6ac07dba6d53f87e7f7906e9ea97131d9c5d`
- `manifest.json` SHA-256：`28a602012b06baef9fdeb798c26144fc6eca6bc1fdb4914864ac292bfdbefaa4`
- 60 个实际图片文件合计 230,076,230 bytes；按 `image_id + file_sha256 + size` 排序生成的集合指纹：`9ead6988d8281e463f82e7d1947441e18586d58261244f562094dd675e57cee9`

## 3. 第一层：System / Contract

Cloud 与 Local 分别报告：

- submitted
- pipeline success
- SYSTEM FAILURE
- provider/protocol failure
- validator failure
- attempts / retry_count / recovered
- 每个 prompt 的 success / failed / success rate
- artifact 是否完整生成

System denominator 固定为 240；8 条 `invalid_test_data` 仍必须执行并参与 System denominator。

Local system gate：目标为 240/240 pipeline success、0 SYSTEM FAILURE、0 provider/protocol failure、0 validator failure。任何失败均保留原始错误，不得通过换测试集、调 prompt 或逐 case 调参规避。

## 4. 第二层：Vision Quality

完全复用 `ACCEPTANCE_CONTRACT_V1.md` 的 Phase3 rubric：

- Positive：`PASS / DEGRADED / FAIL`
- Negative：`TN / FP`
- `FAIL` 与 `FP` 归类为 `VISION_FAILURE`
- `invalid_test_data` 单独记录
- SYSTEM FAILURE 与 VISION FAILURE 分开，不得合并
- 禁止只报一个总体通过率；必须按 prompt 分开报告 Positive 与 Negative

冻结视觉 denominator：

- 原始 Positive：118
- 原始 Negative：122
- `invalid_test_data`：8
- Valid Positive：115
- Valid Negative：117
- Valid visual-quality denominator：232

若 Local 出现 SYSTEM FAILURE，该条仍计入 System denominator，但不伪造视觉 verdict；必须单独报告该条视觉不可评估，不得从报告中静默删除。

## 5. 冻结 invalid_test_data 名单

以下 8 条不增不减：

1. `F1 / fishing_022.jpeg` — positive
2. `F2 / fishing_021.jpeg` — positive
3. `F2 / fishing_022.jpeg` — positive
4. `F3 / fishing_022.jpeg` — negative
5. `F4 / fishing_010.jpeg` — negative
6. `F4 / fishing_022.jpeg` — negative
7. `F4 / fishing_025.jpeg` — negative
8. `P3 / pollution_030.jpeg` — negative

权威台账：`_phase2/adjudication.json`，SHA-256：`7729f2103d9319078a903d72734c1765d8928947da0efd924f09bec00d03e50f`。

## 6. Cloud 对照产物冻结

- `_phase2/fix_v1_regression_240.json` SHA-256：`c206103ba450972185a6d713f30f5757cdd84e711ad3a036f3021e54ad27ba60`
- 240 result JSON 集合指纹：`0f7c879f5ca10f2d1408db4da4fa2aabdb7c6673084445160be27742ce9f676e`
- 240 rendered image 集合指纹：`abe09c2e8e6a13aad4a7aa3a027d2764f1306164cd3c94639233733217e19d7d`
- 所有 240 条 `action_result.image_path` 当前存在，且路径互异

早期 Phase3 的 204 个成功 artifact 与当前 Cloud full-240 对比：

- 171 个渲染图 SHA-256 完全一致
- 33 个渲染图已变化
- 36 条当时为 SYSTEM FAILURE，没有早期成功 artifact

因此 Cloud 不重新运行，但正式 Cloud 视觉对照必须以当前 full-240 artifacts 为准。早期 `196 valid` 分数只能作为历史证据，不能作为本轮唯一 Cloud 质量结果；33 个变化结果和36个新增成功结果尤其不得沿用旧 verdict。

## 7. 禁止事项

- 不改 prompt、positive/negative 划分或 8 条 invalid 名单
- 不改 Detector、SAM、Pipeline、evidence、18 MiB normalization、4 MP first pass、relation、renderer、validator 或三态合同
- 不按 case 修改 Local VLM 参数
- 不因结果不好更换图片、评分规则或 denominator
- 不重新运行 Cloud 240
- Contract Freeze 阶段不运行 Local 240

下一阶段只允许在上述合同下，一次性执行 Local 240，并保存可追溯的 result JSON、渲染图、运行状态和协议 telemetry；完成后再进行 Cloud vs Local 质量判定。
