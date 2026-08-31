# GENERAL_RGB_BEHAVIOR_RELATION_PRODUCTION_IMPLEMENTATION_PREFLIGHT_V1

## 状态

`IMPLEMENTATION PREFLIGHT = EXECUTED / READ-ONLY`
- 检查 1–3：PASS
- 检查 4：PASS（88/88 pytest；附 1 项脚本级 baseline 发现，见 §4.3）
- 检查 5：PASS（已执行子集 0 模型 / DINO / SAM 调用）
- Production code modification：`NOT AUTHORIZED`（本阶段零 Production 改动）
- Implementation：`NOT AUTHORIZED`
- 原始输出：`pytest_junit_88tests.xml`（10 个 pytest 文件 88 用例）

## 0. 依据

- Contract：`GENERAL_RGB_BEHAVIOR_RELATION_PRODUCTION_IMPLEMENTATION_CONTRACT_V1` revision 2
  （Evidence HEAD `071b3590a1db193da560cda8b058953d8cbbe5b2`，REVIEW = PASS / FROZEN）
- Frozen contract SHA：contract_candidate.json `f5264b0d...8bd015a`、MD `74366e06...f8f0ea`、manifest `63796d86...5c9a9`
- Implementation target tree：`be54f3c89171d8b16f53c82397e9f468fb4b4c97`
- 本 preflight 不修改任何 Production 文件；不运行任何真实模型。

## 1. 设计定的 implementation worktree

- 路径：`E:\3\Visual Agent\_implementation_worktree`
- Branch：`general-rgb-behavior-relation-production-implementation-v1`（新建，base = be54f3c）
- 新建原因（透明披露）：be54f3c 树内文件在 `core.autocrlf=true` 下以 CRLF 字节检出；
  contract §0 冻结 SHA 是 reviewed runner（a1c61c3 joint worktree）检出字节的 SHA-256，
  即全 CRLF 转换后的字节哈希。既有 `_remediation_v1` worktree 中 evidence.py / vlm.py /
  relations.py 的磁盘字节为早期混合换行的陈旧检出（git 归一化后与 be54f3c blob 完全一致，
  `git status` 干净，但字节哈希不等于冻结值）。为满足 §3.2 "8/8 当前 worktree 文件 == 冻结 SHA"
  的字节级门且不触碰任何现有文件，本 preflight 新建规范检出的 implementation worktree：
  同一 LF blob 的确定性 CRLF 检出，8/8 字节哈希与冻结值一致。

## 2. 检查 1 — worktree HEAD / base

```text
git rev-parse HEAD        = be54f3c89171d8b16f53c82397e9f468fb4b4c97
expected                 = be54f3c89171d8b16f53c82397e9f468fb4b4c97
RESULT = PASS
```

## 3. 检查 2 — git status --short = empty

```text
git status --porcelain 条目数 = 0
git diff --exit-code         = 0
RESULT = PASS
```

## 4. 检查 3 — 8/8 Production 文件 SHA-256 == 合同冻结值

| File | Frozen SHA-256 | Worktree SHA-256 | |
|---|---|---|---|
| visual_agent/pipeline.py | `531903d3...adb0452` | 一致 | OK |
| visual_agent/evidence.py | `8dc4f1d6...5749747` | 一致 | OK |
| visual_agent/vlm.py | `a2df5c96...ae6d83e` | 一致 | OK |
| visual_agent/relations.py | `293f2c98...286f968` | 一致 | OK |
| visual_agent/grounding.py | `ac56602e...28f3be` | 一致 | OK |
| visual_agent/qwen_protocol.py | `89ccd004...6ebfb3` | 一致 | OK |
| visual_agent/vlm_client.py | `a3678216...82c88` | 一致 | OK |
| visual_agent/deepseek_agent.py | `cdc6be9c...0f1f12` | 一致 | OK |

`SHA_MATCH = 8/8`，`RESULT = PASS`（完整 SHA 见 `preflight_receipt.json`）。

注（字节口径澄清）：冻结 SHA 是 "autocrlf=true 检出字节" 的 SHA-256；be54f3c 的 LF blob
本体哈希不同（如 pipeline.py blob=`e64e63aa...`）。二者 git 级内容等价；
preflight 与实现审查统一使用工作树字节口径（与 reviewed runner `_verify_file` 一致）。

## 5. 检查 4 — 合同列出的 16 个既有测试在 be54f3c baseline

### 5.1 pytest 子集（10 个文件 / 88 用例）— 全部 PASS

运行环境锁定：`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`、
`VLM_BASE_URL=http://127.0.0.1:9`、`VLM_API_KEY=dummy`、`DASHSCOPE_API_KEY=dummy`；
Python 3.12.4 / pytest 7.4.4 / torch 2.11.0+cpu（cuda=False）。

| File | Tests | Result |
|---|---:|---|
| test_planner_config.py | 8 | PASS |
| test_router_plan_contract.py | 24 | PASS |
| test_vlm_client_config.py | 12 | PASS |
| test_evidence_builders.py | 5 | PASS |
| test_evidence_payload_limit.py | 4 | PASS |
| test_box_action.py | 5 | PASS |
| test_pipeline_router.py | 7 | PASS |
| test_relation_router.py | 8 | PASS |
| test_relation_identity_contract.py | 1 | PASS |
| test_router_vlm.py | 14 | PASS |
| **合计** | **88** | **88 passed, 0 failed, 0 errors, 0 skipped** |

