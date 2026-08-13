import json
import sys
import time
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual_agent.relations import verify_relations
from visual_agent.vlm import verify_candidates


BENCHMARK_DIR = ROOT / "benchmark"


def run_candidate_stability() -> list[dict]:
    source = json.loads(
        (BENCHMARK_DIR / "phase7_results/challenge_004/result.json").read_text(encoding="utf-8")
    )
    candidates = [
        {"id": item["id"], "bbox": item["bbox"]}
        for item in source["candidates"]
    ]
    image_path = ROOT / "images/test_images/benchmark_fishing_two_people.png"
    results = []
    for run in range(1, 11):
        started = time.perf_counter()
        try:
            value, metadata = verify_candidates(
                image_path,
                source["prompt"],
                source["plan"],
                candidates,
            )
            result = {
                "run": run,
                "status": "success",
                "protocol": metadata,
                "result": value,
                "seconds": round(time.perf_counter() - started, 3),
            }
        except Exception as error:
            result = {
                "run": run,
                "status": "error",
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
                "seconds": round(time.perf_counter() - started, 3),
            }
        results.append(result)
        print(f"candidate {run}/10 {result['status']}", flush=True)
        (BENCHMARK_DIR / "phase8_candidate_stability.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return results


def run_relation_stability() -> list[dict]:
    source = json.loads(
        (BENCHMARK_DIR / "phase7_results/core_004/result.json").read_text(encoding="utf-8")
    )
    image_path = ROOT / "images/test_images/commons_umbrella.jpg"
    subjects = source["verified_subjects"]
    related = source["relation_candidates"]
    relation_plan = source["plan"]["related_objects"][0]
    results = []
    for run in range(1, 6):
        started = time.perf_counter()
        try:
            value, metadata = verify_relations(
                image_path,
                subjects,
                related,
                relation_plan["object"],
                relation_plan["relation"],
            )
            result = {
                "run": run,
                "status": "success",
                "protocol": metadata,
                "result": value,
                "seconds": round(time.perf_counter() - started, 3),
            }
        except Exception as error:
            result = {
                "run": run,
                "status": "error",
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
                "seconds": round(time.perf_counter() - started, 3),
            }
        results.append(result)
        print(f"relation {run}/5 {result['status']}", flush=True)
        (BENCHMARK_DIR / "phase8_relation_stability.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return results


def main() -> None:
    candidate = run_candidate_stability()
    relation = run_relation_stability()
    if any(item["status"] != "success" for item in [*candidate, *relation]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
