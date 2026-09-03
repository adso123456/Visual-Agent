# GENERAL_RGB_FINAL_ACCEPTANCE_V4 — Execution Report

## Final status

```text
GENERAL_RGB_FINAL_ACCEPTANCE_V4 = FAIL
SYSTEM_GATE = FAIL
VISUAL_ADJUDICATION = NOT_PERFORMED_SYSTEM_GATE_FAILED
PRODUCTION_MERGE = NOT AUTHORIZED
```

## Execution facts

- Terminal：140/140，unique=140。
- System success / SYSTEM FAILURE：137 / 3。
- Result JSON / image artifacts：139 / 139。
- Final Response failures：2；Planner contract final failures：1。
- Transport exhausted / VLM protocol / validator / MemoryError：0 / 0 / 0 / 0。
- Agent / VLM：qwen3.8:27b-mtp-q4_K_M @ http://192.168.250.9:11434/v1；unexpected VLM model/endpoint：0/0。
- 累计记录耗时：13176.668 秒（包含一次约 4357 秒系统待机）。
- 2026-09-03 12:14:44–13:27:21 Windows 进入 Modern Standby；原 runner 未重启，恢复后继续，未补跑或覆盖 unit。`F2__fishing_026` 的在途 Relation 请求超时后由 transport retry 恢复，unit 最终 success。

## Failed units

| Unit | Class | Error | Artifacts |
|---|---|---|---|
| F2__fishing_027 | agent_final_response_empty | final_response_status=failed_empty_response; agent_response_empty | JSON + image |
| F4__fishing_007 | planner_contract_final_failure | DeepSeek Planner 两次均违反契约：显式手持语义（手持/拿着/撑着）必须编译为 relation + held_by_target | none |
| F4__fishing_021 | agent_final_response_empty | final_response_status=failed_empty_response; agent_response_empty | JSON + image |

## Bucket execution

| Bucket | Submitted | Success | SYSTEM FAILURE |
|---|---:|---:|---:|
| CORE_CHALLENGE | 20 | 20 | 0 |
| F1 | 30 | 30 | 0 |
| F2 | 30 | 29 | 1 |
| F3 | 30 | 30 | 0 |
| F4 | 30 | 28 | 2 |

## Audit decision

V4 是独立 140-unit batch，未拼接 V3 或 8-unit replay。全部 terminal 结果原样保留，未补跑、覆盖或替换。由于存在 3 个 SYSTEM FAILURE，V4 按冻结流程 FAIL / CLOSED，不进行视觉裁决。
