"""端到端延迟测量：冷启动 vs 热复用，本地栈 vs 全链路。

用法示例（本地栈，无需任何 API key）：
    .venv/Scripts/python benchmark/measure_latency.py \
        --image images/test_images/benchmark_fishing_clear.png \
        --plan-map benchmark/latency_plan_map.json \
        --no-verify --no-final-response --runs 2 \
        --json benchmark/latency_report.json

全链路（需 DEEPSEEK_API_KEY + DASHSCOPE_API_KEY）：
    .venv/Scripts/python benchmark/measure_latency.py \
        --image images/test_images/test_family_fishing.jpg --prompt "找到正在钓鱼的人"

说明：
- 每个进程内 DINO/SAM2 只加载一次（visual_agent.models 常驻注册表）。
- 第 1 次运行强制冷启动（fresh_models=True），其余热复用。
- --no-verify 时所有 DINO 候选直接视为已验证，关系目标会被跳过
  （relation 需要 VLM），因此 local 模式请使用无 related_objects 的 plan。
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from visual_agent.pipeline import run_pipeline  # noqa: E402


def _load_plan_map(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("plan-map 必须是 {图像文件名: plan dict}")
    return data


def _collect_timings(saved: dict) -> dict:
    timings = dict(saved["timings"])
    sam2 = timings.get("sam2") or {}
    timings["sam2_load_seconds"] = sam2.get("load_seconds", 0.0)
    timings["sam2_inference_seconds"] = sam2.get("inference_seconds", 0.0)
    timings["sam2_cached"] = sam2.get("cached")
    timings["sam2_load_seconds_total"] = sam2.get("load_seconds")
    return timings


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def run_case(
    image_path: Path,
    prompt: str | None,
    plan: dict | None,
    verify: bool,
    final_response: bool,
    fresh: bool,
    output_dir: Path,
) -> dict:
    started = time.perf_counter()
    image_out, json_out = run_pipeline(
        image_path,
        prompt or "",
        plan=plan,
        verify=verify,
        final_response=final_response,
        fresh_models=fresh,
        output_dir=output_dir,
    )
    wall = time.perf_counter() - started
    saved = json.loads(json_out.read_text(encoding="utf-8"))
    return {
        "wall_seconds": round(wall, 3),
        "total_seconds": saved["timings"].get("total_seconds"),
        "timings": _collect_timings(saved),
        "candidates": len(saved["candidates"]),
        "verified_subjects": len(saved["verified_subjects"]),
        "targets": len(saved["targets"]),
        "action": saved["plan"]["action"]["type"],
        "agent_response": saved["agent_response"],
        "image_output": str(image_out),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="端到端延迟测量：冷启动 vs 热复用")
    parser.add_argument("--image", action="append", type=Path, default=[], help="输入图片（可重复）")
    parser.add_argument("--dir", type=Path, default=None, help="批量测量目录（*.jpg/*.png/*.jpeg）")
    parser.add_argument("--prompt", default=None, help="提示词；local 模式用 --plan/--plan-map")
    parser.add_argument("--plan", type=Path, default=None, help="canned plan JSON（对所有图生效）")
    parser.add_argument("--plan-map", type=Path, default=None, help="{图像文件名: plan} JSON")
    parser.add_argument("--no-verify", action="store_true", help="跳过 Qwen 验证（本地栈测量）")
    parser.add_argument("--no-final-response", action="store_true", help="跳过 DeepSeek 汇总，用本地模板")
    parser.add_argument("--fresh-each", action="store_true", help="每次运行都强制冷启动（隔离测量）")
    parser.add_argument("--runs", type=int, default=1, help="热复用重复次数（默认 1；第 1 次恒为冷启动）")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "benchmark" / "latency_scratch", help="结果输出目录")
    parser.add_argument("--json", dest="json_out", type=Path, default=None, help="报告 JSON 输出路径")
    args = parser.parse_args()

    images = list(args.image)
    if args.dir:
        images += sorted(args.dir.glob("*.jpg")) + sorted(args.dir.glob("*.png")) + sorted(args.dir.glob("*.jpeg"))
    images = [path for path in dict.fromkeys(path.resolve() for path in images) if path.is_file()]
    if not images:
        raise SystemExit("没有可用图片：--image 或 --dir 至少提供一个")
    if args.prompt is None and args.plan is None and args.plan_map is None:
        raise SystemExit("缺少输入：--prompt（全链路）或 --plan/--plan-map（本地栈）必须提供")

    plan_map: dict[str, dict] = {}
    if args.plan_map:
        plan_map = _load_plan_map(args.plan_map)
    if args.plan:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        plan_map = {image.name: plan for image in images}

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    verify = not args.no_verify
    final_response = not args.no_final_response

    fresh_next = not args.fresh_each
    report = {
        "mode": {"verify": verify, "final_response": final_response, "runs_per_image": args.runs},
        "images": [],
    }
    for image_path in images:
        prompt = args.prompt
        plan = plan_map.get(image_path.name) if plan_map else None
        if plan is None and prompt is None:
            print(f"跳过 {image_path.name}：plan-map 中没有该图且未给 --prompt")
            continue
        entry = {"image": str(image_path), "prompt": prompt, "plan": plan, "runs": []}
        print(f"== {image_path.name} ==")
        for run_index in range(1 + args.runs):
            fresh = fresh_next or args.fresh_each
            fresh_next = False
            try:
                result = run_case(image_path, prompt, plan, verify, final_response, fresh, output_dir)
            except Exception as error:  # noqa: BLE001
                result = {"error": f"{type(error).__name__}: {error}"}
                print(f"  run {run_index + 1} 失败: {result['error']}")
            result["run_index"] = run_index + 1
            result["cold"] = fresh
            entry["runs"].append(result)
            stage = "cold" if fresh else f"warm{run_index}"
            total = result.get("total_seconds")
            print(
                f"  [{stage}] total={total}s wall={result.get('wall_seconds')}s "
                f"candidates={result.get('candidates')} targets={result.get('targets')}"
            )
        report["images"].append(entry)
        print()

    cold_totals = [r["total_seconds"] for e in report["images"] for r in e["runs"] if r.get("cold") and r.get("total_seconds") is not None]
    warm_totals = [r["total_seconds"] for e in report["images"] for r in e["runs"] if not r.get("cold") and r.get("total_seconds") is not None]
    summary = {
        "cold_median_seconds": _median(cold_totals),
        "warm_median_seconds": _median(warm_totals),
        "cold_runs": len(cold_totals),
        "warm_runs": len(warm_totals),
    }
    report["summary"] = summary
    print("汇总:", json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入：{args.json_out}")


if __name__ == "__main__":
    main()
