# General RGB Production Targeted Regression V3

- Implementation: `aed1e3e6acb537480664b89531a9bc12a29d708f`
- Execution: 34/34 success, 0 error
- Provider/protocol/validator final failures: 0/0/0
- VLM calls: 140; tokens: 428525

## Gates

- System: PASS
- Behavior: PASS
  - Challenge safety: PASS
  - F1 candidate/task: 5/10, 3/6; regression 0/0
  - New false assignment: 0
  - Fallback harm: 0
- Relation: PASS
  - F4::017 retained/fallback/non-target FP: 5/5, 5/5, 0
  - F2::005 fallback/retained/satisfied binding: 5/5, 0, 0
  - F2::024/core_003 retained: True/True
  - core_014 targets/satisfied binding: 0/0

## Final

`JOINT TARGETED REGRESSION = PASS`
