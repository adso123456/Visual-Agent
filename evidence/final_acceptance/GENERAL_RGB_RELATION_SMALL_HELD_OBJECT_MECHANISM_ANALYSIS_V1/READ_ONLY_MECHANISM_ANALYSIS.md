# GENERAL_RGB_RELATION_SMALL_HELD_OBJECT_MECHANISM_ANALYSIS_V1

## 状态

```text
GENERAL_RGB_RELATION_SMALL_HELD_OBJECT_MECHANISM_ANALYSIS_V1
= READ-ONLY COMPLETE

MODEL CALLS
= 0

PRODUCTION / BENCHMARK CODE MODIFICATION
= 0
```

本阶段只读取既有冻结 evidence，分别追踪 `F4::fishing_017.jpeg` 与
`F4::fishing_020.jpeg` 从 subject validity、related-object grounding、secondary grounding、
held binding 到最终 artifact 的执行链。没有重新调用模型，也没有把两案预设成同一根因。

## 结论摘要

两案不是同一种 relation failure。

| Case | 首个决定性失败层 | 机械归因 |
|---|---|---|
| F4::fishing_017 | related-object grounding | **RELATED_OBJECT_NOT_GROUNDED（指手中目标小鱼）**；small-object evidence scale 是被现有证据支持的机制因素 |
| F4::fishing_020 | subject validity | **SUBJECT_VALIDITY_REJECTED_BEFORE_RELATION**；不属于 held binding 或 related-object grounding 失败 |

因此不能把两案合并成一个“放宽 held verifier”修复。017 的 verifier 正确拒绝了被框出的桶内鱼；
020 根本没有进入 relation 路径。

## F4::fishing_017

### 冻结执行事实

- 原图 SHA-256：`2ca02d15f8799d620598751ef299851915f91fe094d863a5f7cf51f6b50f0c99`。
- subject A 被保留为 relation-eligible person，bbox 固定为
  `[3.93, -13.14, 1140.06, 2078.16]`。
- 旧 Final Acceptance 首轮得到 4 个 fish candidates，4/4 binding 均为 `not_satisfied`。
- Remediation Gate 2 的 5 次执行全部 terminal success；每次都得到 7 个 fish candidates：
  首轮 R1–R4 加一次 35% subject-conditioned secondary grounding 的 R5–R7。
- 每次 7/7 binding 均为 `not_satisfied`；`satisfied=0`、`uncertain=0`、retry=0。
- R1–R7 的 evidence 一致描述候选鱼位于透明桶内/桶口附近，主体手部未抓握这些鱼；
  同时多次指出手中是“另一小物体”。
- 五次最终 target 均为 0，Gate 2 retained = 0/5。

### 分层判断

1. `RELATED_OBJECT_GROUNDED_BUT_HELD_BINDING_REJECTED` **不适用于目标小鱼**。
   Grounding 确实找到了多个“鱼”，但它们是桶内/桶边的其他鱼，不是用户语义中手里那条小鱼。
2. `RELATED_OBJECT_NOT_GROUNDED` **成立**：手中目标小鱼没有进入 relation candidate universe。
3. `SMALL_OBJECT_EVIDENCE_SCALE_INSUFFICIENT` **作为机制因素有直接支持**：
   固定 35% subject-local secondary grounding 已执行并新增 R5–R7，仍只重复发现桶内较显著鱼，
   没有形成手中小鱼候选。
4. `SUBJECT↔OBJECT_RELATION_CONTEXT_INSUFFICIENT` **不是现有证据指向的首因**：
   marked full scene 中包含人物手部、桶和候选对象；verifier 能稳定判断被框候选不在手中。
   缺失的是正确 related-object identity anchor，而不是对已框目标的归属推理失败。

### 最小机制边界

017 后续若设计 remediation，应先研究“subject-hand vicinity 中的小型 requested object 如何进入候选 universe”，
而不是放宽 `held_by_target`。在目标小鱼仍未被框出的条件下放宽 verifier，会把桶内鱼错误借给人物，破坏
现有 ownership safety。

## F4::fishing_020

### 冻结执行事实

- 原图 SHA-256：`c3179a25a12c012e194afd9e5163a360a4687b8527aeaf67205cad591eef44d5`。
- person detector 返回一个几乎覆盖全图的候选 A：
  `[87.97, 14.53, 3826.89, 5734.23]`，confidence `0.5861`。
- subject validity 将 A 判为 invalid：画面只有两只手、部分前臂和少量衣物，缺少可独立识别为完整人物的结构。
- `relation_candidates=[]`、`relation_bindings=[]`；relation grounding、relation verification 均为 0 次。
- Final Acceptance V1 与 Remediation Gate 3 都在同一上游边界停止，最终 target=0。
- 既有独立研究证据中，同一原图的 simplified global context、single-candidate full-scene、group-scene
  均能把任务语义识别为 `satisfied`；这说明“手托鱼”的视觉事实可见，但 Production 的完整人物实例合同阻止其进入 relation。

### 分层判断

020 不属于下列四个 relation 内部类别中的任何一个：

- 不是 `RELATED_OBJECT_NOT_GROUNDED`：related-object grounding 未启动；
- 不是 `RELATED_OBJECT_GROUNDED_BUT_HELD_BINDING_REJECTED`：没有 candidate/binding；
- 不是已执行后的 `SMALL_OBJECT_EVIDENCE_SCALE_INSUFFICIENT`：鱼本身在原图中大且清晰；
- 不是 `SUBJECT↔OBJECT_RELATION_CONTEXT_INSUFFICIENT`：relation verifier 从未收到 evidence。

其首因应单独记录为：

```text
SUBJECT_VALIDITY_REJECTED_BEFORE_RELATION
= PARTIAL-PERSON / EXISTENTIAL-SUBJECT CONTRACT MISMATCH
```

它涉及“只有手/前臂但持有关系清晰时，是否允许把隐含人物作为 existential subject”的产品合同，
不是 small held-object grounding 的同一修复点。

## 对下一步的约束

```text
F4::fishing_017
PRIMARY = REQUESTED HELD OBJECT NOT GROUNDED
SUPPORTED MECHANISM = SMALL HELD OBJECT SCALE / LOCALIZATION
DO NOT = RELAX HELD BINDING WITHOUT CORRECT OBJECT ANCHOR

F4::fishing_020
PRIMARY = SUBJECT VALIDITY REJECTED BEFORE RELATION
BOUNDARY = PARTIAL-PERSON / EXISTENTIAL-SUBJECT CONTRACT
DO NOT = TREAT AS RELATION VERIFIER FAILURE

UNIFIED SMALL-HELD-OBJECT REMEDIATION FOR 017+020
= NOT SUPPORTED
```

下一次合同设计应先由人工决定 020 是否属于 v1 必须支持的“隐含人物/局部人体”语义。
如果不属于，则应作为明确 limitation；如果属于，则需要独立 subject-contract remediation。
017 才适合进入一个很窄的 small-object localization/evidence-scale mechanism design。

Behavior policy candidate 保持原状态，不在本阶段重新确认；Production modification、merge、
General RGB Final Acceptance V2 均未授权，Remote Sensing Water Quality 继续 blocked。

## 审计来源

精确来源路径、SHA-256、计数和机器归因见同目录 `mechanical_attribution.json` 与 `manifest.json`。
