# Gate R 执行合同澄清

## Relation evidence normalization

Gate R 原样复用 `visual_agent.relations.verify_relations()`。该 Production 路径通过
`_marked_scene_data_url()` 生成 full-scene marked JPEG data URI，并未调用
`visual_agent.vlm.py` 的 18 MiB PNG evidence normalization。

因此本阶段冻结为：

```text
RELATION VERIFY PATH
= EXISTING PRODUCTION verify_relations()

RELATION EVIDENCE
= FULL-SCENE MARKED JPEG DATA URI

18 MiB PNG NORMALIZATION
= NOT APPLICABLE TO CURRENT PRODUCTION RELATIONS PATH
```

Gate R runner 不新增 normalization，不改变 JPEG quality、标框方式、system/user prompt、
validator、retry、三态合同或 OpenAI-compatible wire format。

## 执行授权

执行授权由同目录 `GATE_R_EXECUTION_AUTHORIZATION.json` 单独承载。原 Gate L 冻结合同
字节保持不变；authorization artifact 绑定：

- Gate L evidence：`3308fee09ac2d3fa827f81854c1d556a0b4c87f6`
- reviewed runner：`c6451a710e929116ee0941b2befc1ce223128232`
- Arm B / C：各 5 次，共 10 个 slots
- failed execution replacement：`false`
- Production modification：`false`
