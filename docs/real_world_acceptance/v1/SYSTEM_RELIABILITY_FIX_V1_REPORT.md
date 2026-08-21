# SYSTEM_RELIABILITY_FIX_V1 — IMPLEMENTATION REPORT (FINAL)

最终 tested Production commit: **6ce8533d8a55b52e01d7daa30bce43139b5070b4**

implementation 历史(three commits on system-reliability-fix-v1):
- b1ea943  初始 payload normalization(18MiB safe cap, 4MP 首遍, telemetry)
- 2b6c2fe  强制 hard-cap invariant(超限即 RuntimeError, 绝不发送)
- 6ce8533  EOF housekeeping(仅补文件末尾换行, 无行为变化)

范围声明: 诊断报告曾列出多个候选方案(JPEG/WebP 编码策略、relation evidence 封顶、连接重试/timeout、provider/model 调整等); 正式 implementation freeze 最终**只选择 payload-bounded PNG normalization**，其余候选方案**未实施**。未改: 原始上传图片 resize / Detector 输入 / SAM 输入输出 / evidence 构造语义 / PNG→JPEG/WebP / relation evidence / timeout/retry / provider/model / Batch concurrency / API 上传限制。

## 1. 代码变更清单（仅 visual_agent/vlm.py + 新单元测试）

- `vlm.py` 新增 `import math`
- 序列化边界新增内部不变量常量: `EVIDENCE_PAYLOAD_SAFE_LIMIT = 18 * 1024 * 1024`(base64 payload 实际发送字节), `EVIDENCE_NORMALIZE_TARGET_PIXELS = 4_000_000`
- `_encode_png_data_url(PIL) -> (data_url, payload_bytes)`: 现有 PNG 编码 + 实测 payload
- `_normalize_evidence_payload(PIL) -> (data_url, telemetry)`: payload ≤ 18MiB 原样发送; 否则按比例缩小(保宽高比、禁止放大)到 4MP 首遍目标重编码, 仍超则 target_pixels 折半继续; 所有退出路径后 hard check: 最终 payload 仍 > 18MiB 一律 raise RuntimeError("failed to satisfy safe limit"), **绝不把超限 data-uri 返回 provider**(循环上限 64 次防死循环)
- `_pil_image_data_url` = 上述的入口包装(保持原签名); `_take_evidence_telemetry()` 取回最近一次编码遥测
- `verify_subject_instance` / `verify_candidate_constraints` 返回值 protocol 追加 `evidence_payload` 遥测 → 经 pipeline 落盘到 result.json 的 qwen_protocol.*
- 新增 `benchmark/test_evidence_payload_limit.py`(4 用例: 小图不触发 / 超限噪声图触发且 ≤上限 / 4MP 首遍目标 / **无法收敛必须 raise**), 全部通过

## 2. 修复回归：36 baseline SYSTEM FAILURE

环境: 当前云端模型、MAX_CONCURRENT_JOBS=1、冻结 prompt、同一 Batch API; 只跑原 36 条, 未重跑全 240。

| 基线 | 修复后 |
|---|---|
| 36 / 36 SYSTEM FAILURE | **36 / 36 pipeline success**(residual = 0) |

按测试: F1 2/2, F2 2/2, P1 7/7, P2 2/2, P3 8/8, P4 15/15 全部转为 success。

## 3. Payload telemetry 证明(非偶然成功)

- 36 任务共 84 次 Qwen evidence 调用; 55 次 normalization_triggered=True; **55 次全部对应 original_payload > 18MiB(1:1 命中)**; normalized_payload > 18MiB 违规 = 0。
- 之前 A1/A2 失败的 fishing_001(26.1MiB)/fishing_020(25.1MiB) 现触发 normalization → ~4MP(1675×2388 等, 宽高比保持)。
- 最大载荷案例: P4/pollution_009 77.6MiB → 2309×1732; P4/pollution_015.png 75.5MiB → 2449×1633 — 均收敛到 ≤ 18MiB。
- 小 evidence **不触发** normalization: P1/pollution_003(1.8MiB)、P3/pollution_022(5.5MiB)、P4/pollution_024(17.4MiB) trig=False — 行为保持原样。
- 归一化维度首遍 ≈ 4MP(如 2450×1633), 与冻结的 first-pass target 一致。

## 4. 结论与边界(FINAL)

- 最终硬性不变量: **任何发给 Qwen 的 PNG evidence payload > 18 MiB 必须本地失败, 绝不发送**; failure 需正常记为 SYSTEM FAILURE, 不重试掩盖。
- targeted 36/36 PASS(36 baseline SYSTEM FAILURE → 36/36 pipeline success)。
- **full 240 regression PASS**(240/240 pipeline success, 0 SYSTEM FAILURE; 原36→36/36, 原204→204/204; 639 calls / 65 triggered / 574 non-triggered / 1:1 / 0 violations / hard-cap RuntimeError=0)。
- 当前最终状态: targeted 36/36 PASS + full 240 regression PASS + **Production merge PENDING**(master@5075ab5 → 6ce8533, --ff-only)。
- 视觉 PASS/FAIL 不重新评分。

## 5. 文件

- `visual_agent/vlm.py`(改), `benchmark/test_evidence_payload_limit.py`(新)
- `_phase2/fix_v1_regression.json`(36 条状态+遥测), `_phase2/fix_v1_telemetry_summary.json`
- `_phase2/_fix36/<test>_<image>.json`(每成功任务 result.json 全量)