"""为最终人工审查生成原图/当前输出并排证据页。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1\_general_rgb_final_acceptance_v1")
RAW = ROOT / "raw_execution.jsonl"
OUT = ROOT / "review_sheets"
REPO = Path(r"E:\3\Visual Agent\Visual-Agent")
FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")


def git_json(path: str):
    raw = subprocess.check_output(
        ["git", "show", f"origin/local-vlm-quality-evidence-v1:{path}"],
        cwd=REPO,
    )
    return json.loads(raw.decode("utf-8"))


def fitted(image_path: str, box: tuple[int, int]) -> Image.Image:
    image = Image.open(image_path).convert("RGB")
    image.thumbnail(box, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", box, "#eef1f5")
    canvas.paste(image, ((box[0] - image.width) // 2, (box[1] - image.height) // 2))
    return canvas


def build_pages(name: str, rows: list[dict], subtitle) -> None:
    normal = ImageFont.truetype(str(FONT_PATH), 23)
    small = ImageFont.truetype(str(FONT_PATH), 18)
    for page_no in range(0, len(rows), 2):
        page_rows = rows[page_no : page_no + 2]
        page = Image.new("RGB", (1600, 2200), "white")
        draw = ImageDraw.Draw(page)
        draw.text((40, 25), f"{name} review page {page_no // 2 + 1}", fill="black", font=normal)
        for row_index, row in enumerate(page_rows):
            top = 90 + row_index * 1040
            label = f"{row['unit_id']} | {subtitle(row)} | targets={row.get('target_count')}"
            draw.text((40, top), label, fill="black", font=normal)
            prompt = row["prompt"]
            draw.text((40, top + 42), f"Prompt: {prompt}", fill="#222222", font=small)
            original = fitted(row["image_path"], (740, 880))
            result = fitted(row["result_image"], (740, 880))
            page.paste(original, (30, top + 100))
            page.paste(result, (830, top + 100))
            draw.text((320, top + 985), "ORIGINAL", fill="#555555", font=small)
            draw.text((1110, top + 985), "CURRENT OUTPUT", fill="#555555", font=small)
        page.save(OUT / f"{name}_{page_no // 2 + 1:02d}.jpg", quality=92)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line]
    manifest = git_json("evidence/manifest.json")
    historical = {item["case_id"]: item for item in manifest["cases"]}

    core = [row for row in rows if row["suite"] == "core"]
    challenge = [row for row in rows if row["suite"] == "challenge"]
    changed = [
        row
        for row in rows
        if row["suite"] == "real_world_fishing"
        and not row["frozen_invalid"]
        and row["result_image_sha256"] != historical[row["case_id"]]["local_output"]["sha256"]
    ]
    build_pages(
        "core",
        core,
        lambda row: f"expected={row['expected']['target_description']} / count={row['expected']['target_count']}",
    )
    build_pages(
        "challenge",
        challenge,
        lambda row: f"expected={row['expected']['target_description']} / count={row['expected']['target_count']}",
    )
    build_pages(
        "changed_real_world",
        changed,
        lambda row: f"GT={row['ground_truth_class']}",
    )
    print(json.dumps({"core": len(core), "challenge": len(challenge), "changed_real_world": len(changed)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
