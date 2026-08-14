# Manual ground-truth status

Status: `GT_FROZEN_VISION_REVIEW_DRAFTED`

- Ground truth is FROZEN for all 24 Test images (annotation_state=FROZEN, 24/24 COMPLETE, reviewed_by=human).
- Assistant vision-model candidate review is drafted for all 122 raw candidates
  (reviews/grounding_dino_base.json, review_source=assistant_vision_draft,
  schema-validated through CandidateReviewStore).
- Official baseline computed: reports/grounding_dino_base_v1.json / .md
  (Instance Recall 0.733, Instance Purity 0.685, Mixed-box Rate 0.098, Duplicate Rate 0.043).

Pending before official freeze:

1. Human confirmation of every candidate classification in the review tool
   (python -m benchmark.instance_quality_v1.annotation_tool --review).
2. Optional semantic downstream probe (needs DASHSCOPE_API_KEY) for
   Downstream Usability.
3. Update reviews/grounding_dino_base.json reviewed_by -> human and
   review_status -> COMPLETE after confirmation.

The frozen GT was NOT derived from detector output (per contract). The vision
review draft is an assistant aid and does not constitute official human review.
