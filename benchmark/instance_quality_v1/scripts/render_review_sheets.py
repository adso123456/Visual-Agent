"""Render visual-only candidate review sheets; geometry is displayed as reference only."""

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
COLORS = {"gt": "#00ff66", "candidate": "#ffff00", "other": "#ff4040"}


def iou(left, right):
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = (left[2] - left[0]) * (left[3] - left[1]) + (right[2] - right[0]) * (right[3] - right[1]) - intersection
    return 0 if union <= 0 else intersection / union


def draw_box(draw, box, scale, offset, color, label, width=3):
    coords = [box[index] * scale + offset[index % 2] for index in range(4)]
    draw.rectangle(coords, outline=color, width=width)
    draw.text((coords[0] + 3, coords[1] + 3), label, fill=color, stroke_width=2, stroke_fill="#000000")


def context_box(box, image_size):
    width, height = box[2] - box[0], box[3] - box[1]
    span = max(width, height, min(image_size) * 0.16)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    crop_width, crop_height = span * 1.7, span * 1.35
    x1, y1 = max(0, cx - crop_width / 2), max(0, cy - crop_height / 2)
    x2, y2 = min(image_size[0], cx + crop_width / 2), min(image_size[1], cy + crop_height / 2)
    return [x1, y1, x2, y2]


def render_card(image, candidate, candidates, instances, target_size=(480, 380)):
    header = 54
    crop_box = context_box(candidate["bbox"], image.size)
    crop = image.crop(tuple(crop_box))
    scale = min(target_size[0] / crop.width, (target_size[1] - header) / crop.height)
    shown = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
    card = Image.new("RGB", target_size, "#202124")
    offset = ((target_size[0] - shown.width) / 2, header + (target_size[1] - header - shown.height) / 2)
    card.paste(shown, (round(offset[0]), round(offset[1])))
    draw = ImageDraw.Draw(card)
    shifted = (-crop_box[0] * scale + offset[0], -crop_box[1] * scale + offset[1])
    for item in instances:
        draw_box(draw, item["bbox"], scale, shifted, COLORS["gt"], f"GT {item['instance_id']}", 3)
    for item in candidates:
        if item["id"] != candidate["id"]:
            draw_box(draw, item["bbox"], scale, shifted, COLORS["other"], item["id"], 1)
    draw_box(draw, candidate["bbox"], scale, shifted, COLORS["candidate"], candidate["id"], 4)
    overlaps = sorted(((iou(candidate["bbox"], item["bbox"]), item["instance_id"]) for item in instances), reverse=True)[:3]
    reference = ", ".join(f"{instance_id}:{value:.2f}" for value, instance_id in overlaps if value > 0) or "none"
    draw.text((8, 5), f"{candidate['id']} conf={candidate['confidence']:.4f}  IoU(ref)={reference}", fill="#ffffff")
    draw.text((8, 25), f"bbox={[round(value, 1) for value in candidate['bbox']]}", fill="#dddddd")
    return card


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    ground_truth = json.loads((ROOT / "annotations" / "ground_truth.json").read_text(encoding="utf-8"))
    raw = json.loads((ROOT / "runs" / "grounding_dino_base" / "candidates.json").read_text(encoding="utf-8"))
    meta = {item["image_id"]: item for item in manifest["images"]}
    gt = {item["image_id"]: item for item in ground_truth["images"]}
    for row in raw["images"]:
        image_id = row["image_id"]
        image = Image.open(ROOT / meta[image_id]["relative_path"]).convert("RGB")
        overview = image.copy()
        draw = ImageDraw.Draw(overview)
        for item in gt[image_id]["instances"]:
            draw_box(draw, item["bbox"], 1, (0, 0), COLORS["gt"], f"GT {item['instance_id']}", max(3, min(image.size) // 220))
        for item in row["candidates"]:
            draw_box(draw, item["bbox"], 1, (0, 0), COLORS["other"], item["id"], max(2, min(image.size) // 300))
        overview.thumbnail((1800, 1400), Image.Resampling.LANCZOS)
        overview.save(output / f"{image_id}_overview.jpg", quality=94)
        cards = [render_card(image, item, row["candidates"], gt[image_id]["instances"]) for item in row["candidates"]]
        for page in range(math.ceil(len(cards) / 12)):
            selected = cards[page * 12:(page + 1) * 12]
            sheet = Image.new("RGB", (1920, 1140), "#111111")
            for index, card in enumerate(selected):
                sheet.paste(card, ((index % 4) * 480, (index // 4) * 380))
            sheet.save(output / f"{image_id}_cards_{page + 1:02d}.jpg", quality=94)


if __name__ == "__main__":
    main()
