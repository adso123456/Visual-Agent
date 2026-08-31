# GENERAL_RGB_BEHAVIOR_RELATION_JOINT_TARGETED_CONFIRMATION_V1 — V2 执行报告

## 裁决

```text
BATCH = GENERAL_RGB_BEHAVIOR_RELATION_JOINT_EXECUTION_BATCH_V2
EXECUTION = COMPLETE / PASS
BEHAVIOR POLICY CANDIDATE = CONFIRMED BY TARGETED GATE
RELATION ACTIVATION POLICY CANDIDATE = CONFIRMED BY TARGETED GATE
JOINT POLICY CANDIDATE = CONFIRMED
PRODUCTION IMPLEMENTATION / MERGE = NOT AUTHORIZED
```

V2 是新的独立完整 48-slot 批次，不是首次失败批次的补跑或失败替换。首次 `469914a...` execution evidence 保持不可变。

## Provenance

- Authorization：`EXECUTION_AUTHORIZATION_V2.json`
- Authorization SHA-256：`c3f8c4b0f88490cee35924a24b105b6d81dcb2e60a5c2033bf38a8dd4337f1cc`
- Frozen evidence head：`30fa9cddd851f376831b2bd3d940f6ab1165c084`
- Observed evidence head：`60089ed608a2c72f0b2cb275e89ab8a4e5f68e54`
- Execution base：`be54f3c89171d8b16f53c82397e9f468fb4b4c97`
- Reviewed runner：`a1c61c3b4d38c25bafd841fc3b8c52fecbdbb897`
- Model：`qwen3.8:27b-mtp-q4_K_M`
- Endpoint：`http://192.168.250.9:11434/v1`
- Timeout：120 秒
- Concurrency：1
- Failed execution replacement：false
- 执行窗口：2026-08-31 11:33:31 至 12:12:48（Asia/Shanghai），约 39 分 17 秒

## System / Contract

| 指标 | 结果 |
|---|---:|
| scheduled | 48 |
| terminal | 48 |
| terminal success | 48 |
| terminal failure | 0 |
| Behavior | 35/35 success |
| Relation | 13/13 success |
| provider/protocol/validator/evidence final failure | 0 |
| failed execution replacement | 0 |

Windows-safe artifact slug 在 11 个含 `::` 的 Relation slot 上全部成功，未再出现 `WinError 123`。

## Behavior Gate

| 指标 | 结果 |
|---|---:|
| challenge_001 bystander satisfied | 0/5 |
| challenge_001 operator retained | 5/5 |
| challenge_003 uncertain | 5/5 |
| challenge_004 elder retained | 5/5 |
| challenge_004 child satisfied | 0/5 |
| F1 candidate correct | 5/10 |
| F1 task correct | 3/6 |
| F1 candidate regression | 0 |
| F1 task regression | 0 |
| F1::fishing_004 A satisfied | true |
| new false assignment | 0 |
| fallback harm | 0 |
| Behavior Gate | PASS |

Behavior candidate verifier：56 logical calls / 56 HTTP attempts，retry=0、recovered=0；prompt/completion/total tokens=`167414 / 4137 / 171551`，记录内 latency 合计 `1060.970s`。

## Relation Gate

| 指标 | 结果 |
|---|---:|
| F4::017 hand fallback attempts | 5/5 |
| F4::017 target satisfied | 5/5 |
| F4::017 subject retained | 5/5 |
| F4::017 non-target satisfied | 0 |
| F2::005 hand fallback attempts | 5/5 |
| F2::005 subject retained | 0/5 |
| F2::005 hand candidate satisfied | 0 |
| F2::024 final positive retained | true |
| core_003 final positive retained | true |
| existing-positive hand detector/relation calls | 0 / 0 |
| core_014 final target / new false binding | 0 / 0 |
| Relation Gate | PASS |

Relation 共执行 13 次正式 `run_pipeline()`。Production pipeline telemetry 记录 subject-validity attempts=13、relation attempts=22，retry=0、recovered=0。Hand fallback 共 11 次，Detector calls=33，hand Relation logical calls=10 / HTTP requests=10；其 prompt/completion/total tokens=`46285 / 805 / 47090`，请求 latency 合计 `122.672s`。

## Artifacts

- `execution_v2/preflight.json`
- `execution_v2/raw_results.jsonl`
- `execution_v2/summary.json`
- `execution_v2/relation_artifacts/`：13 个 slot 目录、13 JPG、13 result JSON、2 PNG mask
- `execution_v2/artifact_manifest.json`：逐文件 path / SHA-256 / bytes

原始执行文件共 31 个、`21,865,686` bytes；artifact manifest 独立记录这些原始文件，不包含自身，避免循环 hash。

## 边界

本轮只确认冻结的 Behavior + Relation policy candidate 在 targeted set 上通过。它不等于 Production 已实现，也不授权 merge 或 GENERAL_RGB_FINAL_ACCEPTANCE_V2。下一步必须先进行 Production implementation contract / code review，再决定 targeted Production regression 与最终验收。
