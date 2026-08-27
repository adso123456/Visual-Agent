# R3 Candidate Identity A/B/C Execution Report

## Frozen execution

- Scheduled first-pass calls: 105
- Terminal records: 105 (success 105, failure 0)
- Logical Local VLM calls: 130 (fallback 25)
- Protocol attempts: 130; retry 0; recovered 0
- Tokens: prompt 339836, completion 9480, total 349316
- Model latency: 1826.263 s; wall time: 1979.669 s
- Provider/model: OpenAI-compatible Local Ollama / `qwen3.8:27b-mtp-q4_K_M`

No failed execution was replaced. No Production code was modified.

## Frozen Gate observations

| Metric | A | B | C |
|---|---:|---:|---:|
| challenge_001 bystander false assignment | 5/5 | 0/5 | 0/5 |
| challenge_001 true operator retained | 5/5 | 5/5 | 5/5 |
| challenge_003 uncertainty preserved | 0/5 | 5/5 | 0/5 |
| challenge_003 confident binary | 5/5 | 0/5 | 5/5 |
| challenge_004 elder retained | 0/5 | 0/5 | 0/5 |
| challenge_004 child false assignment | 0/5 | 0/5 | 0/5 |
| F1 candidate correct | 5/10 | 4/10 | 5/10 |
| F1 task correct | 3/6 | 2/6 | 3/6 |

Fallback classification: A `{'fallback_harm': 5, 'correctly_resolved': 1, 'still_uncertain': 2}` (report only), B N/A, C `{'non_harm': 10, 'fallback_harm': 5, 'correctly_resolved': 1, 'still_uncertain': 1}` (Gate requires zero harm).

## Decision

- Arm B removes challenge_001 false assignment and safely preserves challenge_003 uncertainty, but it does not retain the challenge_004 elder and regresses the paired F1 candidate/task counts.
- Arm C removes challenge_001 false assignment and matches A on F1, but it converts challenge_003 legitimate uncertainty to confident binary and does not retain the challenge_004 elder.
- Therefore neither B nor C passes all frozen gates. No R3 candidate-identity Production change is authorized; keep the current Production evidence policy.

The full mechanical verdict is in `gate_evaluation.json`; raw terminal records remain in `results.jsonl`.
