"""Frozen-VLM Downstream Usability Probe（契约 §10.5）。

第二层测试：在 Detector-only 评价完成后，用冻结 VLM（qwen3-vl-flash）对每个
candidate 做语义可理解性判断，区分两类失败：

- DETECTOR_DOWNSTREAM_UNUSABLE：候选框本身过小/局部/混检（人工 review 已判
  FALSE/MIXED/UNUSABLE_PARTIAL 或 ambiguous），VLM 无法理解 → Detector 问题；
- VLM_SEMANTIC_LIMIT：候选人工确认清晰独立（VALID / USABLE_PARTIAL），
  但冻结 VLM 判断失败 → VLM 问题。

前置条件：reviews/grounding_dino_base.json 必须已完成人工确认
（reviewed_by=human，24/24 COMPLETE）。

用法：
    python -m benchmark.instance_quality_v1.scripts.run_semantic_probe

输出：runs/grounding_dino_base/semantic_results.json，供 evaluate.py 读取。
"""

import base64
import io
import json
import os
from pathlib import Path

from openai import OpenAI
from PIL import Image

from benchmark.instance_quality_v1.annotation_tool.review_store import CandidateReviewStore


ROOT = Path(__file__).resolve().parents[1]
VLM_MODEL = "qwen3-vl-flash"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

UNUSABLE_CLASSES = {"FALSE_DETECTION", "MIXED_INSTANCE", "AMBIGUOUS"}


def _client() -> OpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("未设置环境变量 DASHSCOPE_API_KEY")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def _crop_data_url(image_path: Path, bbox: list) -> str:
    """把候选 bbox 放大裁剪为 data URL，交给冻结 VLM。"""
    image = Image.open(image_path).convert("RGB")
    x1, y1, x2, y2 = [max(0, int(v)) for v in bbox]
    x1, y1 = min(x1, image.width - 1), min(y1, image.height - 1)
    crop = image.crop((x1, y1, min(x2, image.width), min(y2, image.height)))
    scale = min(4.0, 1024 / max(crop.size)) if max(crop.size) > 0 else 1.0
    if scale > 1:
        crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    crop.save(buffer, format="JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _probe_vlm(client: OpenAI, data_url: str, target_object: str) -> str | None:
    """返回 "YES" / "NO" / "UNCLEAR"，失败返回 None。"""
    question = "框内是否是一个可辨识的 " + target_object + "？"
    response = client.chat.completions.create(
        model=VLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是图像可理解性检查器。只回答 YES / NO / UNCLEAR 三选一。"
                    "YES=框内明确是一个可辨识的目标；NO=框内不是该目标或几乎无法辨认；"
                    "UNCLEAR=目标部分可见但无法可靠确认。不要输出任何解释。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": question},
                ],
            },
        ],
        temperature=0,
        max_tokens=8,
    )
    content = response.choices[0].message.content
    if not content:
        return None
    text = content.strip().upper()
    if text.startswith("YES"):
        return "YES"
    if text.startswith("NO"):
        return "NO"
    return "UNCLEAR"


def main() -> None:
    store = CandidateReviewStore(ROOT)
    if not all(e["review_status"] == "COMPLETE" and e["reviewed_by"] == "human" for e in store.document["images"]):
        raise RuntimeError(
            "CANDIDATE_REVIEW_NOT_HUMAN_CONFIRMED: 需先在 annotation_tool 完成人工确认"
            "（reviewed_by=human，24/24 COMPLETE）才能运行 Downstream Usability Probe",
        )
    client = _client()
    meta_by = {item["image_id"]: item for item in store.gt.manifest["images"]}
    review_by = {item["image_id"]: item for item in store.document["images"]}
    raw_by = {item["image_id"]: item for item in store.raw["images"]}

    results = {"images": []}
    for image_id in store.gt.test_ids:
        meta = meta_by[image_id]
        image_path = ROOT / meta["relative_path"]
        target = meta["target_object"]
        reviews = {r["candidate_id"]: r for r in review_by[image_id]["candidates"]}
        raw_candidates = {c["id"]: c for c in raw_by[image_id]["candidates"]}
        rows = []
        for candidate_id, review in reviews.items():
            classification = review["classification"]
            completeness = review["completeness"]
            human_usable = (
                classification in {"VALID_INSTANCE", "PARTIAL_INSTANCE", "DUPLICATE_INSTANCE"}
                and completeness in {"COMPLETE", "USABLE_PARTIAL"}
            )
            if not human_usable:
                rows.append({"id": candidate_id, "attribution": "DETECTOR_DOWNSTREAM_UNUSABLE"})
                continue
            bbox = raw_candidates[candidate_id]["bbox"]
            data_url = _crop_data_url(image_path, bbox)
            verdict = _probe_vlm(client, data_url, target)
            if verdict == "YES":
                rows.append({"id": candidate_id, "attribution": "VLM_CORRECT"})
            elif verdict in ("NO", "UNCLEAR"):
                rows.append({"id": candidate_id, "attribution": "VLM_SEMANTIC_LIMIT"})
            else:
                rows.append({"id": candidate_id, "attribution": "NOT_EVALUABLE_SEMANTIC"})
        results["images"].append({"image_id": image_id, "candidates": rows})

    out_path = ROOT / "runs" / "grounding_dino_base" / "semantic_results.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print("wrote " + str(out_path))
    from collections import Counter
    attribution = Counter(r["attribution"] for img in results["images"] for r in img["candidates"])
    print("attribution:", dict(attribution))


if __name__ == "__main__":
    main()
