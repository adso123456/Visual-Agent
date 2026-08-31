# GENERAL_RGB_BEHAVIOR_RELATION_JOINT_TARGETED_CONFIRMATION_V1 — 执行报告

## 裁决

```text
EXECUTION = COMPLETE / FAIL
JOINT_POLICY_CANDIDATE = NOT CONFIRMED
PRODUCTION MODIFICATION = 0 / NOT AUTHORIZED
FAILED EXECUTION REPLACEMENT = false
```

本轮严格执行冻结的 48 个 slot。全部 slot 均产生唯一 terminal record；失败未修复、未补跑、未替换。

## 审计绑定

- Frozen evidence head：`30fa9cddd851f376831b2bd3d940f6ab1165c084`
- Authorization evidence commit：`bcecf872f6fdcfce2a22c69b218eaed467799669`
- Execution base：`be54f3c89171d8b16f53c82397e9f468fb4b4c97`
- Reviewed runner：`0aa9e45766dcaa846b4f22b1eea6d66ebe27e546`
- Model：`qwen3.8:27b-mtp-q4_K_M`
- Endpoint：`http://192.168.250.9:11434/v1`
- Timeout：120 秒
- Concurrency：1
- 执行窗口：2026-08-31 10:18:46 至 10:47:05（Asia/Shanghai），约 28 分 19 秒

正式启动前曾有两次 PowerShell wrapper 在 runner import、preflight、输出目录创建和模型调用之前因对空值调用 `Trim()` 而退出。两次均为 0 slot、0 模型调用、0 输出，不属于冻结执行记录。之后未修改 runner、参数、模型或合同，直接使用同一 reviewed module entry point 启动本批次。

## System / Contract 结果

| 指标 | 结果 |
|---|---:|
| scheduled | 48 |
| terminal | 48 |
| terminal success | 37 |
| terminal failure | 11 |
| Behavior success | 35/35 |
| Relation success | 2/13 |
| provider failure | 0 |
| protocol failure | 0 |
| validator failure | 0 |
| unexpected `OSError` | 11 |
| failed execution replacement | 0 |

11 个 Relation failure 的共同错误为 Windows `WinError 123`。Runner 使用 `slot.slot_id.replace("|", "__")` 生成 artifact 目录，但没有处理 case ID 内的 `::`。因此以下冻结 slot 的目录名在 Windows 上非法：

- `F4::fishing_017.jpeg`：5/5 failure
- `F2::fishing_005.jpeg`：5/5 failure
- `F2::fishing_024.jpeg`：1/1 failure

错误发生在 `run_relation_slot()` 调用 Production `run_pipeline()` 时创建/保存 artifact 的路径阶段。对应 pipeline 可能已经发生模型调用，但 runner 未返回 relation telemetry，因此不能从 terminal record 可靠重建这些失败 slot 的实际模型调用数、token 或 retry；报告不做推测。

不含 `::` 的两个 Relation control 正常结束：

- `core_003`：positive retained，未触发 hand fallback。
- `core_014`：0 target，hand fallback attempted=1，3 次 Detector call，0 hand Relation VLM call，未产生 false binding。

## Behavior 结果

Behavior 共 35/35 terminal success。实际 candidate verifier logical calls 为 56，attempts=56，retry=0，recovered=0；累计 prompt/completion/total token 为 167414 / 4137 / 171551，记录内 VLM latency 合计 847.042 秒。

冻结 Gate 摘要：

| 指标 | 结果 |
|---|---:|
| challenge_001 bystander satisfied | 0/5 |
| challenge_001 operator retained | 5/5 |
| challenge_003 uncertain preserved | 5/5 |
| challenge_004 elder retained | 5/5 |
| challenge_004 child satisfied | 0/5 |
| F1 candidate correct | 5/10 |
| F1 task correct | 3/6 |
| F1::fishing_004 A satisfied | true |
| new false assignment | 3 |
| fallback harm | 2 |
| Behavior Gate | FAIL |

具体非合规 observation：

- `F1::fishing_001.jpeg` candidate A：`satisfied`，expected=`not_satisfied`，false assignment。
- `F1::fishing_005.jpeg` candidate A：`satisfied`，expected=`not_satisfied`，false assignment。
- `F1::fishing_014.jpeg` candidate A：`satisfied`，expected=`not_satisfied`，false assignment。
- `F1::fishing_014.jpeg` candidate B/C：最终均为 `uncertain`，expected=`not_satisfied`，各记一次 fallback harm。

因此即使忽略 Relation runner failure，Behavior policy candidate 也未通过冻结 Gate。

## 最终结论

```text
BEHAVIOR POLICY CANDIDATE = NOT CONFIRMED
RELATION ACTIVATION POLICY CANDIDATE = INCONCLUSIVE DUE TO EXECUTION FAILURE
JOINT POLICY CANDIDATE = NOT CONFIRMED
```

本证据不授权修改 Production、不授权 merge，也不允许把 11 个失败 slot 作为同一批次补跑替换。若后续修复 Windows artifact path，必须形成新的 reviewed runner SHA、独立授权和新的批次身份；本批原始失败记录保持不可变。
