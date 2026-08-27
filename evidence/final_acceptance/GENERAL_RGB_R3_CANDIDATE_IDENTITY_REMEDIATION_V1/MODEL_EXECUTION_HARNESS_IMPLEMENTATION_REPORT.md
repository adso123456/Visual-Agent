# R3 Model Execution Harness — Implementation Report

## 状态

- Frozen contract: `local-vlm-quality-evidence-v1@4b6232cd87d0eb231be37039c6609b58a643c5ce`
- Builder review baseline: `0b32695dcd46d13cf22987f5347b2b212e7132c1`
- Harness branch: `general-rgb-r3-candidate-identity-benchmark-v1`
- Harness commit: `9a9e8f7e1a86317b91e5fc5ca232f60f769ed0b0`
- Review state: `IMPLEMENTED / NARROW CODE REVIEW REQUIRED`

## 新增文件

- `benchmark/r3_candidate_identity_v1/execution_harness.py`
- `benchmark/r3_candidate_identity_v1/EXECUTION_HARNESS_README.md`
- `benchmark/test_r3_model_execution_harness.py`

已审通过的 6 个 builder 文件没有修改；`visual_agent/*` 没有修改。

## 固化边界

- 直接调用 Production `verify_candidate_constraints()`，不复制或修改 behavior prompt、validator、`request_validated_json()` retry；
- preflight 强制核验 contract、selection、schedule 固定 SHA；
- 强制确认 `0b32695d...` 为当前 HEAD 祖先，并确认 6 个 builder 文件相对该 commit 没有 drift；
- mask/evidence manifest 自身 SHA、artifact SHA/bytes 以及与冻结 9-image SHA 集合的 coverage 全部核验；
- preflight receipt 自动写入结果 sidecar，每个 terminal record 保存 receipt SHA；
- first pass 固定两图；A/C uncertain fallback 固定三图 `isolated + local + full-scene`；B 无 fallback；
- 记录实际 model、provider、base URL、Production protocol、18 MiB/4 MP evidence telemetry、token、logical/request latency；
- provider/protocol/validator/evidence failure 分阶段写入 terminal record，并保留失败 telemetry；
- 已完成的 success/failed slot 继续按原 runner 规则跳过，不补跑、不覆盖。

## 测试结果

```text
python -m pytest benchmark/test_r3_model_execution_harness.py -q
13 passed in 1.05s

python -m pytest benchmark/test_r3_candidate_identity_builder.py benchmark/test_r3_model_execution_harness.py -q
30 passed in 0.96s

python -m pytest benchmark -q
128 passed in 23.73s
```

`git diff --cached --check` 通过。

## 明确未执行

- 未生成真实 SAM mask cache；
- 未创建真实模型执行入口；
- 未调用 Local VLM 或 Cloud VLM；
- 未运行 105+fallback Gate；
- 未修改或 merge Production；
- `GENERAL_RGB_FINAL_ACCEPTANCE_V2` 未授权；
- `REMOTE_SENSING_WATER_QUALITY` 继续保持 `BLOCKED`。
