# General RGB Production Targeted Regression V1

- Implementation: `2398ae9e31e8f053541a24bde56b2e0eb9b01990`
- Execution: 34/34 success, 0 error
- Provider/protocol/validator final failures: 0/0/0
- VLM calls: 133; tokens: 403801

## Gates

- System: PASS
- Behavior: FAIL
  - Challenge safety: PASS
  - F1 candidate/task: 5/10, 3/6; regression 0/0
  - New false assignment: 1
    - `F1::fishing_014.jpeg` candidate `B`: uncertain -> satisfied
  - Fallback harm: 0
- Relation: PASS
  - F4::017 retained/fallback/non-target FP: 5/5, 5/5, 0
  - F2::005 fallback/retained/satisfied binding: 5/5, 0, 0
  - F2::024/core_003 retained: True/True
  - core_014 targets/satisfied binding: 0/0

## Final

`JOINT TARGETED REGRESSION = FAIL`
