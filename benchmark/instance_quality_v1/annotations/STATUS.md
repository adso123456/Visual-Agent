# Manual ground-truth status

Status: `BLOCKED_BY_MANUAL_GT`

All 24 Test images require independent manual GT before the benchmark can be
frozen. In particular, the dense, small/distant, occlusion, and scale-variation
images contain instances that cannot be exhaustively and reliably boxed from
the available inspection view without an independent annotation pass.

Detector, Qwen, SAM, or any other model output must not be used to fill this
file. No partial GT is represented as an official baseline.

Pending image IDs:

- TST_SPARSE_001 through TST_SPARSE_003
- TST_ADJACENT_001 through TST_ADJACENT_003
- TST_DENSE_001 through TST_DENSE_003
- TST_SMALL_001 through TST_SMALL_003
- TST_OCCLUSION_001 through TST_OCCLUSION_003
- TST_SCALE_001 through TST_SCALE_003
- TST_INTERFERENCE_001 through TST_INTERFERENCE_003
- TST_DOMAIN_001 through TST_DOMAIN_003

The local manual tool is now available. Start it from the repository root:

```powershell
python -m benchmark.instance_quality_v1.annotation_tool
```
