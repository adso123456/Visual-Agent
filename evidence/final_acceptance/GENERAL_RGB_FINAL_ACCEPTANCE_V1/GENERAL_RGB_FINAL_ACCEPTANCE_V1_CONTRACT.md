# GENERAL_RGB_FINAL_ACCEPTANCE_V1 — Frozen Contract

## Status

```text
GENERAL_RGB_FINAL_ACCEPTANCE_V1 = CONTRACT FROZEN
MODEL EXECUTION = AUTHORIZED
PRODUCTION MODIFICATION = NOT AUTHORIZED
REMOTE_SENSING_WATER_QUALITY = BLOCKED
```

本阶段只验证最终冻结的 General RGB Production 是否可交付，不研究新架构，不进行 A/B，不使用 Global Context，不继续 Detector benchmark。

## 1. Production baseline

- Git commit：`master@4dac9cb3823e22e90ff3bb8157c6544c6c6b88fd`。
- 必须从该 commit 建立独立 clean worktree；执行前后 `git status --short` 均为空。
- Production code、prompt、Detector、SAM、Pipeline、evidence、validator、renderer、三态和 relation matrix 全部冻结。
- VLM：`qwen3.8:27b-mtp-q4_K_M`。
- VLM endpoint：`http://192.168.250.9:11434/v1`。
- `VLM_API_KEY` 必须显式设置为 dummy Local key；执行子进程移除 `DASHSCOPE_API_KEY`，禁止意外 Cloud VLM 调用。
- `VLM_TIMEOUT=120`、`MAX_CONCURRENT_JOBS=1`、temperature 保持 Production 默认。
- DeepSeek Planner 保持当前 Production 配置，不修改、不替换。

## 2. Frozen execution set

### A. Real-world General RGB matrix — 120 units

- 图片：既有 fishing 30 张。
- Prompt：F1/F2/F3/F4，每个 prompt 对全部 30 张 fishing 图片执行一次。
- Execution units：`4 × 30 = 120`。
- P1–P4 pollution：0；禁止进入本次执行或 Gate。

| Prompt | 文本 | Positive | Negative | Frozen invalid | Valid Positive | Valid Negative |
|---|---|---:|---:|---:|---:|---:|
| F1 | 框出正在钓鱼的人 | 20 | 10 | 1 positive | 19 | 10 |
| F2 | 把拿着鱼竿的人描边 | 18 | 12 | 2 positive | 16 | 12 |
| F3 | 框出桶 | 3 | 27 | 1 negative | 3 | 26 |
| F4 | 把拿着鱼的人标出来 | 8 | 22 | 3 negative | 8 | 19 |

Real-world system denominator：120。视觉 denominator：113，其中 positive=46、negative=67。

### B. Core delivery set — 15 units

精确使用 `benchmark/cases.json` 的 `core_001`～`core_015`。覆盖：

- 五种 action：highlight / outline / blur_target / dim_background / cutout；
- 单目标、多目标、0-target；
- attribute、behavior、simple held-by relation；
- person+umbrella composite；
- ordinary negative handling。

### C. Challenge / limitation probes — 5 units

精确使用 `challenge_001`～`challenge_005`，但不把五条混成一个普通 accuracy denominator：

- `challenge_001/002`：supported edge probes，必须 PASS 或 DEGRADED，不得发生相邻候选错误归属。
- `challenge_003`：legitimate ambiguity safety probe。接受保守 `uncertain/0-target`；confident satisfied target 视为 unsafe attribution。
- `challenge_004`：clear elder + ambiguous child。老人必须保留；儿童必须为 uncertain/未选，confident child assignment 视为 unsafe attribution。
- `challenge_005`：dense exhaustive recall non-goal，只参加 System/Artifact Gate；目标数量和漏检如实记录，不参加 Visual Delivery Gate。

### Total

```text
REAL_WORLD = 120
CORE = 15
CHALLENGE = 5
SYSTEM DENOMINATOR = 140
```

执行顺序固定为：`core_001..015 → challenge_001..005 → F1..F4 × fishing_001..030`。禁止根据中间结果调整顺序。

## 3. System / Contract Gate — zero tolerance

以下必须全部成立：

1. submitted=140、terminal=140、pipeline success=140；
2. SYSTEM FAILURE=0；
3. provider/protocol failure=0；
4. validator final failure=0；
5. Planner/Detector/SAM/renderer runtime failure=0；
6. 140 个 result JSON 齐全且可解析；
7. 每个需要渲染的 case 具有可读取 artifact；0-target case 的合同结构合法；
8. 实际 VLM model/base_url 全部为冻结 Local VLM；Cloud VLM call=0；
9. attempts/retry/recovered、token、latency、evidence telemetry 完整汇总；
10. 失败不得单条补跑、调参或从 denominator 删除。Runner 意外中断时只允许跳过已经落盘的 terminal units，不能覆盖或重跑。

任何一项失败：`GENERAL_RGB_FINAL_ACCEPTANCE_V1 = FAIL`。

## 4. Core Delivery Gate — strict

`core_001..015` 必须同时满足：

- 15/15 plan contract 正确；
- 15/15 target selection 与冻结 expected 一致；
- 15/15 action 正确；
- 15/15 人工视觉结果为 PASS；
- core_003/core_004 relation binding 与 person+umbrella composite 完整；
- core_012/core_013/core_014 为合法 0-target，未制造 false positive；
- 所有进入 SAM 的 case mask/action artifact 可用。

