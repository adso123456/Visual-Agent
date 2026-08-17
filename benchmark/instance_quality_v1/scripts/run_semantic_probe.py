"""Frozen Qwen 对预声明用户语义约束的 Downstream Usability Probe。"""

import base64
import hashlib
import io
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI
from PIL import Image

from benchmark.instance_quality_v1.annotation_tool.review_store import CandidateReviewStore


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "annotations" / "semantic_probe_v1.json"
VLM_MODEL = "qwen3-vl-flash"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
PROMPT_VERSION = "semantic_constraint_v1"
PROBE_TYPE = "predeclared_semantic_constraint"


def _client() -> OpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("未设置环境变量 DASHSCOPE_API_KEY")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def _crop_data_url(image_path: Path, bbox: list) -> str:
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


def _probe_vlm(client: OpenAI, data_url: str, question: str) -> str | None:
    response = client.chat.completions.create(
        model=VLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是冻结的视觉语义约束判断器。候选目标已经由 Detector 定位。"
                    "只依据候选裁剪中的可见证据，判断该目标是否满足用户预声明条件。"
                    "只回答 YES / NO / UNCLEAR：YES=满足，NO=不满足，UNCLEAR=证据不足。"
                    "不要改为判断基础对象类别，不要输出解释。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": "预声明条件：" + question},
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


def _load_and_validate_spec(store: CandidateReviewStore) -> tuple[dict, str]:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    required = {
        "benchmark_version", "probe_version", "annotation_state", "gt_fingerprint",
        "raw_candidates_sha256", "review_sha256", "answer_space", "images",
    }
    missing = required - set(spec)
    if missing:
        raise ValueError(f"SEMANTIC_SPEC_UNVERIFIABLE: missing={sorted(missing)}")
    if spec["probe_version"] != PROMPT_VERSION or spec["annotation_state"] != "FROZEN":
        raise ValueError("SEMANTIC_SPEC_NOT_FROZEN")
    if spec["answer_space"] != ["YES", "NO"]:
        raise ValueError("SEMANTIC_SPEC_ANSWER_SPACE_INVALID")
    if spec["gt_fingerprint"] != store.gt.fingerprint():
        raise ValueError("SEMANTIC_SPEC_GT_MISMATCH")
    if spec["raw_candidates_sha256"] != store.raw_sha256:
        raise ValueError("SEMANTIC_SPEC_RAW_MISMATCH")
    if spec["review_sha256"] != hashlib.sha256(store.review_path.read_bytes()).hexdigest():
        raise ValueError("SEMANTIC_SPEC_REVIEW_MISMATCH")

    gt_by = {item["image_id"]: item for item in store.gt.document["images"]}
    raw_by = {item["image_id"]: item for item in store.raw["images"]}
    review_by = {item["image_id"]: item for item in store.document["images"]}
    expected_images = {item["image_id"] for item in store.gt.test_images}
    actual_images = [item.get("image_id") for item in spec["images"]]
    if len(actual_images) != len(set(actual_images)) or set(actual_images) != expected_images:
        raise ValueError("SEMANTIC_SPEC_IMAGE_SET_MISMATCH")
    for item in spec["images"]:
        image_id = item["image_id"]
        gt_rows = {row["instance_id"]: row for row in gt_by[image_id]["instances"]}
        raw_ids = {row["id"] for row in raw_by[image_id]["candidates"]}
        review_rows = {row["candidate_id"]: row for row in review_by[image_id]["candidates"]}
        expected = item.get("expected_by_gt", {})
        evidence_ids = item.get("evidence_sufficient_candidate_ids", [])
        if not item.get("constraint_id") or not item.get("question"):
            raise ValueError(f"SEMANTIC_SPEC_CONSTRAINT_MISSING:{image_id}")
        if not set(expected) <= set(gt_rows) or not set(expected.values()) <= {"YES", "NO"}:
            raise ValueError(f"SEMANTIC_SPEC_EXPECTATION_INVALID:{image_id}")
        if len(evidence_ids) != len(set(evidence_ids)) or not set(evidence_ids) <= raw_ids:
            raise ValueError(f"SEMANTIC_SPEC_EVIDENCE_SET_INVALID:{image_id}")
        for candidate_id in evidence_ids:
            review = review_rows[candidate_id]
            if _attribute(review, "YES", True, "YES") == "DETECTOR_DOWNSTREAM_UNUSABLE":
                raise ValueError(f"SEMANTIC_SPEC_EVIDENCE_ON_UNUSABLE_CANDIDATE:{image_id}:{candidate_id}")
            mapped_gt = review["mapped_gt_instance_id"]
            if mapped_gt not in expected:
                raise ValueError(f"SEMANTIC_SPEC_EVIDENCE_WITHOUT_EXPECTATION:{image_id}:{candidate_id}")
            if gt_rows[mapped_gt]["semantic_visibility"] != "sufficient":
                raise ValueError(f"SEMANTIC_SPEC_EVIDENCE_CONFLICTS_WITH_GT:{image_id}:{candidate_id}")
    return spec, hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest()


