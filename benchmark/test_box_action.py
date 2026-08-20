import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from demo_ui.server import _build_summary, _validate_plan
from visual_agent.actions import ACTION_TYPES as EXECUTOR_ACTION_TYPES
from visual_agent.actions import ImageActionExecutor
from visual_agent.deepseek_agent import (
    ACTION_TYPES as AGENT_ACTION_TYPES,
    PLANNER_SYSTEM_PROMPT,
    TOOL_NAME,
    DeepSeekAgent,
)
from visual_agent.pipeline import run_pipeline
from visual_agent.vlm import ACTION_TYPES as VLM_ACTION_TYPES


BOX_PLAN = {
    "target_object": "person",
    "label": "戴眼罩的人",
    "constraints": [{"text": "戴眼罩", "route": "attribute"}],
    "action": {"type": "box"},
    "related_objects": [],
}
BLUE_BOX_PLAN = {**BOX_PLAN, "action": {"type": "box", "color": "#0000ff"}}


def test_box_contract_and_prompt_mapping():
    tool_call = SimpleNamespace(
        function=SimpleNamespace(
            name=TOOL_NAME,
            arguments=json.dumps(BOX_PLAN, ensure_ascii=False),
        )
    )

    assert DeepSeekAgent._validated_plan([tool_call]) == BOX_PLAN
    colored_tool_call = SimpleNamespace(
        function=SimpleNamespace(
            name=TOOL_NAME,
            arguments=json.dumps(BLUE_BOX_PLAN, ensure_ascii=False),
        )
    )
    assert DeepSeekAgent._validated_plan([colored_tool_call]) == BLUE_BOX_PLAN
    assert all(word in PLANNER_SYSTEM_PROMPT for word in ("框出", "框选", "框起来"))
    assert "box" in AGENT_ACTION_TYPES
    assert "box" in VLM_ACTION_TYPES
    assert "box" in EXECUTOR_ACTION_TYPES
    assert _validate_plan(BOX_PLAN) is None


def test_box_executor_draws_only_rectangle_border():
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    result = ImageActionExecutor().execute(
        image,
        masks=[],
        action_type="box",
        boxes=[[10, 8, 30, 32]],
    )

    assert np.array_equal(result[8, 10], [0, 0, 255])
    assert np.array_equal(result[20, 20], image[20, 20])
    assert np.array_equal(result[4, 4], image[4, 4])

    blue_result = ImageActionExecutor().execute(
        image,
        masks=[],
        action_type="box",
        boxes=[[10, 8, 30, 32]],
        action_color="#0000ff",
    )
    assert np.array_equal(blue_result[8, 10], [255, 0, 0])


def test_outline_and_highlight_honor_requested_color():
    image = np.zeros((32, 32, 3), dtype=np.uint8)
    mask = np.zeros((32, 32), dtype=bool)
    mask[8:24, 8:24] = True
    executor = ImageActionExecutor()

    outline = executor.execute(image, [mask], "outline", action_color="#0000ff")
    highlight = executor.execute(image, [mask], "highlight", action_color="#00ff00")

    assert outline[:, :, 0].max() == 255
    assert outline[:, :, 2].max() == 0
    assert highlight[16, 16, 1] > 100
    assert highlight[16, 16, 2] == 0


def test_box_pipeline_skips_sam_and_writes_bbox_result(tmp_path, monkeypatch):
    image_path = tmp_path / "input.jpg"
    cv2.imwrite(str(image_path), np.zeros((48, 64, 3), dtype=np.uint8))

    class DetectorStub:
        device = "cpu"
        load_seconds = 0.0
        memory_after_load_mb = 0.0

        @staticmethod
        def detect(_image_path: Path, target_object: str):
            assert target_object == "person"
            return [{"bbox": [10, 8, 30, 32], "text_label": "person", "confidence": 0.9}]

    monkeypatch.setattr("visual_agent.pipeline.get_detector", lambda fresh=False: (DetectorStub(), False))

    def fail_if_sam_is_loaded(*_args, **_kwargs):
        raise AssertionError("box 动作不应加载 SAM2")

    monkeypatch.setattr("visual_agent.pipeline.get_segmenter", fail_if_sam_is_loaded)

    image_output, json_output = run_pipeline(
        image_path,
        "框出戴眼罩的人",
        plan=BLUE_BOX_PLAN,
        verify=False,
        final_response=False,
        output_dir=tmp_path / "output",
    )

    result_image = cv2.imread(str(image_output))
    result_json = json.loads(json_output.read_text(encoding="utf-8"))
    assert result_json["plan"]["action"] == {"type": "box", "color": "#0000ff"}
    assert result_json["timings"]["sam2"] is None
    assert "segmentation" not in result_json["targets"][0]
    assert not list(image_output.parent.glob("*_mask_*.png"))
    assert result_image[8, 10, 0] > 150
    assert result_image[8, 10, 0] > result_image[8, 10, 2] * 3
    assert result_image[20, 20, 0] < 30


def test_demo_summary_displays_box_action():
    result = {
        "prompt": "框出戴眼罩的人",
        "plan": BOX_PLAN,
        "candidates": [],
        "verified_subjects": [],
        "relation_bindings": [],
        "targets": [],
        "timings": {},
    }

    summary = _build_summary(result, local_mode=True)
    assert summary["action_type"] == "box"
    assert summary["action_label"] == "矩形框选"
