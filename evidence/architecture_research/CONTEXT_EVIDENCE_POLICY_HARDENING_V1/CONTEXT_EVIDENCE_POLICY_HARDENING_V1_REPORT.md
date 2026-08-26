# CONTEXT_EVIDENCE_POLICY_HARDENING_V1 结果报告

```text
CONTEXT_EVIDENCE_POLICY_HARDENING_V1 = CLOSED WITH RELATION FOLLOW-UP
RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1 = PENDING
PRODUCTION MODIFICATION = NOT AUTHORIZED
```

## 执行边界

- 25 个冻结 General RGB 真实案例；F1/F2/F4 18 个，Demo Acceptance 7 个。
- P1–P4 为 0；未修改 Production；Local VLM 配置固定。
- 固定既有 Detector candidates 与 subject validity，只比较候选语义/关系 binding 的 evidence policy。
- A=当前 Production；B=A+每图一次 simplified global facts；C=仅 A uncertain 时 lazy fallback。

执行终端曾在 A 完成、C 完成 6 条后中断；runner 依据已落盘 case_id 原样续跑，未重跑、补跑或覆盖任何已完成 case。

## 核心结果

| Arm | Unit accuracy | Task accuracy | False assignment | Uncertain | Protocol failure | Logical calls | Tokens | Model seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 20/44 (45.45%) | 13/25 (52.00%) | 7 | 15 | 2 | 35 | 124108 | 585.1 |
| B | 26/44 (59.09%) | 16/25 (64.00%) | 4 | 12 | 0 | 60 | 217157 | 956.9 |
| C | 21/44 (47.73%) | 14/25 (56.00%) | 8 | 11 | 2 | 49 | 176497 | 886.2 |

## 协议与成本

| Arm | HTTP attempts | Retry | Recovered | Logical protocol failures | Calls/image | Tokens/image | Warm model seconds/image | Separate reasoning present |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 42 | 7 | 6 | 1 | 1.40 | 4964 | 23.40 | 0 |
| B | 67 | 7 | 7 | 0 | 2.40 | 8686 | 38.27 | 0 |
| C | 58 | 10 | 9 | 2 | 1.96 | 7060 | 35.45 | 0 |

这里的 latency 是串行 warm-model HTTP 调用累计值除以 25，不包含 SAM evidence 重建；不是端到端 Pipeline 延迟。

## Route 分解

### attribute

| Arm | Unit | Task | False assignment | Uncertain | Protocol failure |
|---|---:|---:|---:|---:|---:|
| A | 5/6 (83.33%) | 2/2 (100.00%) | 0 | 0 | 0 |
| B | 5/6 (83.33%) | 2/2 (100.00%) | 0 | 0 | 0 |
| C | 5/6 (83.33%) | 2/2 (100.00%) | 0 | 0 | 0 |

### behavior

| Arm | Unit | Task | False assignment | Uncertain | Protocol failure |
|---|---:|---:|---:|---:|---:|
| A | 12/22 (54.55%) | 7/14 (50.00%) | 5 | 6 | 0 |
| B | 16/22 (72.73%) | 9/14 (64.29%) | 3 | 2 | 0 |
| C | 13/22 (59.09%) | 8/14 (57.14%) | 5 | 3 | 0 |

### relation

| Arm | Unit | Task | False assignment | Uncertain | Protocol failure |
|---|---:|---:|---:|---:|---:|
| A | 3/16 (18.75%) | 4/9 (44.44%) | 2 | 9 | 2 |
| B | 5/16 (31.25%) | 5/9 (55.56%) | 1 | 10 | 0 |
| C | 3/16 (18.75%) | 4/9 (44.44%) | 3 | 8 | 2 |

## Adaptive 合同核验

- Lazy evaluation：PASS；触发 7 图 / 15 units。
- A 非 uncertain 结果不可变：PASS。
- 下游 payload 仅 facts/evidence：PASS；task_status leak=0。
- C uncertain resolution：`{"correctly_resolved": 2, "still_uncertain": 10, "wrong_resolution": 1, "fallback_harm": 1, "correctly_preserved": 1}`。
- C fallback harm：1。

## 裁决

- `attribute` → **ISOLATED_CANDIDATE_EVIDENCE / Arm A**（A/B/C 均为 5/6 unit、2/2 task；Global Facts 无质量增益，仅增加调用成本）
- `behavior` → **35_PERCENT_CANDIDATE_LOCAL_EVIDENCE / Arm A**（B/C 都把合法 uncertain 的 challenge_003 强制改为 satisfied；C 仅净增 1 个正确 unit，且存在 fallback_harm；B 虽增益较大但存在 1 个明确回归；当前结果不支持安全启用 Global Context）
- `relation` → **FULL_SCENE_MARKED_BINDING_EVIDENCE / Arm A**（B 的 unit correct 3→5、task correct 4→5、false assignment 2→1，方向正面；仅有 2 个 unit improvement，其中 1 个来自 A 的单次 logical protocol failure；纯语义改善基本只有 F2::fishing_008 一个 binding；B 的绝对 relation accuracy 仍为 5/16，uncertain 由 9 增至 10）
  - 研究候选：`FULL_SCENE_MARKED_BINDING_PLUS_SIMPLIFIED_GLOBAL_FACTS = NEEDS_CONFIRMATION`
  - 限定：B 是待确认研究候选，不是已通过 Production Gate 的 Evidence Policy
- `GLOBAL_CONTEXT_ROLE = AUXILIARY_CONTEXT_RESEARCH_CANDIDATE_ONLY`
- `PRODUCTION_CHANGE_RECOMMENDED = FALSE`

- `NEXT_GATE = RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1`

本阶段没有修改 Production；relation 的 B 结果只授权进入窄确认 Gate，不构成实施授权。

完整逐 unit 修正/回归、成本和协议统计见 `comparison_summary.json`；原始模型输出见三个 `arm_*.jsonl`。
