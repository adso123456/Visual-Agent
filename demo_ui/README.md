# Visual Agent Demo UI

本地零依赖 Web 演示界面（仅使用 Python 标准库，不引入 Flask/Gradio）。

满足 PRD §18 最低需求：图片输入、自然语言输入、执行按钮、结果图片，
并附加 Agent plan / candidate bbox / semantic verification / final targets 调试面板。

## 运行

```powershell
.venv\Scripts\python.exe -m demo_ui.server --host 127.0.0.1 --port 8080
```

打开 http://127.0.0.1:8080 。

## 两种模式

| 模式 | 触发方式 | 依赖 | 链路 |
|---|---|---|---|
| 自然语言（完整链路） | 只填指令，不填 plan | DEEPSEEK_API_KEY + DASHSCOPE_API_KEY | DeepSeek 规划 → DINO → Qwen 验证 → 关系 → SAM2 → Action |
| 预编译计划（本地调试） | 粘贴 plan JSON 或点击示例计划 | 无 API Key，仅本地模型 | DINO → SAM2 → Action（无 LLM 规划与语义验证） |

未设置 API Key 时自动提示切换本地调试模式。本地调试模式明确标注
「无 LLM 验证」，不会把未验证候选当作生产语义结论。

## API

- `GET /` UI 页面
- `GET /api/health` 健康检查
- `POST /api/run` 提交任务（multipart: image + prompt [+ plan]）
- `GET /api/status/<job_id>` 轮询状态与结果摘要
- `GET /api/job/<job_id>/<file>` 获取任务产物（result 图片 / JSON / mask / candidates.png）

## 说明

- Detector（Grounding DINO Base）与 SAM2.1 在进程内只加载一次，后续任务复用。
- 任务在后台线程串行执行（单 worker），模型推理不会被并发任务抢占。
- 输出写入 demo_ui/outputs/<job_id>/，上传图片存 demo_ui/uploads/。
- 语义验证缺失时（本地调试模式），关系任务会如实返回
  related_object_not_detected / binding_not_satisfied 等失败归因，
  不会伪造结果（PRD §16/§23）。
