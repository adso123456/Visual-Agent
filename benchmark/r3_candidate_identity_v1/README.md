# R3 Candidate Identity Benchmark Builder V1

本目录只实现冻结合同所需的 benchmark evidence、固定 mask cache、schedule 展开和不可替换的结果记录。

- 不创建或调用 VLM、Planner、Final Response。
- 不接入 `visual_agent/pipeline.py`。
- A/B/C 的 35% crop、45/55 灰度混合、target-overlap 优先和 5px 红色 contour 均为固定算法。
- mask 由外部注入的 segmenter 一次生成，之后按图片 SHA-256 缓存并校验复用。
- first-pass 只有 `uncertain` 可触发 A/C fallback；B 无 fallback。
- 每个冻结 slot 只能写入一次 terminal record，失败不补跑、不替换。

当前阶段只允许以 stub/mock 运行单元测试；模型执行仍未授权。
