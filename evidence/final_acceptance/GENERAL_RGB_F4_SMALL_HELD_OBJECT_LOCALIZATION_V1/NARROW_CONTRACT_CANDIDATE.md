# GENERAL_RGB_F4_SMALL_HELD_OBJECT_LOCALIZATION_V1

## 状态

```text
NARROW CONTRACT FREEZE CANDIDATE
= REVIEW REQUIRED

CODE MODIFICATION
= NOT AUTHORIZED

DETECTOR / VLM EXECUTION
= NOT AUTHORIZED

PRODUCTION MODIFICATION / MERGE
= NOT AUTHORIZED
```

本合同候选只回答：能否通过少量、统一、确定性的局部定位视图，让
`F4::fishing_017.jpeg` 中主体手里可见的小鱼进入 related-object candidate universe。

它不修改 `held_by_target` 语义，不研究 `fishing_020`，也不确认完整 Relation Production policy。

## Frozen input candidate

- Case：`F4::fishing_017.jpeg`。
- Prompt：`把拿着鱼的人标出来`。
- Image SHA-256：`2ca02d15f8799d620598751ef299851915f91fe094d863a5f7cf51f6b50f0c99`。
- Image size：`2260 × 3390`。
- Subject：A，bbox `[3.93, -13.14, 1140.06, 2078.16]`。
- Requested related object：`fish`。
- Relation：`held_by_target`。
- Current fixed 35% subject crop：`[0, 0, 1538, 2811]`。
- 人工 reference region 候选：`[880, 680, 1040, 860]`；reference center：`[960, 770]`。

reference region 只标识手中目标小鱼，不包含桶内鱼。它属于本次合同审查项；合同冻结后不得根据检测结果移动。

## Common detector contract

- Detector：现有 `IDEA-Research/grounding-dino-base`。
- `box_threshold = text_threshold = 0.30`。
- 不更换模型、不调整 threshold、不追加 aliases。
- 原图 initial related-object grounding 保持现有 Production 结果与路径，不修改 Detector 主路径。
- 所有局部检测 bbox 必须确定性 remap 回原图坐标。
- 同一 Arm 内候选按 `confidence desc, x1, y1, x2, y2` 排序；IoU `>= 0.80` 的重复框只保留排序靠前者。
- 保存每个输入 view 的原始 PNG bytes、SHA-256、crop bbox、query、raw detections 和 remapped detections。

## Arms

### Arm A — CURRENT CONTROL

- View：现有 35% subject crop `[0, 0, 1538, 2811]`。
- Query：`fish`。
- Detector calls：1。
- 作用：复现当前 R2.3 secondary grounding，不作为新机制。

### Arm B — FIXED OVERLAPPING FINE-SCALE TILES

只把 Arm A 的固定 crop 划成 2×2 tiles；每个 tile 宽高均为 base crop 的 60%，相邻 tile 在各轴重叠 20%。
取整固定为起点 `floor`、终点 `ceil`，得到原图坐标：

1. `[0, 0, 923, 1687]`
2. `[615, 0, 1538, 1687]`
3. `[0, 1124, 923, 2811]`
4. `[615, 1124, 1538, 2811]`

每个 tile 只查询 `fish`，Detector calls 固定为 4。禁止看到结果后改变 tile 数量、重叠或顺序。

### Arm C — DETERMINISTIC HAND-CONDITIONED VIEW

1. 在 Arm A base crop 上使用同一 Detector 查询 `hand`，threshold `0.30`。
2. 将 hand bbox remap 到原图；只保留 bbox center 位于 subject A bbox 内的 hand detections。
3. 按 `confidence desc, x1, y1, x2, y2` 排序，最多保留前 2 个。
4. 每个 hand bbox 在四边各扩展自身 width/height 的 100%，clamp 到 Arm A base crop；取整使用
   `floor(x1/y1)`、`ceil(x2/y2)`。
5. 完全相同的 crop 去重；每个保留 crop 查询一次 `fish`，threshold `0.30`。

Detector calls 最大为 3：1 次 `hand` 加最多 2 次 `fish`。hand 未检出时不得换 query、降 threshold 或回退人工 crop；
该 Arm 直接记录 `NO_HAND_VIEW`。

## Localization adjudication

一个 remapped fish detection 只有同时满足以下机械条件，才记为 `TARGET_SMALL_FISH_LOCALIZED`：

1. bbox 包含 reference center `[960, 770]`；
2. bbox 与 reference region `[880, 680, 1040, 860]` 的 IoU `>= 0.10`；
3. bbox center 位于 reference region 内。

所有其他 fish detections 记录为 non-target candidates；不得因视觉上“接近手”人工升级为 target。

本 Gate 的 primary metric 是正确目标是否进入 candidate universe；同时报告 target candidate bbox/confidence、
non-target candidate 数、Detector calls、view 数和每个 view 延迟。

## Sequential Gate

### Gate L — Localization

- Arm A/B/C 各执行一次；Grounding DINO 为 eval/inference 模式，不做随机重复。
- raw failure 保留，不补跑、不调参。
- 若 Arm B 与 Arm C 都没有 `TARGET_SMALL_FISH_LOCALIZED`：

```text
SMALL_HELD_OBJECT_LOCALIZATION_MECHANISM
= NOT FOUND / CLOSED
```

此时不得调用 Relation VLM，也不得继续设计更宽松 verifier。

- 只有成功定位目标的 B/C Arm 才能进入 Gate R；Arm A 只作 control。

### Gate R — Existing held verifier（后续、单独授权）

Gate R 不在本轮执行授权内。若 Gate L 成功，后续仍必须使用现有 Production：

- `verify_relations()` system/user prompt；
- full-scene JPEG marked binding evidence；
- `held_by_target` 三态合同；
- validator、retry、18 MiB normalization、Local VLM 配置。

每个 Gate-L-successful Arm 执行 5 次独立 relation calls；同次 call 包含 subject A、现有 full-scene
R1–R4 与该 Arm 的局部 remapped candidates，完成完整 S×R matrix。失败保留，不补跑。

Gate R 只有全部满足才确认该 Arm 的机制：

1. 目标小鱼 candidate `satisfied >= 4/5`；
2. 所有 non-target 桶内/桶边鱼 `satisfied = 0`；
3. subject A retained `>= 4/5`；
4. provider/protocol/validator/evidence final failure = 0；
5. failed execution replacement = false。

通过时唯一允许的结论是：

```text
F4_SMALL_HELD_OBJECT_LOCALIZATION_AND_BINDING_MECHANISM
= CONFIRMED
```

不得写成 Relation Production policy 或 Final Acceptance confirmed。

## Prohibitions

- 不修改 Production、Planner、subject validity、ownership resolver、relation prompt/validator。
- 不改变 initial full-scene Detector 路径、模型、query、threshold。
- 不加入 `fishing_020` 或其他 case。
- 不根据结果移动 reference region、改变 tiles、hand crop margin 或 top-k。
- 不把未定位正确小鱼但被 VLM 猜为持有的结果算成功。
- 不 merge、不建立 Final Acceptance V2、不解除 Remote Sensing blocker。
