# CONTEXT_EVIDENCE_POLICY_HARDENING_V1 — Frozen Contract

## Status

```text
CONTEXT_EVIDENCE_POLICY_HARDENING_V1 = CONTRACT FROZEN
PRODUCTION MODIFICATION = NOT AUTHORIZED
GENERAL_RGB_FINAL_ACCEPTANCE_V1 = PENDING
REMOTE_SENSING_WATER_QUALITY = BLOCKED
```

## Evaluation set

- 25 frozen real-image cases.
- General RGB F1/F2/F4: 18 cases from the existing context-sensitive frozen set.
- Demo Acceptance: `core_011`, `challenge_005`, `challenge_001`, `challenge_003`, `challenge_004`, `core_003`, `core_014`.
- Pollution P1–P4: excluded.
- Existing Production Detector candidates/bindings are frozen; this phase does not re-evaluate Detector recall.

## Arms

### A — Current Production

- attribute: isolated candidate PNG.
- behavior: 35% candidate-local PNG with current-instance contour.
- relation: full-scene marked JPEG binding evidence.

### B — A + Simplified Global Facts

- Candidate-specific evidence is byte/semantic-equivalent to A.
- Generate one simplified Global Context per task/image.
- Global Context may output `task_status/facts/evidence`, but deterministic downstream projection removes `task_status`.
- Candidate verifier receives only `{facts, evidence}` as auxiliary scene context.

### C — Adaptive Local-first

1. Fully execute A.
2. If every candidate/binding is `satisfied` or `not_satisfied`, do not generate Global Context and adopt A unchanged.
3. Only when at least one candidate/binding is `uncertain`, lazily generate exactly one Global Context for that image.
4. Re-evaluate only uncertain candidates/bindings; same-image fallback units reuse the same projected facts.
5. A `satisfied/not_satisfied` results are immutable and may not be overturned.
6. Only route-semantic or relation-binding `uncertain` is fallback-eligible. A `subject_validity=uncertain` is identity uncertainty and remains immutable; Global Context may not repair candidate identity.

## Identity and anti-contamination invariant

- Candidate identity/assignment must be anchored by candidate-specific evidence.
- Global facts may only supply scene-level context missing from local evidence.
- Global facts may not independently assign a global fact to a candidate.
- Global Context contains no candidate IDs.
- The downstream payload is constructed programmatically as `{facts, evidence}`; `task_status` is absent, not merely hidden by prompt instruction.
- Subject validity is outside the Context Policy arm and is held constant across A/B/C.

## Metrics

- candidate/binding accuracy by attribute, behavior and relation.
- regressions relative to A.
- false assignment.
- uncertain and legitimate-uncertain preservation.
- protocol failure, attempts, retry and recovered.
- calls, prompt/completion/total tokens, warm latency and per-image cost.
- uncertain resolution: correct / still uncertain / wrong.
- fallback harm: a reasonable A uncertain forced into an incorrect binary result.

The final decision may select A, B, C, route-specific policies, or NO CHANGE. Fewer uncertain results are not automatically better.
