# GENERAL_RGB_BEHAVIOR_LONG_RANGE_CONTEXT_REMEDIATION_V1

## Frozen 8-call execution report

状态：`LONG_RANGE_NOT_SATISFIED_ESCALATION_MECHANISM = CONFIRMED`

本报告不确认 Production policy。Production 修改与 merge 仍未授权。

## Execution identity

- Frozen contract evidence commit：`16d48bbe74b9d297ac66748d7bf39a75cfea42e9`
- Reviewed benchmark head：`22b22570c5f9ac6bd5249dae8f70782f500fb810`
- Model：`qwen3.8:27b-mtp-q4_K_M`
- Endpoint：`http://192.168.250.9:11434/v1`
- Provider：`openai_compatible`
- Timeout：120 秒
- Concurrency：1
- First-pass rerun：0
- Failed execution replacement：false

## System / contract

- Scheduled logical calls：8
- Terminal records：8
- Success：8
- Final failure：0
- Protocol attempts：8
- Retry：0
- Recovered：0
- Prompt tokens：38,072
- Completion tokens：474
- Total tokens：38,546
- Model latency：147.764 秒
- Batch wall time：147.828 秒

## Semantic Gate

### challenge_004 elder

5/5 escalation 均返回 `satisfied`。五次 evidence 文本一致指出：红色轮廓锚定的蓝色夹克男性站在水边，双手握持伸向水面的钓竿，呈典型钓鱼姿态。

Gate：`satisfied >= 4/5` → PASS。

### F1 negative controls

- `F1::fishing_010.jpeg` candidate A：`not_satisfied`；识别为徒手捕鱼而非持竿钓鱼。
- `F1::fishing_010.jpeg` candidate B：`not_satisfied`；识别为徒手/鸬鹚捕鱼而非钓鱼。
- `F1::fishing_018.jpeg` candidate A：`not_satisfied`；候选本身是一条鱼，不可能执行钓鱼行为。

Gate：3/3 保持 `not_satisfied`，new false assignment = 0 → PASS。

### Inherited immutable controls

Preflight 按 source `results.jsonl` 完整 SHA 与冻结 slot/status 验证 20 条记录：

- `challenge_001` bystander：`uncertain` 5/5。
- `challenge_001` true operator：`satisfied` 5/5。
- `challenge_003` legitimate ambiguity：`uncertain` 5/5。
- `challenge_004` child：`uncertain` 5/5。

这些状态没有模型重判。

## Decision

全部冻结 Gate 通过，因此：

`LONG_RANGE_NOT_SATISFIED_ESCALATION_MECHANISM = CONFIRMED`

该结论仅证明：在 target-anchored frozen first pass 为 `not_satisfied`、且任务预先属于 `OBJECT_MEDIATED_SCENE_INTERACTION` 时，一次 target-anchored full-scene escalation 能稳定救回 challenge_004 老人，同时未把三个正确 F1 negative 翻成 false positive。

它不证明完整 R3 Arm B 或组合策略已满足 Production Gate。此前 Arm B 的 F1 candidate/task 总体回归继续有效。

- `PRODUCTION POLICY = NOT CONFIRMED`
- `PRODUCTION MODIFICATION = NOT AUTHORIZED`
- `PRODUCTION MERGE = NOT AUTHORIZED`
- `REMOTE_SENSING_WATER_QUALITY = BLOCKED`
