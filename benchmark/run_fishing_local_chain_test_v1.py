"""钓鱼场景纯本地链路专项测试（无云端 API）。

抽样 fishing 场景图片，覆盖四类语义路由：
- behavior：框出正在钓鱼的人
- highlight：把拿着鱼的人标出来
- relation：把拿着鱼竿的人描边（held_by_target）
- negative：框出正在游泳的人（期望 0 target）

运行（需先设置 VLM_*/PLANNER_* 指向本地端点）：
    python benchmark/run_fishing_local_chain_test_v1.py
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual_agent.pipeline import run_pipeline

FISHING_PROMPT = "框出正在钓鱼的人"
FISH_HOLD_PROMPT = "把拿着鱼的人标出来"
ROD_PROMPT = "把拿着鱼竿的人描边"
NEGATIVE_PROMPT = "框出正在游泳的人"

CASES = [
    ("fishing_001.jpeg", FISHING_PROMPT),
    ("fishing_003.jpeg", FISHING_PROMPT),
    ("fishing_005.jpeg", FISHING_PROMPT),
    ("fishing_008.jpeg", FISHING_PROMPT),
    ("fishing_011.jpeg", FISHING_PROMPT),
    ("fishing_014.jpeg", FISHING_PROMPT),
    ("fishing_017.jpeg", FISHING_PROMPT),
    ("fishing_021.jpeg", FISHING_PROMPT),
    ("fishing_002.jpeg", FISH_HOLD_PROMPT),
    ("fishing_009.jpeg", FISH_HOLD_PROMPT),
    ("benchmark_fishing_clear.png", ROD_PROMPT),
    ("benchmark_fishing_two_people.png", ROD_PROMPT),
    ("fishing_004.jpeg", NEGATIVE_PROMPT),
]


def main() -> None:
    results = []
    for index, (image_name, prompt) in enumerate(CASES, start=1):
        started = time.perf_counter()
        record = {"case": f"{index:02d}", "image": image_name, "prompt": prompt}
        try:
            image_out, json_out = run_pipeline(
                ROOT / "images" / "test_images" / image_name, prompt
            )
            data = json.loads(json_out.read_text(encoding="utf-8"))
            record.update(
                ok=True,
                targets=len(data["targets"]),
                summary=data["agent_response"],
                result=str(image_out),
            )
        except Exception as error:  # noqa: BLE001
            record.update(ok=False, error=str(error)[:200])
        record["seconds"] = round(time.perf_counter() - started, 1)
        results.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)

    passed = sum(1 for item in results if item.get("ok") and item["targets"] > 0)
    empty = sum(1 for item in results if item.get("ok") and item["targets"] == 0)
    failed = sum(1 for item in results if not item.get("ok"))
    total_seconds = round(sum(item["seconds"] for item in results), 1)
    print(
        json.dumps(
            {
                "total": len(results),
                "executed_with_targets": passed,
                "executed_empty": empty,
                "runtime_error": failed,
                "total_seconds": total_seconds,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
