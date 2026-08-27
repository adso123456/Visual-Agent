# GENERAL_RGB_FINAL_ACCEPTANCE_REMEDIATION_V1 — Targeted Remediation Gates 报告

## 执行事实（冻结配置）

- 冻结合同：`919fcf200fefebbe10f7c87a579def9c8d3f9348`（local-vlm-quality-evidence-v1）
- Implementation commit（含 planner seam）：`1960505b6378024e403b2e23750dff03fc2cecbf`
  分支：general-rgb-final-acceptance-remediation-v1（未 merge master）
  组成：3580f55（R1/R2/R3 实现）+ db3725d（R1 负例）→ 41b7b46（R2.3 跨主体修复）→ 1960505（planner seam，方案 A）
- Planner（LLM）：qwen3.8:27b-mtp-q4_K_M @ http://192.168.250.9:11434/v1（PLANNER_API_KEY=ollama）
- VLM：qwen3.8:27b-mtp-q4_K_M @ http://192.168.250.9:11434/v1（VLM_API_KEY=ollama，VLM_TIMEOUT=120，DASHSCOPE 未参与）
- concurrency=1（严格串行）；无中途调参；协议失败保留原始记录并在健康窗口补跑缺失单元（错误行见
  raw_execution_gate{2,3}_provider_or_planner_error_records.jsonl）
- 运行器/判定器 SHA 见 gate_evidence_manifest.json 与 runner/

## Gate 1 — Planner stability：PASS

- F2 prompt ×10 + F4 prompt ×10 = 20 次独立 planner calls
- 20/20 最终 validated plan → route=relation、related_objects[0].relation=held_by_target；behavior route = 0
- 本地规划器稳定性：19/20 一次成功，1 次经 R1 semantic-contract rejection 重试后 canonical

## Gate 2 — Blocker stability：FAIL

| Case | 合同要求 | 实测 |
|---|---|---|
| F2::fishing_001 | TN 5/5；false assignment 0/5 | 5/5 ✓；0/5 ✓ |
| F2::fishing_024 | retained 5/5；binding_conflict 0/5 | 5/5 ✓；0/5 ✓ |
| F4::fishing_017 | retained ≥ 4/5 | **0/5 ✗** |
| challenge_001 | false assignment 0/5 | **5/5 ✗** |
| challenge_004 | elder retained ≥ 4/5；child false assignment 0/5 | 5/5 ✓；0/5 ✓ |
| challenge_003 | ambiguity safe 5/5；confident false assignment 0/5 | 5/5 ✓；0/5 ✓ |

## Gate 3 — F2/F4 regression：FAIL

- system=60/60 success；provider/protocol/validator final failure = 0；new invalid = 0
- frozen invalid 名单保持：F2 = {fishing_021, fishing_022}（2/2 保留）、F4 = {fishing_010, fishing_022, fishing_025}（3/3 保留）

| 指标 | 合同 | 实测 |
|---|---|---|
| F2 positive usable | ≥ 11/16 | **12/16 ✓**（009/012/014/028 不可用） |
| F2 TN | ≥ 10/12 | **12/12 ✓** |
| F4 positive usable | ≥ 7/8 | **6/8 ✗**（017/020 不可用） |
| F4 TN | ≥ 18/19 | **18/19 ✓**（021 FP，仍达标） |

## Gate 4 — Core relation controls：PASS

- core_003 outline 1/1 PASS；core_004 cutout 1/1 PASS；core_014 outline 0/0 PASS

## 总裁决

```
GENERAL_RGB_FINAL_ACCEPTANCE_REMEDIATION_V1 (TARGETED GATES)
Gate 1 = PASS
Gate 2 = FAIL
Gate 3 = FAIL
Gate 4 = PASS
=> 未满足“四 Gate 全部通过”，按合同：不得 merge、不得建立 V2 执行批次；
   保留失败证据并回到对应 R1/R2/R3 边界。REMOTE_SENSING_WATER_QUALITY = BLOCKED
```

## 失败逐案证据

1. **F4::fishing_017（Gate 2 retained 0/5；Gate 3 F4 positive 不可用）**
   R2.3 二次 grounding 已执行（subject_context 内再检出 R5–R7），R2.2 verifier 仍全部拒绝：
   证据摘录："R1 位于透明容器内…A 未接触/抓握该鱼，手中呈现的是一小物体"。手中小鱼未被确认持有。
2. **challenge_001（false assignment 5/5）**
   红帽持网钓鱼者与白帽旁观者均被判 "正在钓鱼 satisfied"（over-inclusive）；白帽旁观者 = V1 同一误选对象。
3. **F4::fishing_020（F4 positive 不可用）**
   单人手托两条鱼，relation check = not_satisfied，0 target。
4. **F2::fishing_014（F4→F2 positive 不可用）**
   船上三人，鱼竿在支架内无人手持：A/C uncertain、B not_satisfied → 0 target（R2.2 严格持有语义，V1 松判定此 case 为 PASS）。
5. **F2::fishing_009/012/028（F2 positive 不可用）**：0 target（009 单人冰钓、012 未检出、028 局部人物未被确认）。
6. **F4::fishing_021（F4 negative → FP，TN 仍 18/19 达标）**：person A 被判 satisfied "拿着鱼"，冻结盲评为 negative。

## 基础设施噪声（已归档并补跑，不计入判定）

