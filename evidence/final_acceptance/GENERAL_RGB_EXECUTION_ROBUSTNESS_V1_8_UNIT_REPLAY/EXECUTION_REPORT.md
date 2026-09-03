# GENERAL RGB EXECUTION ROBUSTNESS V1 — 8-unit replay

```text
8-UNIT TARGETED REPLAY = PASS
FINAL ACCEPTANCE V4 = NOT RUN / NOT AUTHORIZED
```

- Implementation HEAD: `362a1a3f8352619d3967efb98828db950346de01`
- Terminal: `8/8`，unique: `8/8`，success: `8/8`。
- 每个 unit 只执行 1 次；无覆盖、补跑或替换。concurrency=1。
- Agent/VLM: `qwen3.8:27b-mtp-q4_K_M`，同一本地 OpenAI-compatible endpoint。
- Transport telemetry nodes: `35`；物理 attempts: `51`；retry: `0`；exhausted: `0`。本次均直接成功。
- `F2__fishing_001` 触发 hand fallback：subject view `4932×7032`，hand Detector 输入 `800×1141`，`hand_detector_resized=true`；无 MemoryError。
- `F2__fishing_002`：首次 Final Response 空，内容级第 2 次恢复成功；最终状态 `success`，`agent_response` 非空。
- `F4__fishing_007`：Final Response 首次成功，`agent_response` 非空。
- 本次未做视觉质量裁决，也不替代完整 Final Acceptance。

| Unit | Terminal | 秒 | Targets | Final Response | 非空文本 |
|---|---:|---:|---:|---|---:|
| F1__fishing_015 | success | 161.204 | 1 | success | yes |
| F1__fishing_016 | success | 53.069 | 1 | success | yes |
| F1__fishing_017 | success | 50.336 | 1 | success | yes |
| F1__fishing_018 | success | 29.488 | 0 | success | yes |
| F1__fishing_019 | success | 25.644 | 0 | success | yes |
| F2__fishing_001 | success | 79.093 | 0 | success | yes |
| F2__fishing_002 | success | 140.518 | 1 | success | yes |
| F4__fishing_007 | success | 253.363 | 1 | success | yes |
