"""钓鱼语义口径网络图盲测（Wikimedia 公开图，需人工预核 GT 后运行）。

口径（产品定义）：
- '钓鱼' 仅指手持钓竿垂钓；
- 撒网/收网/拉网属'捕鱼'，不是'钓鱼'；
- 鱼竿插在支架/船体上而人未手持（插竿守钓）不在应用场景内。

运行前设置纯本地端点（VLM_*/PLANNER_* 指向 Ollama），并 unset 云端 key。
GT 以注释标注，v1 为提示词修复前基线，v2 为修复后回归。
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual_agent.pipeline import run_pipeline

PROMPT = "框出正在钓鱼的人"

# (image, prompt, ground_truth, note)
CASES = [
    ("probe_angling_lake.jpg", PROMPT, "3-4", "4 名持竿岸钓，第 4 人部分遮挡"),
    ("probe_burkina_rods.jpg", PROMPT, "0-1", "3 根竿插放，人未手持；边界案例"),
    ("probe_ice_fishing.jpg", PROMPT, "0", "竿插冰洞，无人在场"),
    ("probe_chair_rods_snow.jpg", PROMPT, "0", "雪地插竿，无人在场"),
    ("probe_fishing_misc.jpg", PROMPT, "0", "船上撒网 = 捕鱼，非钓鱼"),
    ("probe_cast_net_1.jpg", PROMPT, "0", "岸边撒网 = 捕鱼，非钓鱼"),
    ("probe_cast_net_2.jpg", PROMPT, "0", "桥下撒网 = 捕鱼，非钓鱼"),
    ("probe_angling_lake.jpg", "把拿着鱼竿的人描边", "3-4", "关系路由对照例"),
]


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "v1"
    output_path = Path(__file__).resolve().parent / "web_probe_images" / f"probe_results_{tag}.json"
    results = []
    for name, prompt, ground_truth, note in CASES:
        started = time.perf_counter()
        record = {"image": name, "prompt": prompt, "ground_truth": ground_truth, "note": note}
        try:
            _, json_out = run_pipeline(ROOT / "benchmark" / "web_probe_images" / name, prompt)
            data = json.loads(json_out.read_text(encoding="utf-8"))
            record.update(
                ok=True,
                targets=len(data["targets"]),
                summary=data["agent_response"],
                result_json=str(json_out),
            )
        except Exception as error:  # noqa: BLE001
            record.update(ok=False, error=str(error)[:200])
        record["seconds"] = round(time.perf_counter() - started, 1)
        results.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    output_path.write_text(
        json.dumps({"tag": tag, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"saved: {output_path}", flush=True)


if __name__ == "__main__":
    main()
