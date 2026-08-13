import json

import run_benchmark as baseline
from run_phase7_benchmark import run_phase7_case


def main() -> None:
    baseline.RESULTS_DIR = baseline.BENCHMARK_DIR / "phase8_results"
    results = []
    cases = baseline.load_cases()
    for index, case in enumerate(cases, 1):
        print(f"[{index}/{len(cases)}] {case['id']} {case['prompt']}", flush=True)
        result = run_phase7_case(case)
        if result.get("status") == "success":
            data = json.loads(
                (baseline.ROOT / result["artifacts"]["result_json"]).read_text(encoding="utf-8")
            )
            result["qwen_protocol"] = data["qwen_protocol"]
        results.append(result)
        print(
            f"  {result['status']} {result['cli_total_seconds']}s "
            f"targets={len(result.get('targets', []))}",
            flush=True,
        )
        (baseline.BENCHMARK_DIR / "phase8_raw_results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