任意 Core 为 DEGRADED/FAIL：最终 Gate FAIL。Label 文案的非业务同义波动不算失败，但 plan 语义、关系、目标或 action 变化算失败。

## 5. Real-world Vision Quality Gate — frozen non-regression

评分原样复用历史 Phase3 rubric：

- Positive：PASS / DEGRADED / FAIL；PASS+DEGRADED 为 usable。
- Negative：TN / FP。
- SYSTEM FAILURE 与 VISION FAILURE 分开。
- 7 条 frozen invalid_test_data 参加 System denominator，但不参加视觉 denominator；名单不增不减。

### Historical Local baseline

来自既有 232-case blind adjudication 的 F1–F4 Local 结果：

| Prompt | Positive usable | Negative TN |
|---|---:|---:|
| F1 | 14/19 | 5/10 |
| F2 | 11/16 | 10/12 |
| F3 | 1/3 | 25/26 |
| F4 | 7/8 | 18/19 |
| Total | 33/46 | 58/67 |

最终 Real-world Gate 必须同时满足：

1. Positive usable ≥ 33/46；
2. Negative TN ≥ 58/67；
3. 每个 prompt 的 positive usable 不得比上表下降超过 1 个 unit，且 F3 不得降至 0；
4. 每个 prompt 的 TN 不得比上表下降超过 1 个 unit；
5. 新增 invalid_test_data=0；
6. 每个 prompt 必须分别报告 PASS/DEGRADED/FAIL 与 TN/FP，禁止只报总体率。

本 Gate 是“不低于已经完成盲评并获资格确认的 Local VLM 基线”，不是要求消除所有历史 VISION_FAILURE。

## 6. Current-output adjudication

- 只有同时满足 `same case_id`、`same frozen historical Local evidence source`、`artifact/evidence SHA-256 byte-identical`，才允许机械继承该 case 的冻结人工 grade/note。
- 映射缺失、SHA-256 不一致或无法唯一对应时，必须进入重新盲审；禁止仅凭视觉上“看起来一样”继承。
- 输出字节不同的 valid real-world case 必须重新盲审；不得显示历史 grade，不得按期望结果自动评分。
- Core 15 全部重新人工审查，不继承旧报告。
- Challenge 按 §2C 的安全/限制合同独立审查。
- 原始评分 JSON 是事实源；派生 summary 不能覆盖人工评分。

## 7. Allowed historical limitations

以下可以继续作为 v1 已知能力边界，但必须量化报告：

- 真实复杂场景中少量 VISION_FAILURE；
- behavior 的 35% local context starvation；
- relation binding 的 uncertain/漏判；
- 普通多人场景偶发 mixed candidate；
- 小目标、密集目标、重叠目标的 non-exhaustive recall；
- Full Chain 非实时延迟；
- legitimate visual ambiguity 保持 uncertain。

以下不允许被“已知限制”豁免：

- 任何 SYSTEM/provider/protocol/validator final failure；
- Core plan、relation、target 或 action 错误；
- Negative Core false positive；
- ambiguity probe 的 confident false assignment；
- artifact 缺失或结果 JSON 不可解析；
- 意外 Cloud VLM 调用；
- 为得到 PASS 而改 prompt、模型参数、Detector、SAM、Pipeline、evidence、validator、评分或测试集。

## 8. Challenge Safety Gate

- `challenge_001`：no false assignment。
- `challenge_002`：no false assignment。
- `challenge_003`：接受 uncertain / 0-target；禁止 confident false assignment。
- `challenge_004`：elder retained；child 不得被 confidently falsely assigned。
- `challenge_005`：不参加 Challenge visual PASS/FAIL；仅参加 System + Artifact observation。

## 9. Final decision

只有 System Gate、Core Delivery Gate、Real-world Vision Gate 和 Challenge Safety Gate 全部通过：

```text
GENERAL_RGB_FINAL_ACCEPTANCE_V1 = ACCEPTED
REMOTE_SENSING_WATER_QUALITY = UNBLOCKED FOR SEPARATE CONTRACT DESIGN
```

否则：

```text
GENERAL_RGB_FINAL_ACCEPTANCE_V1 = FAIL
REMOTE_SENSING_WATER_QUALITY = BLOCKED
```

失败后只允许根据明确失败模块另开阶段；禁止在本批次中修复、补跑或重评分。

## 10. Frozen sources

- `master@4dac9cb3823e22e90ff3bb8157c6544c6c6b88fd`
- `benchmark/cases.json` SHA-256：`6f56abbca54e7da8abe589881808d32801438e5e57bc0b69aa1929ca55b00acb`
- `acceptance_contract_v1.json` SHA-256：`08ea636fd3335599ddb219653b3a6ac07dba6d53f87e7f7906e9ea97131d9c5d`
- `manifest.json` SHA-256：`28a602012b06baef9fdeb798c26144fc6eca6bc1fdb4914864ac292bfdbefaa4`
- Frozen invalid adjudication SHA-256：`7729f2103d9319078a903d72734c1765d8928947da0efd924f09bec00d03e50f`
- Existing Local/Cloud evidence branch：`ed4ffacbb26b531d33cd2f2e49bb2f165afd9c7a`

## 11. Prohibited after Contract Freeze

- 只允许执行本合同冻结的 140-unit Local VLM acceptance；不得进行合同外模型调用或 Pipeline 实验。
- 不修改 Production、测试或环境变量。
- 不运行 120/140 acceptance。
- 不进入 Remote Sensing。
