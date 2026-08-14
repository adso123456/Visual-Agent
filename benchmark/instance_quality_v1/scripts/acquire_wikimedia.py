"""Acquire the frozen redistributable catalog from Wikimedia Commons."""

import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
API = "https://commons.wikimedia.org/w/api.php"
ALLOWED_LICENSES = {"Public domain", "CC0", "CC BY 2.0", "CC BY 3.0", "CC BY 4.0", "CC BY-SA 2.0", "CC BY-SA 3.0", "CC BY-SA 4.0"}


def plain(value):
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def request_json(titles):
    query = urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "imageinfo", "titles": "|".join(titles),
        "iiprop": "url|extmetadata|size", "iiurlwidth": "1280", "maxlag": "5",
    })
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": "Visual-Agent-Benchmark/1.0 (https://github.com/adso123456/Visual-Agent)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def download(url, path):
    for wait_seconds in (0, 10, 30, 60):
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Visual-Agent-Benchmark/1.0 (https://github.com/adso123456/Visual-Agent)"})
            with urllib.request.urlopen(request, timeout=120) as response:
                path.write_bytes(response.read())
            return
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
    raise RuntimeError(f"Wikimedia rate limit did not clear: {url}")


def main():
    catalog = json.loads((ROOT / "asset_catalog.json").read_text(encoding="utf-8"))
    assets = catalog["assets"]
    metadata = {}
    for offset in range(0, len(assets), 10):
        payload = request_json([item["title"] for item in assets[offset:offset + 10]])
        for page in payload["query"]["pages"].values():
            metadata[page["title"]] = page["imageinfo"][0]
        time.sleep(3)

    manifest, provenance = [], []
    for item in assets:
        info = metadata[item["title"]]
        ext = info["extmetadata"]
        license_name = plain(ext.get("LicenseShortName", {}).get("value"))
        if license_name not in ALLOWED_LICENSES:
            raise RuntimeError(f"License is not allowed: {item['title']} / {license_name}")
        output_dir = ROOT / item["split"]
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(urllib.parse.urlparse(info["thumburl"]).path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        path = output_dir / f"{item['image_id']}{suffix}"
        download(info["thumburl"], path)
        time.sleep(4)
        with Image.open(path) as image:
            width, height = image.size
        attribution = plain(ext.get("Artist", {}).get("value")) or plain(ext.get("Credit", {}).get("value")) or "See source page"
        source_url = info["descriptionurl"]
        record = {
            **item,
            "relative_path": path.relative_to(ROOT).as_posix(), "width": width, "height": height,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "source": "Wikimedia Commons",
            "source_url": source_url, "license": license_name, "attribution": attribution,
            "original_filename": item["title"].removeprefix("File:"),
            "acquisition_note": "1280-pixel thumbnail from Wikimedia Commons API; license inherited from file page.",
        }
        record.pop("title")
        manifest.append(record)
        provenance.append({
            "image_id": item["image_id"], "commons_title": item["title"], "source_url": source_url,
            "download_url": info["thumburl"], "license": license_name,
            "license_url": plain(ext.get("LicenseUrl", {}).get("value")), "attribution": attribution,
            "retrieved_utc": "2026-08-13",
        })
    (ROOT / "manifest.json").write_text(json.dumps({"benchmark_version": "1.0", "images": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "provenance.json").write_text(json.dumps({"benchmark_version": "1.0", "assets": provenance}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Acquired {len(manifest)} assets with explicit licenses.")


if __name__ == "__main__":
    main()
