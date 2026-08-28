# GENERAL_RGB_F4_SMALL_HELD_OBJECT_LOCALIZATION_V1 — Gate R 执行报告

## 状态

- `GATE_R_EXECUTION = COMPLETE`
- `ARM_B = NOT CONFIRMED`
- `ARM_C = CONFIRMED`
- `SMALL_HELD_OBJECT_LOCALIZATION_PLUS_BINDING_MECHANISM = CONFIRMED BY ARM C`
- `PRODUCTION_POLICY = NOT CONFIRMED`
- `PRODUCTION_MODIFICATION = 0`

## Provenance

- Gate L evidence：`3308fee09ac2d3fa827f81854c1d556a0b4c87f6`
- Gate R authorization evidence：`d1d65adfd8f212661c4ef05339e78595075eb68b`
- Reviewed runner：`c6451a710e929116ee0941b2befc1ce223128232`
- Production reference：`be54f3c89171d8b16f53c82397e9f468fb4b4c97`
- Authorization SHA-256：`9ae5258a4cb6a31baec5aa4db5099094d63a4ee4c91cdc47803c69477690c71a`
- Model：`qwen3.8:27b-mtp-q4_K_M`
- Endpoint：`http://192.168.250.9:11434/v1`
- Timeout：120 秒
- Relation path：原样 Production `verify_relations()` + full-scene marked JPEG

## 冻结执行

- Arm B：5 independent calls
- Arm C：5 independent calls
- 执行顺序：B1、C1、B2、C2、B3、C3、B4、C4、B5、C5
- 每次 candidate universe：initial full-scene `R1–R4` + 当前 Arm Gate-L remapped candidates
- Failed execution replacement：`false`

## 结果

| Arm | Terminal success | Target satisfied | Subject A retained | Non-target satisfied | Final failure | Gate |
|---|---:|---:|---:|---:|---:|---|
| B | 5/5 | 0/5 | 0/5 | 0 | 0 | NOT CONFIRMED |
| C | 5/5 | 5/5 | 5/5 | 0 | 0 | PASS / CONFIRMED |

机械汇总：

```text
confirmed_arms = ["C"]
mechanism_confirmed = true
all_arms_pass = false
```

Arm B 的两个 reference-matching candidates 在 5 次中均保持 `uncertain`：一个标框在最终 marked scene 中不可辨认，另一个虽然位于 A 手掌中，但模型认为鱼类别证据不足。Arm C 的单一 hand-conditioned target candidate 在 5/5 中均为 `satisfied`，证据稳定指出该小鱼状物体由 A 手掌直接托握。

## 协议与成本

- Logical calls：10
- Attempts：10
- Retry：0
- Recovered：0
- Provider/protocol/validator/evidence final failure：0
- Prompt tokens：48,815
- Completion tokens：3,855
- Total tokens：52,670
- 10 次 logical-call 累计 wall latency：207.557 秒

## 合同解释

Gate R 按 Arm 独立确认。Arm C 同时满足：target small fish satisfied `>=4/5`、所有 non-target satisfied 为 0、subject A retained `>=4/5`、final failure 为 0。因此已经证明存在一个可行的“小物体定位 + 原 Production held binding”机制。

Arm B 未通过不否定 Arm C 的机制确认。该结果仍不等于 Production policy confirmed，也不授权 Production implementation、merge 或 General RGB Final Acceptance V2。

18 MiB PNG normalization 不适用于当前 Production Relation JPEG 路径；本次没有插入或修改 normalization。
