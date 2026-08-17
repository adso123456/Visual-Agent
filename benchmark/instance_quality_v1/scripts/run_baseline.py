import argparse
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path

import torch
import transformers
from PIL import Image, ImageDraw, ImageFont

from visual_agent.grounding import GroundingDetector


ROOT = Path(__file__).resolve().parents[1]


def annotate(image_path, candidates, output_path):
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(14, min(image.size) // 35))
    width = max(2, min(image.size) // 250)
    for candidate in candidates:
        draw.rectangle(candidate["bbox"], outline="#ff0000", width=width)
        draw.text((candidate["bbox"][0], max(0, candidate["bbox"][1] - 20)), candidate["id"], fill="#ff0000", font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=92)


def percentile(values, fraction):
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def main():
    parser = argparse.ArgumentParser(description="Run the frozen Grounding DINO Base benchmark")
    parser.add_argument("--image-id", action="append", help="Run only the specified Test image; repeatable")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "configs" / "grounding_dino_base.json").read_text(encoding="utf-8"))
    output = ROOT / "runs" / "grounding_dino_base"
    output.mkdir(parents=True, exist_ok=True)
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    detector = GroundingDetector()
    load_seconds = time.perf_counter() - started
    selected = set(args.image_id or [])
    test_ids = {item["image_id"] for item in manifest["images"] if item["split"] == "test"}
    unknown = sorted(selected - test_ids)
    if unknown:
        raise ValueError(f"unknown Test image IDs: {unknown}")
    aggregate_path = output / "candidates.json"
    previous = json.loads(aggregate_path.read_text(encoding="utf-8")) if selected and aggregate_path.exists() else None
    previous_rows = {item["image_id"]: item for item in previous.get("images", [])} if previous else {}
    rows, latencies = [], []
    for item in manifest["images"]:
        if item["split"] != "test" or (selected and item["image_id"] not in selected):
            continue
        image_path = ROOT / item["relative_path"]
        source_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
        with Image.open(image_path) as source_image:
            source_width, source_height = source_image.size
        if source_sha256 != item["sha256"] or (source_width, source_height) != (item["width"], item["height"]):
            raise RuntimeError(f"MANIFEST_IMAGE_BINDING_INVALID: {item['image_id']}")
        started = time.perf_counter()
        detections = detector.detect(image_path, item["target_object"], threshold=config["box_threshold"])
        latency = time.perf_counter() - started
        latencies.append(latency)
        candidates = [{"id": f"C{index:03d}", **candidate} for index, candidate in enumerate(detections, 1)]
        row = {
            "image_id": item["image_id"], "target_object": item["target_object"],
            "source_image_sha256": source_sha256, "source_width": source_width, "source_height": source_height,
            "detector_model": config["model"], "box_threshold": config["box_threshold"],
            "text_threshold": config["text_threshold"], "full_frame": config["full_frame"],
            "latency_seconds": round(latency, 6), "candidates": candidates,
        }
        rows.append(row)
        (output / f"{item['image_id']}_candidates.json").write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        annotate(image_path, candidates, output / f"{item['image_id']}_detector.jpg")
        print(f"{item['image_id']}: {len(candidates)} candidates / {latency:.2f}s", flush=True)
    current_runtime = {
        "model_load_seconds": round(load_seconds, 6), "mean_detection_latency_seconds": round(statistics.mean(latencies), 6),
        "p50_detection_latency_seconds": round(statistics.median(latencies), 6), "p95_detection_latency_seconds": round(percentile(latencies, 0.95), 6),
        "device": detector.device, "cuda_available": torch.cuda.is_available(),
        "peak_vram_bytes": torch.cuda.max_memory_allocated() if torch.cuda.is_available() else "not_available",
        "torch_version": torch.__version__, "transformers_version": transformers.__version__, "python_version": platform.python_version(),
        "batch_support": "not_measured; production detect() accepts one image", "dependency_complexity": "Existing local PyTorch and Transformers stack; no dependency added.",
    }
    if selected and previous:
        previous_rows.update({item["image_id"]: item for item in rows})
        ordered_ids = [item["image_id"] for item in manifest["images"] if item["split"] == "test"]
        rows = [previous_rows[image_id] for image_id in ordered_ids]
        runtime = previous.get("runtime", {})
        runtime.setdefault("binding_repair_runs", []).append({"image_ids": sorted(selected), **current_runtime})
    else:
        runtime = current_runtime
    payload = {"benchmark_version": manifest["benchmark_version"], "detector_config": config, "runtime": runtime, "images": rows}
    aggregate_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(current_runtime, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