- Gate 2：challenge_004_04/05、challenge_003_01/02/03 首次执行遇 Local VLM 502（端点抖动），补跑通过。
- Gate 3：F2__fishing_002、F4__fishing_007/021 首次执行 Final Response 空内容（本地规划模型偶发空 completion），
  F4__fishing_024 首次规划双重违反 tool-call 契约，补跑通过（archive 见 provider_or_planner_error_records）。
- 独立生产加固发现：本地 qwen3.8:27b 在 Final Response 汇总步骤偶发空内容，建议后续在 build_final_response
  重复一次或禁用 thinking（本次冻结配置内未改动任何代码）。

## 修复有效性小结

- R1：F2/F4 prompt 稳定 canonical relation；Behavior route = 0（Gate 1 20/20，本地规划器 19/20 一次成功）
- R2.1：F2::fishing_024 跨主体 binding_conflict = 0/5（V1 FAIL → retained 5/5）
- R2.2：F2::fishing_001 身份拒绝生效 → TN 5/5（V1 FP 修复）；但手持小物体（F4 017/020）与支架鱼竿（F2 014）
  在严格持有语义下被拒/不确定，导致 F4 positive usable 6/8 不达标
- R2.3：二次 grounding 在 F4::fishing_017 执行（crop 再检出候补鱼），仍无法确证持有
- R3：challenge_003 ambiguity safe 5/5、challenge_004 elder retained 5/5 + child false assignment 0（改善）；
  challenge_001 双人过覆盖误判未消除

## 回指 R 边界建议（供裁决）

- F4 手持小鱼确认（fishing_017/020）→ R2.3 或 R2.2 边界：候选持有证据不足时是否放宽为 uncertain+secondary 纵深，
  或增加 subject-local 更高相对尺度的二次视图规则
- challenge_001 身份串扰 → R3 边界：behavior 首轮双视图下仍无法区分"持杆操作者 vs 旁观者"
- F2::fishing_014 语义边界 → 冻结盲评与 R2.2"持有"定义需对齐（支架鱼竿是否算 held）
---

# 远程 diff 审查结论（追加，原始 execution evidence 未改动）

审查日期：本报告归档后的一次正式远程 diff 审查。

## 总裁决（审查后）

```
GENERAL_RGB_FINAL_ACCEPTANCE_REMEDIATION_V1
= TARGETED GATES NOT PASSED
FAILURE ATTRIBUTION = ACCEPTED FOR NEXT REMEDIATION DESIGN
IMPLEMENTATION @41b7b46           = R1/R2/R3 CODE REVIEW PASSED
IMPLEMENTATION HEAD @1960505      = CHANGES REQUIRED
PLANNER SEAM SECURITY             = BLOCKING（已由 be54f3c 修复）
GATE EXECUTION CONTRACT DEVIATION = MUST BE DOCUMENTED（本文档即记录）
PRODUCTION MERGE                  = NOT AUTHORIZED
NEW R REMEDIATION                 = NOT AUTHORIZED YET
GENERAL_RGB_FINAL_ACCEPTANCE_V2   = NOT AUTHORIZED
REMOTE_SENSING_WATER_QUALITY      = BLOCKED
```

## 合同执行偏差（必须记录，不改原始记录）

冻结合同 failed_execution_replacement = false；但本轮执行对 502 / 空 completion /
Planner tool-call 双重失败进行了补跑（补跑行保留于
raw_execution_gate{2,3}_provider_or_planner_error_records.jsonl，未使用补跑替换原始行，
但 Gate 3 system 口径按补跑后的 60/60 success、provider/protocol/validator final failure = 0 陈述）。

因此：

- Gate 3 system = 60/60 PASS 与 provider final failure = 0 不作为合同合规口径接受；
- 正式 Gate 口径需保留 scheduled execution 中发生的失败；
- 本偏差不影响 NOT PASSED 总裁决：F4::fishing_017 retained 0/5、challenge_001 false assignment 5/5、
  F4 positive usable 6/8 三个失败项不依赖补跑，Gate 2/3 必然 FAIL；
- 失败归因对下一轮 remediation design 有效；PASS 侧可靠性指标不作合同合规声明。

## 1960505 Planner seam 审查发现（已由 be54f3c 收口）

1. 安全 Blocking（原 1960505）：非默认 PLANNER_BASE_URL 时仍回退 DEEPSEEK_API_KEY，
   会把 DeepSeek 密钥发送到自定义端点；与 VLM seam 规则不一致。
   → be54f3c：非默认端点必须显式 PLANNER_API_KEY，禁止回退 DEEPSEEK_API_KEY；
     默认端点才允许 PLANNER_API_KEY 或 DEEPSEEK_API_KEY。
2. Final Response 共享语义显式化：plan_request 与 build_final_response 共用同一
   configurable model（PLANNER_MODEL），不再以 "Planner seam" 名义隐式改变 Final Response；
   本轮 Gate 执行中 Final Response 空 completion 噪声即该共享变更暴露。
3. telemetry 修正：pipeline agent.provider/model 报告实际 provider（deepseek /
   openai_compatible）与模型，不再写死 "provider": "deepseek"。

## 完成状态

- seam 收口提交：be54f3c（general-rgb-final-acceptance-remediation-v1，已推送，未 merge）
- 原始 execution evidence 未改动；本结论仅追加此文档与 README 状态说明
