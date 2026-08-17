# Manual ground-truth status

Status: `GROUNDING_DINO_BASELINE_V1_1_FROZEN`

- Ground truth is FROZEN for all 24 Test images (annotation_state=FROZEN, 24/24 COMPLETE, reviewed_by=human).
- Human Candidate Review is COMPLETE for all 122 raw candidates；用户已明确接受
  Codex manual visual audit as final human confirmation。
- Benchmark v1.0 is `REVOKED_GT_OMISSION`。v1.1 补入 37 个经原图确认的真实目标，
  GT 86 → 123，Candidate Review AMBIGUOUS 37 → 0。
- Detector-only official baseline v1.1: Recall 0.821138，Purity 0.827869，Small
  Recall 0.901961，Partial Recall 0.741379，Heavy Occlusion Recall 0.8，
  Duplicate 0.040984，Mixed 0.098361，False Detection 0。
- Semantic constraint spec is FROZEN and bound to GT/raw/review. Formal semantic
  result: 43 correct / 4 VLM semantic limit / 75 detector downstream unusable；
  Semantic Downstream Usability = 0.914894。
- Phase 12 Base Baseline v1.1 is FROZEN；Local Detector A/B may start only from v1.1。

The frozen GT was NOT derived from detector output (per contract). The vision
review provenance is recorded in reviews/grounding_dino_base.json and
reviews/manual_visual_audit_v1.json.
