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
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "configs" / "grounding_dino_base.json").read_text(encoding="utf-8"))
    output = ROOT / "runs" / "grounding_dino_base"
    output.mkdir(parents=True, exist_ok=True)
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    detector = GroundingDetector()
    load_seconds = time.perf_counter() - started
    rows, latencies = [], []
    for item in manifest["images"]:
        if item["split"] != "test":
            continue
        image_path = ROOT / item["relative_path"]
        started = time.perf_counter()
        detections = detector.detect(image_path, item["target_object"], threshold=config["box_threshold"])
        latency = time.perf_counter() - started
        latencies.append(latency)
        candidates = [{"id": f"C{index:03d}", **candidate} for index, candidate in enumerate(detections, 1)]
        row = {"image_id": item["image_id"], "target_object": item["target_object"], "latency_seconds": round(latency, 6), "candidates": candidates}
        rows.append(row)
        (output / f"{item['image_id']}_candidates.json").write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        annotate(image_path, candidates, output / f"{item['image_id']}_detector.jpg")
        print(f"{item['image_id']}: {len(candidates)} candidates / {latency:.2f}s", flush=True)
    runtime = {
        "model_load_seconds": round(load_seconds, 6), "mean_detection_latency_seconds": round(statistics.mean(latencies), 6),
        "p50_detection_latency_seconds": round(statistics.median(latencies), 6), "p95_detection_latency_seconds": round(percentile(latencies, 0.95), 6),
        "device": detector.device, "cuda_available": torch.cuda.is_available(),
        "peak_vram_bytes": torch.cuda.max_memory_allocated() if torch.cuda.is_available() else "not_available",
        "torch_version": torch.__version__, "transformers_version": transformers.__version__, "python_version": platform.python_version(),
        "batch_support": "not_measured; production detect() accepts one image", "dependency_complexity": "Existing local PyTorch and Transformers stack; no dependency added.",
    }
    payload = {"benchmark_version": "1.0", "detector_config": config, "runtime": runtime, "images": rows}
    (output / "candidates.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(runtime, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
