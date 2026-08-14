import argparse
import json
from pathlib import Path

from visual_agent.pipeline import run_pipeline


def _print_timings(timings: dict, indent: int = 2) -> None:
    prefix = " " * indent
    for key, value in timings.items():
        if isinstance(value, dict):
            print(f"{prefix}{key}:")
            _print_timings(value, indent + 2)
        else:
            print(f"{prefix}{key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="用自然语言定位图片中的目标")
    parser.add_argument("--image", required=True, type=Path, help="输入图片路径")
    parser.add_argument("--prompt", required=True, help="自然语言查找指令")
    parser.add_argument(
        "--profile",
        action="store_true",
        help="输出各阶段耗时（含模型加载、推理、LLM 调用、总时长）",
    )
    args = parser.parse_args()

    result_image, result_json = run_pipeline(args.image, args.prompt)
    print(f"结果图片：{result_image}")
    print(f"结果 JSON：{result_json}")
    result = json.loads(result_json.read_text(encoding="utf-8"))
    print(f"Agent：{result['agent_response']}")
    if args.profile:
        print()
        print("各阶段耗时：")
        _print_timings(result["timings"])


if __name__ == "__main__":
    main()
