## Segmentation 证据：SAM mask 优于纯 bbox（PRD §23）

对比图（左=bbox 矩形，右=SAM mask 轮廓）：

- `docs/evidence/sam_vs_bbox_outline.jpg`：outline 操作。右侧红色轮廓严格贴合
  人物 silhouette（头/肩/臂/腿），左侧矩形框包含大量背景（河水、石头）。
- `docs/evidence/sam_vs_bbox_dim.jpg`：dim_background 操作。右侧仅人物形态区域
  保持明亮，左侧矩形区域含非人物内容。

生成方式：对 `images/test_images/test_fishing.jpg` 的第一个 person 候选，
分别用 bbox 与 SAM2 mask 执行同一 Action，并排对比。
