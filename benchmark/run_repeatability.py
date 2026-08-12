import json
from pathlib import Path

from run_benchmark import BENCHMARK_DIR, load_cases, run_case


CASE_IDS = ["core_006", "core_011", "core_012"]


def main() -> None:
    cases = {case["id"]: case for case in load_cases()}
    results = []
    for case_id in CASE_IDS:
        for run_number in range(1, 4):
            result_id = f"repeat_{case_id}_{run_number}"
            print(f"{result_id}", flush=True)
            result = run_case(cases[case_id], result_id=result_id)
            results.append(result)
            print(
                f"  {result['status']} targets={len(result.get('targets', []))} "
                f"time={result['cli_total_seconds']}s",
                flush=True,
            )
            (BENCHMARK_DIR / "repeatability_raw.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )


if __name__ == "__main__":
    main()
