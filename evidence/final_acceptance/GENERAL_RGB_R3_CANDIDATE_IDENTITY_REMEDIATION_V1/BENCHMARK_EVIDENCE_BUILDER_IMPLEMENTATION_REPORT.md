# R3 Benchmark-only Evidence Builder — Implementation Report

## 状态

- Contract source: `local-vlm-quality-evidence-v1@4b6232cd87d0eb231be37039c6609b58a643c5ce`
- Implementation branch: `general-rgb-r3-candidate-identity-benchmark-v1`
- Implementation commit: `0b32695dcd46d13cf22987f5347b2b212e7132c1`
- Base: `be54f3c89171d8b16f53c82397e9f468fb4b4c97`
- Review state: `IMPLEMENTED / CODE REVIEW REQUIRED`

## 实现范围

只新增以下 benchmark 文件：

- `benchmark/r3_candidate_identity_v1/evidence_builder.py`
- `benchmark/r3_candidate_identity_v1/mask_cache.py`
- `benchmark/r3_candidate_identity_v1/runner.py`
- `benchmark/r3_candidate_identity_v1/README.md`
- `benchmark/r3_candidate_identity_v1/__init__.py`
- `benchmark/test_r3_candidate_identity_builder.py`

实现内容：

- A/B/C 三种冻结 evidence 构造；
- 35% candidate-local crop；
- 非目标 person 固定 `45/55` 中性灰混合；
- target-overlap 优先与固定 `5px` 红 contour；
- 按输入图片 SHA-256 固定并复用 mask cache；
- evidence PNG 的 SHA-256、字节数、尺寸与 case manifest；
- 冻结 schedule 展开；
- uncertain-only A/C fallback，B 不执行 fallback；
- `fallback_harm` 机械分类；
- terminal result 保留、失败不补跑、已有 slot 不重新执行且不可覆盖。

## 验证结果

```text
python -m pytest benchmark/test_r3_candidate_identity_builder.py -q
17 passed in 0.32s

python -m pytest benchmark -q
115 passed in 21.95s
```

`git diff --cached --check` 通过，提交范围只有上述 6 个 benchmark 文件。

## 明确未执行

- 未调用 Local VLM 或任何远程模型；
- 未加载真实 SAM，单测仅使用注入的 stub segmenter/verifier；
- 未修改 `visual_agent/pipeline.py` 或任何 `visual_agent/*` Production 文件；
- 未运行正式 105-call Gate；
- 未 merge Production；
- 未授权 `GENERAL_RGB_FINAL_ACCEPTANCE_V2`；
- `REMOTE_SENSING_WATER_QUALITY` 继续保持 `BLOCKED`。

