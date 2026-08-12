# 图片回归测试

Phase 5 使用冻结正式基线运行 15 个 Core、5 个 Challenge，以及 3 组各 3 次重复性测试。

```powershell
.\.venv\Scripts\python.exe benchmark\run_benchmark.py
.\.venv\Scripts\python.exe benchmark\run_repeatability.py
.\.venv\Scripts\python.exe benchmark\generate_report.py
```

`run_benchmark.py` 直接调用 `visual_agent.pipeline.run_pipeline()`，不复制生产逻辑。每个 case 的图片、JSON 和 mask 副本保存在 `benchmark/results/<case_id>/`。

当前 Windows 冻结基线的 renderer 无法读取中文图片路径。`unicode_path_preflight.json` 保留原始失败；正式 manifest 使用内容和 SHA-256 均完全相同的 ASCII 文件名副本继续测试，不修改业务代码。
