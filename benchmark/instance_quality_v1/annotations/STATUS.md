# Manual ground-truth status

Status: `GROUNDING_DINO_BASELINE_V1_FROZEN`

- Ground truth is FROZEN for all 24 Test images (annotation_state=FROZEN, 24/24 COMPLETE, reviewed_by=human).
- Human Candidate Review is COMPLETE for all 122 raw candidates；用户已明确接受
  Codex manual visual audit as final human confirmation。
- Detector-only official baseline: Recall 0.744186，Purity 0.752941，Small Recall
  0.75，Partial Recall 0.6875，Heavy Occlusion Recall 0.333333，Duplicate 0.058824，
  Mixed 0.141176，False Detection 0。
- Semantic constraint spec is FROZEN and bound to GT/raw/review. Formal semantic
  result: 43 correct / 4 VLM semantic limit / 75 detector downstream unusable；
  Semantic Downstream Usability = 0.914894。
- Phase 12 Base Baseline v1 is FROZEN；Local Detector A/B may start from this SHA。

The frozen GT was NOT derived from detector output (per contract). The vision
review provenance is recorded in reviews/grounding_dino_base.json and
reviews/manual_visual_audit_v1.json.
