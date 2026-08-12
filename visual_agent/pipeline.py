from pathlib import Path

from visual_agent.grounding import GroundingDetector
from visual_agent.renderer import save_results
from visual_agent.vlm import understand_target


def run_pipeline(image_path: Path, prompt: str) -> tuple[Path, Path]:
    image_path = image_path.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"图片不存在：{image_path}")

    target_info = understand_target(image_path, prompt)
    detections = GroundingDetector().detect(image_path, target_info["grounding_text"])
    return save_results(image_path, prompt, target_info, detections, Path("outputs"))

