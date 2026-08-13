import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual_agent.deepseek_agent import DeepSeekAgent


CASES = [
    ("只给手持雨伞的人描边", "person", "outline", ["umbrella", "held_by_target"]),
    ("把手持雨伞的人单独抠出来", "person", "cutout", ["umbrella", "held_by_target"]),
    ("找到正在钓鱼的人", "person", "highlight", None),
    ("模糊图中的儿童", "person", "blur_target", None),
    ("找到骑自行车的人", "person", "highlight", None),
    ("找到戴安全帽的人", "person", "highlight", None),
    ("找到靠近汽车的人", "person", "highlight", None),
    ("找到抱着狗的人", "person", "highlight", None),
]


def main() -> None:
    results = []
    for prompt, target_object, action, relation in CASES:
        agent = DeepSeekAgent()
        plan = agent.plan_request(prompt)
        related = plan["related_objects"]
        relation_ok = (
            related == []
            if relation is None
            else related == [{"object": relation[0], "relation": relation[1]}]
        )
        checks = {
            "target_object": plan["target_object"] == target_object,
            "constraints_preserved": bool(plan["constraints"]),
            "action": plan["action"]["type"] == action,
            "related_objects": relation_ok,
        }
        results.append(
            {
                "prompt": prompt,
                "plan": plan,
                "plan_attempts": agent.plan_attempts,
                "checks": checks,
                "passed": all(checks.values()),
            }
        )
    output = ROOT / "benchmark" / "phase7_planner_contract_results.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Phase 7 Planner contract: {sum(item['passed'] for item in results)}/{len(results)}")
    raise SystemExit(0 if all(item["passed"] for item in results) else 1)


if __name__ == "__main__":
    main()
