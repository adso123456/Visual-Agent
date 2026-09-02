# GENERAL_RGB_FINAL_ACCEPTANCE_V3 — Execution Report

## Final status

```text
GENERAL_RGB_FINAL_ACCEPTANCE_V3 = FAIL
SYSTEM_GATE = FAIL
VISUAL_ADJUDICATION = NOT_PERFORMED_SYSTEM_GATE_FAILED
PRODUCTION_MERGE = NOT_AUTHORIZED
```

## Execution facts

- Terminal：140/140。
- Pipeline success / SYSTEM FAILURE：132 / 8。
- Result JSON / image artifacts：132 / 132。
- Local Qwen Agent provider final failures：4（Planner HTTP 502=4）。
- Local Qwen Agent Final Response 空内容：2。
- Planner contract final failures：0。
- Local VLM provider / protocol / validator final failures：1 / 0 / 0。
- Evidence memory allocation failures：1。
- Local VLM calls：372；retry=0，recovered=0。
- Agent / VLM：qwen3.8:27b-mtp-q4_K_M @ http://192.168.250.9:11434/v1（openai_compatible）；执行前强制要求 DEEPSEEK_API_KEY 与 DASHSCOPE_API_KEY 均不存在。
- 累计端到端耗时：9191.077 秒。

## Bucket execution

| Bucket | Submitted | Success | Error |
|---|---:|---:|---:|
| CORE_CHALLENGE | 20 | 20 | 0 |
| F1 | 30 | 25 | 5 |
| F2 | 30 | 28 | 2 |
| F3 | 30 | 30 | 0 |
| F4 | 30 | 29 | 1 |

## Audit decision

本批次 140 个 terminal 结果全部保留，未补跑、未覆盖、未调参。由于 System Gate 已失败，不进行无法覆盖完整 denominator 的视觉质量裁决。
