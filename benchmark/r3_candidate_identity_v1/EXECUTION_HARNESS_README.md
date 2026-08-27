# R3 Model Execution Harness

本 harness 只把冻结的 benchmark evidence 接到现有 Production behavior verifier：

- 直接复用 `visual_agent.vlm.verify_candidate_constraints()`，不复制 prompt、validator 或 retry；
- 调用前核验 contract、selection、schedule、builder implementation 和全部 mask/evidence manifest；
- 将 preflight receipt 固化为结果 sidecar，并在每条 terminal record 保存 receipt SHA；
- first pass 使用 isolated + local；A/C uncertain fallback 使用 isolated + local + full-scene；
- 记录实际 model/provider/base URL、protocol attempts/retry/recovered、evidence normalization、token 和 latency；
- provider/protocol/validator/evidence failure 分阶段保留，失败 slot 不补跑、不覆盖。

当前没有提供真实执行入口。只有 stub/mock 单测获准；真实 SAM cache 和 Local VLM 调用仍未授权。
