# ARCHITECTURE_DECISION

## Decision

`SCENE_CONTEXT_ARCHITECTURE = NEEDS_MORE_EVIDENCE`

保留 Method B（每个 image + prompt 一次 Task-conditioned Structured Scene Context）作为唯一后续候选；拒绝 Method C 作为默认路径，拒绝 Method D，拒绝 Caption-first。

理由：Method B 从 50.00% 提升到 63.89%，且在 F4、P1、P3 均有跨任务改善；但 F1/F2 无提升、3 个合同失败、3 个 control/原正确案例回退，尚不满足“低 regression + 稳定 contract”的 Production gate。

Scene Context 必须缓存于 `image + prompt` 粒度。候选验证只能读取缓存结构，不能每个 candidate 重跑完整图片。当前候选 schema 中的实体 ID 不能视为可用于 Production binding 的可靠身份合同。
