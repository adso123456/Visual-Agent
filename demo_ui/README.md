# Visual Agent Developer Demo v1

本地零依赖 Web 演示界面（仅使用 Python 标准库，不引入 Flask/Gradio）。

用于开发者浏览 Visual Agent 完整执行链。页面展示 Original / Result、Agent Plan、
Detector Candidates、Semantic Verification、Final Targets 与 pipeline 实际 timing。

## 运行

```powershell
.venv\Scripts\python.exe -m demo_ui.server --host 127.0.0.1 --port 8080
```

打开 http://127.0.0.1:8080 。

## 两种模式

| 模式 | 触发方式 | 依赖 | 链路 |
|---|---|---|---|
| Full Chain | 只填指令，不填 plan | DEEPSEEK_API_KEY + DASHSCOPE_API_KEY | DeepSeek 规划 → DINO → Qwen 验证 → 关系 → SAM2 → Action |
| Local Debug | 粘贴 plan JSON 或点击示例 | 无 API Key，仅本地模型 | DINO → SAM2 → Action（Agent / Qwen 均跳过） |

Local Debug 使用 precompiled plan，仅供本地调试，不代表完整自然语言 Agent/VLM
链路。页面中的 Candidate、Semantic、Target 和 Timing 均直接来自 `run_pipeline`
结果，不在 Demo 层重新判断或过滤。

## 固定示例

- 只给穿红色衣服的人描边
- 把拿雨伞的人单独抠出来
- 把正在钓鱼的人高亮

## API

- `GET /` UI 页面
- `GET /api/health` 健康检查
- `POST /api/run` 提交任务（multipart: image + prompt [+ plan]）
- `GET /api/status/<job_id>` 轮询状态与结果摘要
- `GET /api/job/<job_id>/<file>` 获取任务产物（result 图片 / JSON / mask / candidates.png）

## 说明

- Detector（Grounding DINO Base）与 SAM2.1 在进程内只加载一次，后续任务复用。
- 任务在后台线程串行执行（单 worker），模型推理不会被并发任务抢占。
- 输出写入 `demo_ui/outputs/<job_id>/`，上传图片存 `demo_ui/uploads/`。
- 上传图片与任务产物保留 24 小时。服务启动时及每次创建新 job 前，会同时清理超过
  24 小时的 `done` / `error` 任务、对应磁盘文件与内存状态；`queued`、`running`
  和当前正在执行的任务绝不清理。
- 语义验证缺失时（本地调试模式），关系任务会如实返回
  related_object_not_detected / binding_not_satisfied 等失败归因，
  不会伪造结果（PRD §16/§23）。
