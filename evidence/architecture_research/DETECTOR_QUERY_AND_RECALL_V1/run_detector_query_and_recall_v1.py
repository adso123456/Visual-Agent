"""运行 DETECTOR_QUERY_AND_RECALL_V1 的冻结离线探针。

只调用当前 Production Grounding DINO Base，固定阈值 0.3；不调用 VLM，
不修改 Production。输出原始 bbox、几何统计和审查用标框图。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from PIL import Image, ImageDraw

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from visual_agent.grounding import MODEL_NAME, GroundingDetector


DATA_ROOT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1")
OUTPUT = DATA_ROOT / "_detector_query_and_recall_v1"
RAW_RESULTS = OUTPUT / "raw_results.json"
THRESHOLD = 0.3

CASES = [
    # bucket/pail：三个正例和一个无桶真阴性。
    {"case_id": "F3::fishing_003.jpeg", "path": DATA_ROOT / "fishing" / "fishing_003.jpeg", "queries": ["bucket", "pail"], "reference": "exact:2", "group": "bucket_lexical"},
    {"case_id": "F3::fishing_017.jpeg", "path": DATA_ROOT / "fishing" / "fishing_017.jpeg", "queries": ["bucket", "pail"], "reference": "exact:1", "group": "bucket_lexical"},
    {"case_id": "F3::fishing_019.jpeg", "path": DATA_ROOT / "fishing" / "fishing_019.jpeg", "queries": ["bucket", "pail"], "reference": "exact:1", "group": "bucket_lexical"},
    {"case_id": "F3::fishing_018.jpeg", "path": DATA_ROOT / "fishing" / "fishing_018.jpeg", "queries": ["bucket", "pail"], "reference": "exact:0", "group": "bucket_lexical"},
    # bottle/plastic bottle：可数、普通多实例、稠密重叠和无瓶真阴性。
    {"case_id": "P2::pollution_009.jpeg", "path": DATA_ROOT / "water_pollution" / "pollution_009.jpeg", "queries": ["bottle", "plastic bottle"], "reference": "exact:2", "group": "bottle_lexical"},
    {"case_id": "P2::pollution_010.jpeg", "path": DATA_ROOT / "water_pollution" / "pollution_010.jpeg", "queries": ["bottle", "plastic bottle"], "reference": "multiple_distinct", "group": "bottle_lexical"},
    {"case_id": "P2::pollution_012.jpeg", "path": DATA_ROOT / "water_pollution" / "pollution_012.jpeg", "queries": ["bottle", "plastic bottle"], "reference": "dense_many", "group": "bottle_lexical"},
    {"case_id": "P2::pollution_014.jpeg", "path": DATA_ROOT / "water_pollution" / "pollution_014.jpeg", "queries": ["bottle", "plastic bottle"], "reference": "exact:0", "group": "bottle_lexical"},
    # 稠密垃圾：只评估候选拓扑，不声称人工精确实例数。
    {"case_id": "P1::pollution_002.jpeg", "path": DATA_ROOT / "water_pollution" / "pollution_002.jpeg", "queries": ["garbage", "trash", "debris"], "reference": "dense_many", "group": "dense_capability"},
    {"case_id": "P1::pollution_004.png", "path": DATA_ROOT / "water_pollution" / "pollution_004.png", "queries": ["garbage", "trash", "debris"], "reference": "dense_many", "group": "dense_capability"},
    # P3 的 localization_target=object 较弱，测试 bounded query 是否仍受 detector 能力限制。
    {"case_id": "P3::pollution_010.jpeg", "path": DATA_ROOT / "water_pollution" / "pollution_010.jpeg", "queries": ["object", "debris", "floating object"], "reference": "multiple_distinct", "group": "weak_localization"},
    {"case_id": "P3::pollution_012.jpeg", "path": DATA_ROOT / "water_pollution" / "pollution_012.jpeg", "queries": ["object", "debris", "floating object"], "reference": "dense_many", "group": "weak_localization"},
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def geometry(detections: list[dict], width: int, height: int) -> dict:
    areas = []
    for item in detections:
        x1, y1, x2, y2 = item["bbox"]
        areas.append(max(0.0, x2 - x1) * max(0.0, y2 - y1) / (width * height))
    return {
        "candidate_count": len(detections),
        "largest_area_ratio": round(max(areas, default=0.0), 6),
        "near_full_scene_count": sum(area >= 0.5 for area in areas),
        "group_region_count": sum(area >= 0.1 for area in areas),
    }


def render_overlay(path: Path, query: str, detections: list[dict], destination: Path) -> None:
    with Image.open(path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    line_width = max(3, round(max(image.size) / 500))
    for index, item in enumerate(detections, 1):
        box = tuple(item["bbox"])
        draw.rectangle(box, outline=(255, 0, 0), width=line_width)
        draw.text((box[0] + 3, box[1] + 3), f"{index}:{item['confidence']:.2f}", fill=(255, 0, 0), stroke_width=2, stroke_fill="white")
    image.thumbnail((1600, 1200), Image.Resampling.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "JPEG", quality=88, optimize=True)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    detector = GroundingDetector()
    rows = []
    for case_index, case in enumerate(CASES, 1):
        path = case["path"]
        with Image.open(path) as image:
            width, height = image.size
        query_rows = []
        for query_index, query in enumerate(case["queries"], 1):
            started = time.perf_counter()
            detections = detector.detect(path, query, threshold=THRESHOLD)
            elapsed = time.perf_counter() - started
            overlay_name = f"{case['case_id'].replace('::', '__').replace('.', '_')}__{query_index}_{query.replace(' ', '_')}.jpg"
            render_overlay(path, query, detections, OUTPUT / "overlays" / overlay_name)
            query_rows.append({
                "query": query,
                "role": "canonical" if query_index == 1 else "bounded_alias",
                "elapsed_seconds": round(elapsed, 4),
                "geometry": geometry(detections, width, height),
                "detections": detections,
                "overlay": f"overlays/{overlay_name}",
            })
        row = {
            "case_id": case["case_id"],
            "group": case["group"],
            "reference": case["reference"],
            "image_path": str(path),
            "image_sha256": sha256(path),
            "image_size": [width, height],
            "queries": query_rows,
        }
        rows.append(row)
        print(f"{case_index:02d}/{len(CASES)} {case['case_id']}: " + ", ".join(f"{q['query']}={q['geometry']['candidate_count']}" for q in query_rows), flush=True)
    payload = {
        "contract": {
            "phase": "DETECTOR_QUERY_AND_RECALL_V1",
            "production_modified": False,
            "model": MODEL_NAME,
            "threshold": THRESHOLD,
            "case_count": len(CASES),
            "query_call_count": sum(len(case["queries"]) for case in CASES),
            "dense_reference_rule": "不声明人工精确数量，只审查逐实例、分组大框或无召回的候选拓扑",
        },
        "runtime": {
            "device": detector.device,
            "model_load_seconds": round(detector.load_seconds, 4),
            "gpu_memory_after_load_mb": round(detector.memory_after_load_mb, 2),
        },
        "cases": rows,
    }
    RAW_RESULTS.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RAW_RESULTS={RAW_RESULTS}")


if __name__ == "__main__":
    main()
