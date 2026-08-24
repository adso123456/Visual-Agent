# LOCAL_VLM_QUALITY_COMPARISON_V1 — Evidence Report

本分支保存人工盲评的原始评分、私有解盲映射、冻结需求以及逐 case 原始字节证据。所有模型评价均由人工 A/B grade 机械解盲汇总；未重新评分，也未自动解释 note。

## Evidence integrity

- Cases: 232（Positive 115 / Negative 117）
- Binary evidence: 696 files / 3248974817 bytes
- Human notes: 74
- Frozen contract SHA-256: 977b1d85703204d5cc752d3ba7807eec95da6ffdee25053409afe458dbc7cf4d
- Original blinded scores SHA-256: e998bd352117bccc8fe1ae9fa6d7cee0ba8dc1b74539007a87866c5d033c4a79
- Private blinding map SHA-256: 4b5224f31b8625cfed14909be36f88aea4b4d697fab272bfb890199d1e4c986b
- blinded_scores.json 是人工评分原始来源；evaluation.json 仅是可追溯解盲视图。
- 图片按源文件逐字节复制，未压缩、缩放或转格式；每条 SHA-256 记录在 manifest.json。

## Human adjudication summary

| Model | Positive PASS | Positive DEGRADED | Positive FAIL | Positive usable | Negative TN | Negative FP | VISION_FAILURE |
|---|---:|---:|---:|---:|---:|---:|---:|
| Local | 56 | 19 | 40 | 75/115 (65.22%) | 101 | 16 | 56 |
| Cloud | 56 | 19 | 40 | 75/115 (65.22%) | 101 | 16 | 56 |

## Per-prompt grade counts

### F1 — 框出正在钓鱼的人

| Model | PASS | DEGRADED | FAIL | TN | FP |
|---|---:|---:|---:|---:|---:|
| Local | 10 | 4 | 5 | 5 | 5 |
| Cloud | 11 | 4 | 4 | 6 | 4 |

### F2 — 把拿着鱼竿的人描边

| Model | PASS | DEGRADED | FAIL | TN | FP |
|---|---:|---:|---:|---:|---:|
| Local | 8 | 3 | 5 | 10 | 2 |
| Cloud | 10 | 3 | 3 | 11 | 1 |

### F3 — 框出桶

| Model | PASS | DEGRADED | FAIL | TN | FP |
|---|---:|---:|---:|---:|---:|
| Local | 1 | 0 | 2 | 25 | 1 |
| Cloud | 1 | 0 | 2 | 25 | 1 |

### F4 — 把拿着鱼的人标出来

| Model | PASS | DEGRADED | FAIL | TN | FP |
|---|---:|---:|---:|---:|---:|
| Local | 7 | 0 | 1 | 18 | 1 |
| Cloud | 6 | 1 | 1 | 15 | 4 |

### P1 — 框出水面上的垃圾

| Model | PASS | DEGRADED | FAIL | TN | FP |
|---|---:|---:|---:|---:|---:|
| Local | 10 | 2 | 5 | 10 | 3 |
| Cloud | 9 | 2 | 6 | 11 | 2 |

### P2 — 高亮漂浮的塑料瓶

| Model | PASS | DEGRADED | FAIL | TN | FP |
|---|---:|---:|---:|---:|---:|
| Local | 3 | 2 | 1 | 24 | 0 |
| Cloud | 3 | 2 | 1 | 24 | 0 |

### P3 — 描边水中的漂浮物

| Model | PASS | DEGRADED | FAIL | TN | FP |
|---|---:|---:|---:|---:|---:|
| Local | 9 | 6 | 11 | 1 | 2 |
| Cloud | 10 | 4 | 12 | 1 | 2 |

### P4 — 标出水面污染区域

| Model | PASS | DEGRADED | FAIL | TN | FP |
|---|---:|---:|---:|---:|---:|
| Local | 8 | 2 | 10 | 8 | 2 |
| Cloud | 6 | 3 | 11 | 8 | 2 |

## Traceability

每个 case 目录包含冻结 requirement、original、Local output、Cloud output 和 evaluation.json。原始 note 原样保存在对应 evaluation.json，未进行机器归纳或改写。
