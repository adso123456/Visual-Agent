# R3 Model Execution Harness

本 harness 只把冻结的 benchmark evidence 接到现有 Production behavior verifier：

- 直接复用 `visual_agent.vlm.verify_candidate_constraints()`，不复制 prompt、validator 或 retry；
- 调用前核验 contract、selection、schedule、builder、reviewed harness、Production verifier 与 working tree；
- 强制 Local VLM model/base URL/timeout 等于冻结值，错误配置在 client 创建前失败；
- `frozen_execution_bindings.json` 固定 case → prompt → semantic constraint → image → candidates；
- case-keyed mask/evidence manifest 必须与冻结 case、图片、bbox、candidate IDs 一一对应；
- 实际执行 slots 只能来自冻结 selection + schedule 展开结果，并固化 105-slot 顺序 SHA；
- 将 preflight receipt 固化为结果 sidecar，并在每条 terminal record 保存 receipt SHA；
- first pass 使用 isolated + local；A/C uncertain fallback 使用 isolated + local + full-scene；
- 记录实际 model/provider/base URL、protocol attempts/retry/recovered、evidence normalization、token 和 latency；
- provider/protocol/validator/evidence failure 分阶段保留，失败 slot 不补跑、不覆盖。

当前没有提供真实执行入口。只有 stub/mock 单测获准；真实 SAM cache 和 Local VLM 调用仍未授权。
