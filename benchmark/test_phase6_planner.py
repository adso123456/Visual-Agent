import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual_agent.deepseek_agent import DeepSeekAgent


CASES = [
    {"prompt": "找到正在钓鱼的人", "target_object": "person", "constraints": ["正在钓鱼"], "action": "highlight"},
    {"prompt": "把手持雨伞的人单独抠出来", "target_object": "person", "constraints": ["手持雨伞"], "action": "cutout"},
    {"prompt": "模糊图中的儿童", "target_object": "person", "constraints": ["儿童"], "action": "blur_target"},
    {"prompt": "只给穿红衣服的女人描边", "target_object": "person", "constraints": ["女性", "穿红色衣服"], "action": "outline"},
    {"prompt": "把狗以外背景变暗", "target_object": "dog", "constraints": [], "action": "dim_background"},
]


def semantic_match(actual: list[str], expected: list[str]) -> bool:
    normalized = " ".join(actual)
    return len(actual) == len(expected) and all(
        any(keyword in normalized for keyword in group)
        for group in [
            ({"正在钓鱼"} if item == "正在钓鱼" else
             {"手持雨伞", "拿着雨伞", "持伞"} if item == "手持雨伞" else
             {"儿童", "孩子", "小孩"} if item == "儿童" else
             {"女性", "女人", "女"} if item == "女性" else
             {"穿红色衣服", "穿红衣服", "红衣"})
            for item in expected
        ]
    )


def main() -> None:
    results = []
    for case in CASES:
        agent = DeepSeekAgent()
        plan = agent.plan_request(case["prompt"])
        checks = {
            "target_object": plan["target_object"] == case["target_object"],
            "constraints": semantic_match(plan["constraints"], case["constraints"]),
            "action": plan["action"]["type"] == case["action"],
        }
        results.append(
            {
                "prompt": case["prompt"],
                "expected": case,
                "plan": plan,
                "plan_attempts": agent.plan_attempts,
                "checks": checks,
                "passed": all(checks.values()),
            }
        )
    output = ROOT / "benchmark" / "phase6_planner_contract_results.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Planner contract: {sum(item['passed'] for item in results)}/{len(results)}")
    raise SystemExit(0 if all(item["passed"] for item in results) else 1)


if __name__ == "__main__":
    main()
