# TASK_CONDITIONED_SCENE_CONTEXT_BENCHMARK_V1

## 结论

`SCENE_CONTEXT_ARCHITECTURE = NEEDS_MORE_EVIDENCE`

Method B 是本轮最佳方法：23/36（63.89%），相较 Method A 的 18/36（50.00%）净增 5 条、提升 13.89 个百分点。它跨行为、空间/场景关系和污染语义产生了可复用改善，说明 Task-conditioned Structured Scene Context 值得进入合同研究；但 3/36 最终合同失败、3 条原本正确案例回退，以及 F1/F2 没有净提升，使其尚不足以直接批准 Production 接入。

## 当前 Production evidence architecture

- Planner 是纯文本 DeepSeek 调用，不看图片；输出 `target_object`、constraints、action、related_objects。
- 单个 `target_object` 直接作为 Grounding DINO query；当前 base 模型、threshold=0.3。
- subject validity 与 attribute 使用 SAM isolated PNG；behavior 使用围绕候选扩展 35% 的 PNG；relation 使用 full marked scene JPEG。
- VLM 执行语义验证；SAM2 仅依据 bbox 生成 mask；renderer 仅按最终 targets 绘制结果。
- 正式 relation 仅支持 `held_by_target`。本阶段未改变上述任一合同。

## 冻结集

- 36 cases；F1/F2/F4/P1/P3/P4 各 6。
- 包含 FAIL 14、FP 4、DEGRADED 2、PASS controls 8、TN controls 8。
- 冻结已有 60 个 DINO subject candidates；没有重新运行或修改 Detector。

## Semantic correctness

| Prompt | A Current | B Global | C Global+Candidate | D Marked Group |
|---|---:|---:|---:|---:|
| F1 | 3/6 (50.00%) | 3/6 (50.00%) | 3/6 (50.00%) | 1/4 (25.00%) |
| F2 | 4/6 (66.67%) | 4/6 (66.67%) | 3/6 (50.00%) | 1/2 (50.00%) |
| F4 | 3/6 (50.00%) | 5/6 (83.33%) | 5/6 (83.33%) | 1/2 (50.00%) |
| P1 | 3/6 (50.00%) | 5/6 (83.33%) | 4/6 (66.67%) | 1/2 (50.00%) |
| P3 | 2/6 (33.33%) | 3/6 (50.00%) | 3/6 (50.00%) | 1/2 (50.00%) |
| P4 | 3/6 (50.00%) | 3/6 (50.00%) | 2/6 (33.33%) | — |
| **Overall** | **18/36 (50.00%)** | **23/36 (63.89%)** | **20/36 (55.56%)** | **5/12 (41.67%)** |

## 相对 Method A 的迁移

- Method B：previous wrong → correct = 8；previous correct → wrong = 3；uncertain → correct = 3。
- Method C：previous wrong → correct = 5；previous correct → wrong = 3；uncertain → correct = 2。
- Method D（仅 12 条实验子集）：previous wrong → correct = 3；previous correct → wrong = 0。
- Method B：scene_context_wrong = 10；protocol_failure = 3。
- Method C：scene_context_correct_but_candidate_wrong = 3；scene_context_wrong_propagated = 10；protocol_failure = 3。

## Hallucination audit

- 审计全部 13 条 Method B 非正确结果，并抽查 12 条 Method B 正确结果，共 25 条。
- 其中 3 条协议失败没有可审计 scene facts；其余 22 条包含 77 个 task-relevant facts。
- 确认 1 个虚构事实：F2::fishing_012 把人物身边的鱼竿虚构为手持关系。
- per-fact hallucination rate = 1/77（1.30%）；case-level = 1/22（4.55%）。
- candidate identity confusion = 1：F4::fishing_008 把三个人的持竿关系都绑定到同一 E4。它没有改变该 case 最终判断，但说明当前 global graph 不具备可靠实例身份合同。

## 性能与缓存

- Method A：既有 Production 结果共 104 个 VLM contract attempts；36 条 Pipeline 总时长 2260.585s，其中 group verification 汇总 1805.205s。未重跑 Pipeline。
- Method B：36 个逻辑 scene contexts；44 个 contract attempts，8 retries、5 recovered、3 final contract failures；记录到 completion 的模型耗时 1310.997s。
- Method C：冻结候选 60 个；实际执行 54 个 candidate contracts、56 attempts（3 个 B 失败 case 无 context）；VLM 1021.152s，SAM evidence 再生成 69.867s。
- B+C 合计 100 个 contract attempts，记录的 VLM+SAM 耗时 2402.016s。Scene Context 已按 `image + prompt` 只生成一次并缓存复用，没有为每个 candidate 重发 full scene。
- Method D：12 calls，249.267s。
- 另有 2 次 502 transport failure 按完全相同请求重试成功；没有更改 prompt、模型或参数。

## 研究问题回答

1. 完整图 Task-conditioned Structured Scene Context 整体优于 current local-only evidence，但优势不均衡：主要来自 F4、P1、P3，F1/F2 无净提升，P4 持平。
2. 三种候选中 B 最佳。C 会继承 B 的错误/失败，并再次受候选局部证据限制；D 在 12 条中仅 41.67%，不适合作为当前 behavior 通用路径。
3. B 能解决一部分当前动作、岸边/水面、固定岩石/漂浮物和自然物/垃圾边界，但不能稳定解决“展示渔获 vs 当前垂钓”“身边鱼竿 vs 手持鱼竿”等细粒度关系。
4. 幻觉率低但非零；已观察到一次实体身份折叠。没有证据支持 Caption-first。

## 决策

- 支持继续研究 Task-conditioned Structured Scene Context：**YES**。
- 支持 Caption-first：**NO**。
- 建议现在接入 Production：**NO**。
- Phase 2 是否允许开始：**NO，需人工审查本 Phase 1 的 NEEDS_MORE_EVIDENCE gate 后决定**。
- 如人工决定补证据，范围应只针对冻结合同稳定性和跨类复现，不得按 case 调 prompt，也不得提前修改 Production。