def _attribute(review: dict, expected: str | None, evidence_sufficient: bool, verdict: str | None) -> str:
    human_usable = (
        review["classification"] in {"VALID_INSTANCE", "PARTIAL_INSTANCE", "DUPLICATE_INSTANCE"}
        and review["completeness"] in {"COMPLETE", "USABLE_PARTIAL"}
    )
    if not human_usable or not evidence_sufficient:
        return "DETECTOR_DOWNSTREAM_UNUSABLE"
    if expected not in {"YES", "NO"} or verdict not in {"YES", "NO", "UNCLEAR"}:
        return "NOT_EVALUABLE_SEMANTIC"
    return "VLM_CORRECT" if verdict == expected else "VLM_SEMANTIC_LIMIT"


def main() -> None:
    store = CandidateReviewStore(ROOT)
    if not all(e["review_status"] == "COMPLETE" and e["reviewed_by"] == "human" for e in store.document["images"]):
        raise RuntimeError("CANDIDATE_REVIEW_NOT_HUMAN_CONFIRMED")
    spec, spec_sha256 = _load_and_validate_spec(store)
    client = _client()
    manifest_by = {item["image_id"]: item for item in store.gt.manifest["images"]}
    review_by = {item["image_id"]: item for item in store.document["images"]}
    raw_by = {item["image_id"]: item for item in store.raw["images"]}
    spec_by = {item["image_id"]: item for item in spec["images"]}

    results = {
        "benchmark_version": "1.0", "model": VLM_MODEL,
        "provider": "dashscope_openai_compatible", "prompt_version": PROMPT_VERSION,
        "probe_type": PROBE_TYPE, "semantic_spec_sha256": spec_sha256,
        "raw_candidates_sha256": store.raw_sha256,
        "review_sha256": hashlib.sha256(store.review_path.read_bytes()).hexdigest(),
        "gt_fingerprint": store.gt.fingerprint(),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "image_leaves_machine": True, "images": [],
    }
    for image_id in (item["image_id"] for item in store.gt.test_images):
        constraint = spec_by[image_id]
        expected_by_gt = constraint["expected_by_gt"]
        evidence_ids = set(constraint["evidence_sufficient_candidate_ids"])
        reviews = {row["candidate_id"]: row for row in review_by[image_id]["candidates"]}
        raw_candidates = {row["id"]: row for row in raw_by[image_id]["candidates"]}
        rows = []
        for candidate_id, review in reviews.items():
            mapped_gt = review["mapped_gt_instance_id"]
            expected = expected_by_gt.get(mapped_gt)
            evidence_sufficient = candidate_id in evidence_ids
            verdict = None
            if evidence_sufficient:
                data_url = _crop_data_url(ROOT / manifest_by[image_id]["relative_path"], raw_candidates[candidate_id]["bbox"])
                verdict = _probe_vlm(client, data_url, constraint["question"])
            rows.append({
                "id": candidate_id, "constraint_id": constraint["constraint_id"],
                "mapped_gt_instance_id": mapped_gt, "expected": expected,
                "evidence_sufficient": evidence_sufficient, "verdict": verdict,
                "attribution": _attribute(review, expected, evidence_sufficient, verdict),
            })
        results["images"].append({
            "image_id": image_id, "constraint_id": constraint["constraint_id"],
            "question": constraint["question"], "candidates": rows,
        })

    out_path = ROOT / "runs" / "grounding_dino_base" / "semantic_results.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    attribution = Counter(row["attribution"] for image in results["images"] for row in image["candidates"])
    print("wrote " + str(out_path))
    print("attribution:", dict(attribution))


if __name__ == "__main__":
    main()
