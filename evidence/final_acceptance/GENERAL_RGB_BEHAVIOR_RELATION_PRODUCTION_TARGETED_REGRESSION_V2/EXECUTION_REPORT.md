# General RGB Production Targeted Regression V2

- Implementation: `d0fe68576d3d613c52a4f28011c0f8fa8a0f421c`
- Execution: 34/34 success, 0 error
- Provider/protocol/validator final failures: 0/0/0
- VLM calls: 129; tokens: 414327

## Gates

- System: PASS
- Behavior: FAIL
  - Challenge safety: FAIL
  - F1 candidate/task: 4/10, 3/6; regression 0/0
  - New false assignment: 6
    - `challenge_001` candidate `A`: uncertain -> satisfied
  - Fallback harm: 0
- Relation: PASS
  - F4::017 retained/fallback/non-target FP: 5/5, 5/5, 0
  - F2::005 fallback/retained/satisfied binding: 5/5, 0, 0
  - F2::024/core_003 retained: True/True
  - core_014 targets/satisfied binding: 0/0

## Final

`JOINT TARGETED REGRESSION = FAIL`
