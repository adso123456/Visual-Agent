# Instance Quality Benchmark v1.0

This directory implements the detector evaluation rules in
`VISUAL_AGENT_PERCEPTION_CONTRACT_V1.0.md`. Production code must never import
this package.

## Frozen boundaries

- Test: at least 24 images, all eight scenarios, at least three per scenario.
- Calibration: 5 to 10 images, strictly isolated from Test.
- Base: `IDEA-Research/grounding-dino-base`, full-frame, box/text thresholds 0.30.
- No Tile, SAHI, instance dedup repair, instance resolver, or SAM consolidation.
- Ground truth and candidate reviews are manual. Detector/VLM/SAM output is not GT.
- IQS is `NOT_DEFINED_V1`.

## Layout

- `test/`, `calibration/`: redistributable benchmark images.
- `manifest.json`, `provenance.json`: frozen asset metadata and licenses.
- `annotations/`: manual GT (pending until the manual-GT blocker is resolved).
- `reviews/`: manual candidate reviews.
- `configs/`: frozen Base configuration.
- `runs/grounding_dino_base/`: raw candidates, previews, and timing.
- `reports/`: machine-readable and Markdown reports.
- `scripts/`: acquisition, validation, baseline, and evaluation entry points.
- `tests/`: model-independent evaluator fixtures.

## Commands

```powershell
python -m benchmark.instance_quality_v1.scripts.validate
python -m benchmark.instance_quality_v1.scripts.run_baseline
python -m benchmark.instance_quality_v1.scripts.evaluate
python -m benchmark.instance_quality_v1.tests.test_evaluator
```

The official baseline report cannot be generated until every Test image has
reliable manual GT and every Base candidate has a complete manual review.

## Local manual annotation tool

Start Ground Truth mode from the repository root:

```powershell
python -m benchmark.instance_quality_v1.annotation_tool
```

GT MODE NEVER LOADS DETECTOR OUTPUTS. Its import and file-access path contains
only the manifest, original Test images, the manual GT file, and shared schema
enums. It does not import Detector, Qwen, SAM, or candidate-review code.

GT controls:

- Left drag on empty image space: create a bbox, then enter all metadata.
- Left drag inside a selected bbox: move it.
- Left drag its lower-right handle: resize it.
- Double-click a selected bbox: edit its metadata.
- Delete: confirm and delete the selected instance. Existing IDs are not renumbered.
- Mouse wheel: zoom around the cursor; middle/right drag: pan; `0`: reset zoom.
- Left/Right arrows: previous/next image; Escape: cancel drawing; Ctrl+S: validate and save.
- `Mark Image Complete` is an explicit whole-image confirmation. It also supports
  a genuinely zero-instance image; merely saving a bbox never marks completion.
- `Overview` shows every image, status, GT count, and per-scenario completion.
- `Load Assistant Draft` loads an orange-status visual draft for the current
  image. Drafts were made from original images only, without Detector/Qwen/SAM.
  Loading never marks an image complete: the header shows
  `review=pending_human_review` until you inspect/edit the entire image and
  explicitly click `Mark Image Complete`.

Saved bboxes always use original-image pixel coordinates. Every add, move,
resize, metadata edit, delete, and completion change is schema-validated and
atomically autosaved. Original image files are read-only.

GT metadata definitions:

- `visibility`: `full`, `partial`, or `heavily_occluded` visible target extent.
- `scale`: manual `large`, `medium`, or `small` judgment.
- `crowding`: `isolated`, `adjacent`, or `dense` instance context.
- `semantic_visibility`: whether the visible evidence is `sufficient` or
  `insufficient` for downstream semantic judgment; it is never inferred from size.
- `evaluable`: whether a reliable benchmark judgment is possible. A false value
  requires a non-empty human explanation in `notes`.

Each image remains `UNSTARTED` or `IN_PROGRESS` until explicitly marked
`COMPLETE`. After all 24 images are complete, use the GUI's `Freeze GT` button
or this equivalent command:

```powershell
python -m benchmark.instance_quality_v1.annotation_tool.freeze_gt
```

Freezing creates a deterministic GT fingerprint and makes GT read-only. A real
correction requires the explicit developer command below, which appends an audit
event with reason, image ID, timestamp, and changed fields:

```powershell
python -m benchmark.instance_quality_v1.annotation_tool.unfreeze_gt `
  --reason "annotation correction" --image-id TST_SPARSE_001 `
  --changed-field bbox
```

Candidate Review mode is intentionally separate and refuses to start unless all
24 GT images are complete and frozen:

```powershell
python -m benchmark.instance_quality_v1.annotation_tool --review
```

Review mode displays GT in green and raw candidates in red/yellow. It never
modifies the raw candidate file and never auto-matches or auto-classifies a
candidate. Every candidate must receive a manual review before an image can be
marked Review COMPLETE.