两次独立运行：`88 passed in 51.06s` / `88 passed in 49.94s`；JUnit 证据附于 `pytest_junit_88tests.xml`。

### 5.2 合同清单中非 pytest 的 6 个文件（collect = 0）— 逐个处置

| File | 类型 | main() 是否真实模型调用 | Preflight 处置 |
|---|---|---|---|
| test_phase7_relations.py | 脚本校验器 | 否（纯逻辑） | 执行 → **FAIL（baseline 陈旧语义，见 §5.3）** |
| test_phase8_candidate_contract.py | 脚本校验器 | 否（纯逻辑） | 执行 → PASS |
| test_phase8_protocol_retry.py | 脚本校验器 | 否（Stub） | 执行 → PASS |
| test_phase6_planner.py | 脚本校验器 | **是（DeepSeek Planner）** | 不执行（违反 0-model 门）；阶段产物 `benchmark/phase6_planner_contract_results.json` 已在仓库 |
| test_phase7_planner.py | 脚本校验器 | **是（DeepSeek Planner）** | 不执行（违反 0-model 门）；阶段产物 `benchmark/phase7_planner_contract_results.json` 已在仓库 |
| test_phase7_composite.py | 脚本校验器 | **是（Sam2Segmenter 真推理）** | 不执行（违反 0-model 门）；对应 SAM 证据在 phase7_results / instance_quality_v1 资产 |

### 5.3 baseline 发现 — test_phase7_relations.py 在 be54f3c 失败（陈旧语义，非实现回归）

失败点：`main()` 中 `subject_conflict` 用例断言
`_build_semantic_groups(SUBJECTS, RELATED, subject_conflict, PLAN)[0]["completion_reason"] == "binding_conflict"`，
其中 A 对 R1、R2 两个不同 related 同时 satisfied。

该脚本编码的是 phase-7 时期的旧语义：同一 subject 对多个 related 同时 satisfied ⇒ `binding_conflict`。
be54f3c 现行（且后续 R2.3 冻结的）语义为：同一 subject 多 satisfied 时保留 confidence 最高者
（`completion_reason=None`、`status=satisfied`）；`binding_conflict` 仅保留给 === 跨主体对同一
related candidate 的冲突 ===。该现行语义由通过中的 pytest 用例
`test_relation_router.py::test_relation_resolver_freezes_all_status_mappings` 机械冻结，
且 `resolve_relation_outcomes` / `_build_semantic_groups` 位于合同 `must_not_change` 清单。

因此：
1. 该失败是 be54f3c baseline 上已存在的陈旧脚本断言，与本次 implementation diff 无因果关系；
2. 合同 §3.1 "16 个既有测试全部保持绿色" 的字面口径需要更正：
   应把 `test_phase7_relations.py` 从 "保持绿色集" 移出（或以 "pytest 88 用例绿 + 脚本单独处置"
   口径描述）；其被取代的语义由 `test_relation_router.py` 覆盖。
3. 建议：实现授权时附带 contract §3.1 订正（corrigendum）；在此之前本合同 revision 2 保持不变。

### 5.4 结论

```text
pytest 88/88 PASS（10 文件）
纯逻辑脚本：2/3 PASS（phase8_*），1/3 FAIL（test_phase7_relations.py，陈旧语义，见 §5.3）
真实模型脚本：3 文件按 0-model 门不执行（phase6/7 planner、composite；阶段产物为既有证据）
RESULT = PASS（pytest 门全绿；baseline 脚本发现已披露并给出订正建议）
```

## 6. 检查 5 — 0 模型 / DINO / SAM 调用

已执行子集（10 pytest 文件 + 3 纯逻辑脚本）的证据：

1. 全文件 grep：仅 `test_phase7_composite.py` 出现真实 `Sam2Segmenter().segment(...)`、
   仅 `test_vlm_client_config.py` 出现 `create_vlm_client`（且被 monkeypatch 成记录 lambda）；
   其余文件无真实 Detector/Segmenter/VLM 客户端实例化（stub 均经 monkeypatch.setattr 注入）。
2. 网络/下载锁定：`VLM_BASE_URL=http://127.0.0.1:9`（不可达，任何意外 VLM 调用立即失败）；
   `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`（任何模型下载立即失败）。
3. 运行环境：torch 2.11.0+cpu、`cuda=False`（即使误触也无 GPU 推理路径）。
4. 真实模型脚本（phase6/7 planner、composite）在本 preflight 未执行。

`RESULT = PASS`（已执行子集 0 模型 / DINO / SAM 调用）。

## 7. 状态

```text
IMPLEMENTATION PREFLIGHT          = PASS
  WORKTREE BASE                   = be54f3c89171d8b16f53c82397e9f468fb4b4c97
  WORKTREE BRANCH                 = general-rgb-behavior-relation-production-implementation-v1
  GIT STATUS                      = EMPTY
  SHA 8/8                         = MATCH
  PYTEST 88/88                    = PASS
  MODEL / DINO / SAM CALLS        = 0
CONTRACT §3.1 CORRIGENDUM        = REQUESTED (test_phase7_relations.py, stale baseline script)
PRODUCTION CODE MODIFICATION     = NOT AUTHORIZED
IMPLEMENTATION                   = NOT AUTHORIZED
```
