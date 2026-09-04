# Visual Agent Developer Demo v1

本地零依赖 Web 演示界面（仅使用 Python 标准库，不引入 Flask/Gradio）。

极简界面：上传图片 → 输入自然语言指令 → 运行 → 查看原图与结果图。

## 运行

```powershell
.venv\Scripts\python.exe -m demo_ui.server --host 127.0.0.1 --port 8080
```

打开 http://127.0.0.1:8080 。

## 使用

1. 点击或拖拽上传一张图片。
2. 输入自然语言任务指令（例如"只给穿红色衣服的人描边"）。
3. 点击「运行」，等待任务完成，查看原始图片与结果图片。
4. 点击结果图片可放大查看。

## 完整链路

执行完整链路需要规划与语义验证凭据；规划端默认走本地 Ollama，语义验证
默认走 Cloud Qwen（详见仓库根目录 README 的模型端点配置表）：

| 环境变量 | 说明 |
|---|---|
| `PLANNER_MODEL` / `PLANNER_BASE_URL` / `PLANNER_API_KEY` | 规划端（默认本地 qwen3.8:27b，无需密钥） |
| `VLM_MODEL` / `VLM_BASE_URL` / `VLM_API_KEY` | 语义验证 VLM（默认 Cloud Qwen，需 `DASHSCOPE_API_KEY`） |

缺少凭据时页面会返回明确错误提示。

## API

- `GET /` UI 页面
- `GET /api/health` 健康检查
- `POST /api/run` 提交任务（multipart: image + prompt + 可选 plan）
- `GET /api/status/<job_id>` 轮询状态与结果摘要
- `GET /api/job/<job_id>/<file>` 获取任务产物（result 图片 / JSON / mask）

## 说明

- Detector（Grounding DINO Base）与 SAM2.1 在进程内只加载一次，后续任务复用。
- 任务在后台线程串行执行（单 worker），模型推理不会被并发任务抢占。
- 输出写入 `demo_ui/outputs/<job_id>/`，上传图片存 `demo_ui/uploads/`。
- 上传图片与任务产物保留 24 小时。服务启动时及每次创建新 job 前，会同时清理超过
  24 小时的 `done` / `error` 任务、对应磁盘文件与内存状态；`queued`、`running`
  和当前正在执行的任务绝不清理。