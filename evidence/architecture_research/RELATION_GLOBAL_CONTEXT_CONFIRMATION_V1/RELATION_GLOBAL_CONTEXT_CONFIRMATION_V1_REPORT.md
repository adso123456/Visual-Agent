# RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1 结果报告

## 执行完整性

- 7 cases / 16 bindings / 5 repetitions。
- Scheduled paired binding slots：80；valid paired semantic observations：70。
- Scheduled logical calls：105；actual executed logical calls：105。
- Paired-valid case repetitions：30/35。
- A-first/B-first：18/17。

## Reliability

| Layer | Scheduled | Executed | Final failure | Rate | Retry | Recovered | Tokens | Model seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A relation | 35 | 35 | 5 | 14.29% | 35 | 30 | 304720 | 1023.1 |
| B global | 35 | 35 | 0 | 0.00% | 0 | 0 | 141250 | 429.8 |
| B relation | 35 | 35 | 0 | 0.00% | 35 | 35 | 313685 | 1042.9 |

- B global projection contract failure：0。
- B relation skipped due global failure：0。

### Protocol-only observation

- `F4::fishing_003.jpeg`：A relation final failure 5/5，B relation final failure 0/5；该变化只计 reliability，不计 semantic improvement。

## Stable semantic result

- Stable pure semantic improvements：1。
- Independent improvement image SHA groups：1。
- Stability improvements（不计入 Gate）：0。
- Stable semantic regressions：0。
- Stable false assignment A/B：2/1。
- Legitimate uncertain → wrong binary：0。

- Pure improvements：`F2::fishing_008.jpeg / B::R1`：A=uncertain → B=satisfied（expected=satisfied）。

## Gate

| Condition | Result |
|---|---|
| `stable_pure_semantic_improvements_gte_2` | FAIL |
| `distinct_image_sha256_groups_gte_2` | FAIL |
| `stable_semantic_regression_eq_0` | PASS |
| `b_false_assignment_lte_a` | PASS |
| `legitimate_uncertain_to_wrong_binary_eq_0` | PASS |
| `global_projection_contract_failure_eq_0` | PASS |
| `b_relation_failure_rate_lte_a` | PASS |
| `global_final_failures_recorded` | PASS |

## Decision

```text
RELATION_GLOBAL_FACTS_CANDIDATE = NOT CONFIRMED
RELATION_EVIDENCE_POLICY = KEEP_CURRENT_PRODUCTION
PRODUCTION MODIFICATION = NOT AUTHORIZED
```

逐 binding 五次状态、稳定性分类与 improvement/regression 明细见 `confirmation_summary.json`；逐 logical call 原始响应见 `raw_call_events.jsonl`。
