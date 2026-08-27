# R3 Model Execution Harness — Audit Fix Report

## 提交

- Previous reviewed candidate: `9a9e8f7e1a86317b91e5fc5ca232f60f769ed0b0`
- Audit fix commit: `b35bde57ca8f60699d95edc64101451695eacdc1`
- Review-lock commit / branch HEAD: `22b22570c5f9ac6bd5249dae8f70782f500fb810`
- Branch: `general-rgb-r3-candidate-identity-benchmark-v1`
- Review state: `CHANGES IMPLEMENTED / NARROW RE-REVIEW REQUIRED`

## Blocking 1：Harness code identity

- review-lock 固定 `b35bde57...` 为 `harness_review_sha`；
- 固定 builder `0b32695d...` 与 Production base `be54f3c...`；
- 固定 harness、测试、README、execution bindings 的 SHA-256 与 bytes；
- preflight 检查 reviewed commit ancestry、commit-to-HEAD drift；
- `benchmark/` 与 `visual_agent/` working tree 非 clean 时拒绝执行；
- receipt 分别记录 builder SHA、harness SHA、review-lock SHA。

Review-lock SHA-256：

```text
eff9212667c79ec6fe14c36cad1f43e847f59a200de052823a1e8f319e07c10f
```

## Blocking 2：Frozen Local VLM config

任何 client 创建前强制：

```text
model   = qwen3.8:27b-mtp-q4_K_M
baseURL = http://192.168.250.9:11434/v1
timeout = 120
```

任一字段不一致均产生 `preflight / frozen_vlm_config`，测试确认 model client 调用数为 0。

## Blocking 3：Case / constraint / evidence binding

- `frozen_execution_bindings.json` 固定 9 个 case 的 prompt、semantic constraint、image SHA 与 candidate IDs；
- 文件 SHA 进入 review-lock；
- preflight 与冻结 selection 逐 case 比较；
- mask manifest 必须逐 case 对应 image SHA、candidate ID、bbox；
- evidence manifest 必须逐 case 对应 case ID、source image SHA、candidate IDs；
- `ManifestEvidenceProvider` 只能从 preflight receipt 获取 case manifest，不再接受外部可交换 map。

## Blocking 4：Actual slot schedule binding

- preflight 直接用冻结 selection + schedule 调用 `expand_schedule()`；
- receipt 固定 scheduled slot count、完整 slot payload sequence SHA 和 slot IDs；
- `run_harness_slots()` 不再接受外部 slots，只执行 receipt 中的冻结 slots；
- slot count 或 sequence SHA 不一致时，在 verifier 调用前失败。

## 测试

```text
python -m pytest benchmark/test_r3_model_execution_harness.py -q
15 passed in 1.12s

python -m pytest benchmark/test_r3_candidate_identity_builder.py benchmark/test_r3_model_execution_harness.py -q
32 passed in 1.02s

python -m pytest benchmark -q
130 passed in 23.33s
```

`git diff --check 9a9e8f7..22b2257` 通过；reviewed harness files 相对 `b35bde5` 零 drift；`visual_agent` 相对 `be54f3c` 零 drift；worktree clean。

## 未授权事项

- 未生成真实 SAM cache；
- 未调用 Local/Cloud VLM；
- 未执行 105+fallback Gate；
- 未修改或 merge Production；
- Remote Sensing Water Quality 继续 `BLOCKED`。
