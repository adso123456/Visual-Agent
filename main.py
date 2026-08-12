import argparse
import json
from pathlib import Path

from visual_agent.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="用自然语言定位图片中的目标")
    parser.add_argument("--image", required=True, type=Path, help="输入图片路径")
    parser.add_argument("--prompt", required=True, help="自然语言查找指令")
    args = parser.parse_args()

    result_image, result_json = run_pipeline(args.image, args.prompt)
    print(f"结果图片：{result_image}")
    print(f"结果 JSON：{result_json}")
    result = json.loads(result_json.read_text(encoding="utf-8"))
    print(f"Agent：{result['agent_response']}")


if __name__ == "__main__":
    main()
