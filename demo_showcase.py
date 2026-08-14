"""Demo showcase：按 PRD §7 核心流程跑通一组规范示例。

用法（本地栈，无需 API Key）：
    python demo_showcase.py [--output-dir demo_showcase_output]

每个示例：图片 + 自然语言指令 + 预编译计划 -> 真实 run_pipeline
（Detector -> SAM2 -> Action），输出处理图 + 结构化 JSON，并打印汇总。

语义验证（constraints/relation）需要 Qwen API；本地栈模式下 verify=False
会改变结果语义（所有候选视为已验证），因此这里选用的示例要么无约束、
要么明确标注该差异。完整链路请使用 main.py / Demo UI 并设置 API Key。
"""

import argparse
import json
from pathlib import Path

from visual_agent.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parent

# (名称, 图片相对路径, 指令, plan) —— 覆盖 PRD §7/§14 的五种确定性操作
DEMO_CASES = [
    (
        "01_red_shirt_outline",
        "images/test_images/commons_red_shirts.jpg",
        "只给穿红色衣服的人描边",
        {"target_object": "person", "label": "穿红色衣服的人",
         "constraints": ["穿红色衣服"], "action": {"type": "outline"}, "related_objects": []},
    ),
    (
        "02_umbrella_cutout",
        "images/test_images/commons_umbrella.jpg",
        "把拿雨伞的人单独抠出来",
        {"target_object": "person", "label": "拿雨伞的人",
         "constraints": ["手持雨伞"], "action": {"type": "cutout"},
         "related_objects": [{"object": "umbrella", "relation": "held_by_target"}]},
    ),
    (
        "03_fishing_highlight",
        "images/test_images/test_fishing.jpg",
        "把正在钓鱼的人高亮",
        {"target_object": "person", "label": "正在钓鱼的人",
         "constraints": ["正在钓鱼"], "action": {"type": "highlight"}, "related_objects": []},
    ),
    (
        "04_hat_blur",
        "images/test_images/benchmark_fishing_hats.png",
        "把戴帽子的人模糊",
        {"target_object": "person", "label": "戴帽子的人",
         "constraints": ["戴帽子"], "action": {"type": "blur_target"}, "related_objects": []},
    ),
    (
        "05_dim_background",
        "images/test_images/test_family_fishing.jpg",
        "把人物以外的背景变暗",
        {"target_object": "person", "label": "人物",
         "constraints": [], "action": {"type": "dim_background"}, "related_objects": []},
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Visual Agent Demo showcase")
    parser.add_argument("--output-dir", default=str(ROOT / "demo_showcase_output"))
    parser.add_argument("--only", help="只运行指定名称（逗号分隔）")
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    only = set(args.only.split(",")) if args.only else None

    summary = []
    for name, image_rel, prompt, plan in DEMO_CASES:
        if only and name not in only:
            continue
        image_path = ROOT / image_rel
        if not image_path.is_file():
            print(f"[skip] {name}: 图片缺失 {image_path}")
            continue
        print(f"[run ] {name}: {prompt}")
        result_image, result_json = run_pipeline(
            image_path,
            prompt,
            plan=plan,
            verify=False,
            final_response=False,
            output_dir=output_dir,
        )
        result = json.loads(result_json.read_text(encoding="utf-8"))
        entry = {
            "name": name,
            "prompt": prompt,
            "plan": plan,
            "candidates_count": len(result["candidates"]),
            "targets_count": len(result["targets"]),
            "action": result["plan"]["action"]["type"],
            "result_image": result_image.name,
            "result_json": result_json.name,
            "note": "local_stack: verify=False（无 Qwen 语义验证）；关系/约束任务结果仅展示定位与分割链路",
        }
        summary.append(entry)
        print(f"        targets={entry['targets_count']} candidates={entry['candidates_count']} image={result_image.name}")

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({"benchmark_version": "demo_showcase_1.0", "local_stack": True, "cases": summary},
                   ensure_ascii=False, indent=2) + chr(10),
        encoding="utf-8",
    )
    print(f"\n汇总：{manifest_path}")


if __name__ == "__main__":
    main()
