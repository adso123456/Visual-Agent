# GENERAL_RGB_FINAL_ACCEPTANCE_V1 — Final Report

## Final status

```text
GENERAL_RGB_FINAL_ACCEPTANCE_V1 = FAIL
REMOTE_SENSING_WATER_QUALITY = BLOCKED
```

## Gate summary

| Gate | Result | Evidence |
|---|---|---|
| System / Contract | PASS | 140/140 pipeline success；0 system/provider/protocol/validator final failure；140 JSON + 140 image artifacts |
| Core Delivery | PASS | plan/action/target/manual visual 均为 15/15 |
| Real-world Vision | FAIL | Positive usable 32/46（Gate ≥33/46）；Negative TN 57/67（Gate ≥58/67） |
| Challenge Safety | FAIL | failures: challenge_001, challenge_004 |

## Execution facts

- Local VLM：`qwen3.8:27b-mtp-q4_K_M` @ `http://192.168.250.9:11434/v1`；unexpected model/endpoint calls 均为 0。
- VLM calls=286，protocol attempts=286，retry=0，recovered=0。
- Tokens：prompt=995313，completion=20468，total=1015781。
- 累计端到端耗时：6492.478 秒。
- Evidence telemetry：records=245，normalized=7，max sent payload chars=17190864。

## Real-world result

| Prompt | PASS | DEGRADED | FAIL | TN | FP | Positive usable | Negative TN |
|---|---:|---:|---:|---:|---:|---:|---:|
| F1 | 11 | 4 | 4 | 5 | 5 | 15/19 | 5/10 |
| F2 | 8 | 2 | 6 | 9 | 3 | 10/16 | 9/12 |
| F3 | 1 | 0 | 2 | 25 | 1 | 1/3 | 25/26 |
| F4 | 6 | 0 | 2 | 18 | 1 | 6/8 | 18/19 |

评分来源：90 条满足 case_id + historical source + byte-identical SHA-256，机械继承冻结盲评；23 条 SHA 变化，重新人工审查；7 条 frozen invalid 仅进入 System denominator。

## Blocking findings

1. Real-world Positive usable 为 32/46，低于冻结 Gate 33/46。
2. Real-world Negative TN 为 57/67，低于冻结 Gate 58/67。
3. `challenge_001` 错误选择证据不足的白帽人物，违反 no false assignment。
4. `challenge_004` 未保留明确持竿老人，违反 elder retained。

未修改 Production，未补跑单条，未调整模型/prompt/Detector/SAM/evidence/validator/timeout/并发或评分合同。
