# RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1 — Frozen Contract

## Status

```text
RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1 = CONTRACT FROZEN
PRODUCTION MODIFICATION = NOT AUTHORIZED
GENERAL_RGB_FINAL_ACCEPTANCE_V1 = PENDING
REMOTE_SENSING_WATER_QUALITY = BLOCKED
```

## Objective

只确认 Relation 的 Simplified Global Facts 是否带来稳定、可重复的纯语义增益，并排除单次协议失败、随机波动和同图重复任务造成的证据放大。

不重新研究 attribute/behavior，不修改 Detector、SAM、Pipeline、prompt、validator、evidence 或 Production。

## Frozen evaluation

- 7 个会实际产生 relation VLM 调用的冻结 case。
- 16 个冻结 binding。
- 每个 case 独立重复 5 次。
- `SCHEDULED_PAIRED_BINDING_SLOTS = 16 × 5 = 80`。
- `VALID_PAIRED_SEMANTIC_OBSERVATIONS <= 80`；协议失败不补跑，不能预称为 80 个有效 observations。
- 35 个 case-repetition；每个计划 A relation、B global、B relation，共 105 个 scheduled logical calls。
- Independence unit 是 `DISTINCT IMAGE_SHA256 GROUP`。同一原图上的不同 prompt/action 不能贡献多个独立 scene-level improvement source。
- `core_003/core_004` 若同时出现，只能贡献一个独立 image group；当前冻结执行只包含 `core_003`，不额外加入 action-only duplicate `core_004`。

## Arms

### A

当前 Full-scene Marked Binding relation evidence，不提供 Global Facts。

### B

与 A 完全相同的 marked-scene evidence、relation prompt 和 validator，并额外执行一次 Simplified Global Context。Global Context 每个 case-repetition 重新生成，不跨重复缓存。

下游 payload 由程序确定性投影为：

```json
{
  "facts": ["..."],
  "evidence": "..."
}
```

`task_status` 不进入 relation verifier。

## Execution controls

- Local VLM：`qwen3.8:27b-mtp-q4_K_M`。
- Endpoint：`http://192.168.250.9:11434/v1`。
- Temperature：0。
- Timeout：120 秒。
- Concurrency：1。
- Production validator/retry contract 原样复用。
- A/B 顺序严格使用 `frozen_schedule.json`；35 个 case-repetition 总体为 A-first 18、B-first 17。
- 禁止根据中间结果调整顺序、参数、样本或 prompt。
- final protocol failure 原样保留，不补跑。

## Reliability accounting

分别报告：

1. A relation logical final failure rate：`A relation final failures / 35`。
2. B global-context logical final failure rate：`B global final failures / 35`。
3. B global projection contract failure：`projection failures / 35`。
4. B relation logical final failure rate：`B relation final failures / executed B relation calls`。
5. B 因 Global Context 失败而未执行 relation 的次数。

任何 B Global Context 最终失败都必须进入 B reliability 统计，不能因 relation 未执行而消失。

一个群组 relation logical failure 即使影响多个 binding，也只计一次 logical final failure；受影响 binding 不能作为语义证据。

## Paired semantic observation

同一 case、同一 repetition 中，只有以下全部成立才形成 paired-valid semantic observation：

- A relation 通过 validator；
- B Global Context 通过 validator；
- B projection 合同通过；
- B relation 通过 validator。

否则该 repetition 对相应 bindings 不进入 semantic comparison，但仍进入 reliability denominator。

## Stable semantic state

对每个 binding 分别聚合 paired-valid repetitions：

- 5 个 paired-valid：同一状态至少 4/5 才 stable。
- 4 个 paired-valid：必须 4/4 同一状态才 stable。
- 少于 4 个 paired-valid：`INCONCLUSIVE`。
- 4 或 5 个有效重复但达不到上述一致性：`UNSTABLE`。

`stable_semantic_improvement` 必须同时满足：

```text
A 有 stable semantic state
B 有 stable semantic state
A stable state != expected
B stable state == expected
```

A 不稳定或 inconclusive、B 变为稳定正确，只记录为 `stability_improvement`，不能计入确认 Gate 所要求的纯语义改善。

`stable_semantic_regression` 定义为：

```text
A stable state == expected
B stable state != expected
```

## Confirmation Gate

B 只有同时满足以下全部条件才为 `CONFIRMED`：

1. stable pure semantic improvements ≥ 2；
2. improvements 覆盖至少 2 个不同 `image_sha256` groups；
3. stable semantic regression = 0；
4. B stable false assignment ≤ A；
5. legitimate `uncertain → wrong binary` = 0；
6. B Global projection contract failure = 0；
7. B relation validator failure rate ≤ A；
8. Global Context final failures完整记录，未从 B reliability denominator 隐藏。

否则：

```text
RELATION_GLOBAL_FACTS_CANDIDATE = NOT CONFIRMED
RELATION_EVIDENCE_POLICY = KEEP CURRENT PRODUCTION
PRODUCTION MODIFICATION = NOT AUTHORIZED
```
