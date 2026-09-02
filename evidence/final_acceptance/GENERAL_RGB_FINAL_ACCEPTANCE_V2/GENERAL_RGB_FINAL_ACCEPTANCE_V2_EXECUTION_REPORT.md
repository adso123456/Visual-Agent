# GENERAL_RGB_FINAL_ACCEPTANCE_V2 — Execution Report

## Final status

```text
GENERAL_RGB_FINAL_ACCEPTANCE_V2 = FAIL
SYSTEM_GATE = FAIL
VISUAL_ADJUDICATION = NOT_PERFORMED_SYSTEM_GATE_FAILED
PRODUCTION_MERGE = NOT_AUTHORIZED
```

## Execution facts

- Terminal：140/140。
- Pipeline success / SYSTEM FAILURE：62 / 78。
- Result JSON / image artifacts：62 / 62。
- DeepSeek provider final failures：77（503=74，500=2，invalid None response=1）。
- Planner contract final failures：1。
- Local VLM provider / protocol / validator final failures：0 / 0 / 0。
- Local VLM calls：227；retry=0，recovered=0。
- 累计端到端耗时：5612.163 秒。

## Bucket execution

| Bucket | Submitted | Success | Error |
|---|---:|---:|---:|
| CORE_CHALLENGE | 20 | 20 | 0 |
| F1 | 30 | 30 | 0 |
| F2 | 30 | 12 | 18 |
| F3 | 30 | 0 | 30 |
| F4 | 30 | 0 | 30 |

## Audit decision

本批次 140 个 terminal 结果全部保留，未补跑、未覆盖、未调参。由于 System Gate 已失败，不进行无法覆盖完整 denominator 的视觉质量裁决。
