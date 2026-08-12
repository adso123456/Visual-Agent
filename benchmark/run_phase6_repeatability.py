import json

import run_benchmark as baseline
from run_phase6_benchmark import run_phase6_case


REPEAT_CASES = ["core_006", "core_011", "core_012"]


def main() -> None:
    baseline.RESULTS_DIR = baseline.BENCHMARK_DIR / "phase6_results"
    cases = {case["id"]: case for case in baseline.load_cases()}
    results = []
    for case_id in REPEAT_CASES:
        for run in range(1, 4):
            result_id = f"repeat_{case_id}_{run}"
            print(f"[{len(results) + 1}/9] {result_id}", flush=True)
            result = run_phase6_case(cases[case_id], result_id)
            results.append(result)
            print(
                f"  {result['status']} {result['cli_total_seconds']}s "
                f"attempts={result.get('agent', {}).get('plan_attempts', 'error')}",
                flush=True,
            )
            (baseline.BENCHMARK_DIR / "phase6_repeatability_raw.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )


if __name__ == "__main__":
    main()
