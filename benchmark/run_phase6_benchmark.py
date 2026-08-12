import argparse
import json
from pathlib import Path

import run_benchmark as baseline


PHASE6_RESULTS_DIR = baseline.BENCHMARK_DIR / "phase6_results"


def run_phase6_case(case: dict, result_id: str | None = None) -> dict:
    result = baseline.run_case(case, result_id)
    if result.get("status") == "success":
        data = json.loads(
            (baseline.ROOT / result["artifacts"]["result_json"]).read_text(encoding="utf-8")
        )
        result["agent"] = data["agent"]
        result["agent_response"] = data["agent_response"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 Phase 6 DeepSeek Agent 图片回归测试")
    parser.add_argument("--case", action="append", dest="case_ids", help="只运行指定 case，可重复传入")
    parser.add_argument("--suite", choices=["core", "challenge"], help="只运行指定 suite")
    parser.add_argument("--output", default="phase6_raw_results.json", help="汇总结果文件名")
    args = parser.parse_args()

    baseline.RESULTS_DIR = PHASE6_RESULTS_DIR
    cases = baseline.load_cases()
    if args.case_ids:
        cases = [case for case in cases if case["id"] in set(args.case_ids)]
    if args.suite:
        cases = [case for case in cases if case["suite"] == args.suite]

    results = []
    for index, case in enumerate(cases, 1):
        print(f"[{index}/{len(cases)}] {case['id']} {case['prompt']}", flush=True)
        result = run_phase6_case(case)
        results.append(result)
        print(
            f"  {result['status']} {result['cli_total_seconds']}s "
            f"targets={len(result.get('targets', []))}",
            flush=True,
        )
        (baseline.BENCHMARK_DIR / args.output).write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
