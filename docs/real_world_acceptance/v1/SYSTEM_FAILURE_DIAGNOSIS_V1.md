# SYSTEM RELIABILITY 只读诊断 V1 — 36 条 SYSTEM FAILURE 代码路径与阶段归因

范围: 只读诊断, 未修改任何 Production 文件, 未重跑 case, 未对 36 条 baseline 做任何处理。

## 1. 真实调用链（upload → run_pipeline → provider）

上传原图 → api/storage(JobManager) → run_pipeline(image_path, prompt)：

1. DeepSeekAgent.plan_request(prompt) — 纯文本 Tool Call, **不含图片** (deepseek_agent.py, api.deepseek.com, deepseek-v4-pro; 重试 2 次即 deepseek_agent.py:72 `range(1,3)`)。
2. Detector: grounding.py `Image.open` 原图 → Grounding DINO Base 本地 (GPU), 模型内部自有 preprocessing, **与云端载荷无关**。
3. SAM2 分割: segmentation.py 原图坐标, mask 为原生分辨率, 本地。
4. **逐候选语义验证（Qwen / DashScope, qwen3-vl-flash）— 36 条失败的所在阶段**:
   - pipeline.py `if constraints and runtime_candidates and verify:` 门控 (≈line 354);
   - evidence.py: `build_isolated_instance_evidence` → **全幅原生分辨率**, 仅候选区保留像素其余中性灰 (line 19-32);
   - evidence.py: `build_behavior_evidence` → **原生分辨率 bbox+35% 局部裁剪** (line 34-56);
   - vlm.py `_pil_image_data_url` → 直接 **PNG 编码 → base64 data-uri, 无任何尺寸上限** (vlm.py:28); 调用点 verify_subject_instance (vlm.py:129) / verify_candidate_constraints (vlm.py:242);
   - relations.py `_marked_scene_data_url` → 全分辨率 **JPEG q90** data-uri, 只做 ≥1024 放大不缩小 (relations.py:31-47) — 仅 relation 路由 (F4 类) 使用。
5. 渲染/结果汇总: renderer 本地; DeepSeek build_final_response 仅文本汇总 (无图片)。

## 2. 36 条失败阶段归因（不变量: 全部位于 Qwen 证据载荷路径）

| 错误族 | 条数 | 触发阶段 | 证据 |
|---|---|---|---|
| A1 data-uri 20MiB (decoded bytes cap) | 15 | Qwen 逐候选验证调用 (verify_subject_instance / verify_candidate_constraints) | 原生分辨率证据 PNG 解码字节 > 20,971,520 — 与 images 原生 PNG 编码体积高度正相关 (见 §4) |
| A2 string-length ~28M chars | 9 | 同一 Qwen 调用路径 | DashScope 对同 payload 的字符串长度校验 (`String value length (28,049,408)…`) |
| B APIConnectionError | 12 | Qwen client (openai → dashscope compatible-mode) 传输层 | 与 A 类同一超大 payload 群体 (send-big-body 时连接中断; openai 默认 read=600s/max_retries=2 后仍失败) |

结论: 24(A) + 12(B) 共 36 条, **没有一条来自 Detector/SAM/API storage/DeepSeek 阶段**; A2 与 A1 是同一载荷被 provider 两个不同校验命中的表现, B 是同一载荷的传输层表现。

## 3. 为什么同一张图有的 prompt 成功、有的失败（机制, 代码级）

- F3 (框出桶): plan.constraints=[] → pipeline **跳过整个逐候选 Qwen 验证块** → 对大图零图片调用 → 30/30 成功。
- F1/F2 (正在钓鱼/手持鱼竿 → behavior/attribute 约束): 每个候选触发 `verify_subject_instance`(全幅隔离 PNG) + `verify_candidate_constraints`(行为裁剪 PNG) → 大图证据超限 → A1/A2。
- F4 (拿着鱼 → relation 路由): 无 behavior/attribute 证据 PNG; 主体有效性用隔离图(灰色背景 PNG 压缩好); relation 图用 JPEG q90 (大图也约 ≤8MB) → 30/30 成功。
- P1/P3/P4 (水面/漂浮/污染区域): 大尺寸候选区域(藻华/垃圾/水域) → evidence 原生 PNG 最大 → A1/A2/B 集中; P4 最多(15)。

## 4. 载荷体积实证（失败图像的原生全幅 PNG → base64 估计）

| 失败图(节选) | 分辨率 | 文件 | 全幅PNG | base64 估 | 类别 |
|---|---|---|---|---|---|
| pollution_015.png | 6960x4640 | 64.3MB | 64.1MB | ~85MB | B(P4) |
| pollution_009.jpeg | 9660x7245 | 7.5MB | 68.4MB | ~91MB | B(P4)/A1(A-P3) |
| pollution_006.jpeg | 9660x7245 | 6.7MB | 62.0MB | ~83MB | B(P4) |
| fishing_001.jpeg | 5152x7728 | 2.7MB | 22.0MB | ~29MB | A1(F1,F2) |
| fishing_020.jpeg | 3840x5760 | 2.2MB | 19.7MB | ~26MB | A1(F1,F2) |
| (其余成功的大图) | <~18MB 全幅PNG | | | | 均未出现 A1/A2 |

判据: baseline 中**所有** A1/A2 失败图像的全幅原生 PNG 均 ≥ ~18.6MB; 小图无此失败 = 载荷体积与 provider caps 精确对应。

## 5. 当前 timeout / retry 现状

- openai SDK 默认(所有 client 均未覆盖): timeout connect=5s / read=600s / write=600s / pool=600s; max_retries=2 → 12 条连接错误是在 SDK 自动重试 2 次之后仍然失败。
- qwen_protocol.py MAX_ATTEMPTS=2: 仅结构/格式重试一次(与传输无关)。
- deepseek plan_request: 契约重试 2 次(无图片)。
- 代码中没有任何证据载荷尺寸上限/缩放策略; `_image_data_url`(整文件 base64)与 `verify_candidates`(全场景标注图)当前是未调用死代码。

## 6. 修复建议范围（本阶段只诊断, 不实施）

定点修复只针对云端 Qwen evidence/payload, 不破坏原图与 Detector/SAM 输入:
1. evidence 图片(隔离图/行为裁剪)编码前加尺寸上限(如长边 ≤1280px 或字节预算), PNG 改为按内容 JPEG/WebP 混合;
2. relations._marked_scene_data_url 增加与 1 一致的封顶(当前只放大不缩小);
3. 连接类: 针对 send-big-body 场景显式 read timeout / 重试策略, 不依赖 SDK 默认;
4. 明确不动: grounding.py / segmentation.py / 原图 / prompt / action 语义 / F3 类无约束路径;
5. 后续 SYSTEM_RELIABILITY_FIX_V1 实施后按同 contract 跑回归, 保留 baseline→fix→regression 历史。

## 7. 停止条件已达成

36 条 SYSTEM FAILURE 的真实代码路径与失败阶段归因已取得(A1/A2/B 全部=Qwen 证据载荷路径, 24+12 同一根因族); 本阶段到此停止, 未修改任何 Production 文件。