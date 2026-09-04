# Visual Agent API Usage（Batch V1）

`api/` 是 Visual Agent 当前版本的正式 HTTP 调用入口。它不依赖 Demo UI：
单图与批量任务都进入后台线程 worker queue，调用同一个
`visual_agent.pipeline.run_pipeline()`，任务状态保存在进程内存，
产物落在 `api/storage/` 目录。

**部署定位：本机 / 内网 / 受控服务调用**，不是面向公网多租户的生产 API 平台。
V1 明确不包含鉴权、持久化任务存储、分布式队列、限流、产物 TTL、崩溃恢复
与多实例协调；这些不属于视觉 Agent 核心目标，`api/jobs.py` 也将 V1 定义为
"不引入 Redis/Celery/数据库，状态在进程内"。

## 架构

```text
FastAPI HTTP 接口 + 后台线程 worker queue
（queue.Queue + threading.Thread，不是 asyncio worker）

POST /api/v1/tasks  → 202 立即返回 task_id
        ↓ 写入内存 job 表 + 入队
worker 线程执行 run_pipeline()（串行，默认 1 个 worker）
        ↓
GET /api/v1/tasks/{task_id} 轮询 → success / failed
```

## 启动

```powershell
# 正式本地配置：必须显式设置以下 6 个变量（代码不回退 Cloud key）
$env:PLANNER_MODEL = "qwen3.8:27b-mtp-q4_K_M"
$env:PLANNER_BASE_URL = "http://192.168.250.9:11434/v1"
$env:PLANNER_API_KEY = "ollama"
$env:VLM_MODEL = "qwen3.8:27b-mtp-q4_K_M"
$env:VLM_BASE_URL = "http://192.168.250.9:11434/v1"
$env:VLM_API_KEY = "ollama"

# worker 并发数，V1 建议保持 1（单 runner 串行，避免抢占模型推理）
$env:MAX_CONCURRENT_JOBS = "1"

.\.venv\Scripts\python.exe -m api.server --host 0.0.0.0 --port 8000
```

> `PLANNER_API_KEY` / `VLM_API_KEY` 是 OpenAI-compatible client 要求的显式占位值；
> 本地 Ollama 不校验该值。注意：正式配置必须显式设置全部 6 个 `PLANNER_*`/`VLM_*`
> 变量，不能只清空 Cloud key 后依赖代码默认值。
> 可选 `--data-dir` 指定上传与产物根目录（默认 `api/storage`）。

## 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/tasks` | 单图任务，multipart：`image` + `prompt`，立即返回 `task_id` |
| `GET` | `/api/v1/tasks/{task_id}` | 查询任务状态、结果摘要与产物地址 |
| `GET` | `/api/v1/tasks/{task_id}/artifacts/{name}` | 下载结果图片 / JSON / mask |
| `POST` | `/api/v1/batches` | 批量任务，multipart：`prompt` + `images[]`，立即返回 `batch_id` |
| `GET` | `/api/v1/batches/{batch_id}` | 查询 `total / completed / failed` 与逐图状态 |
| `GET` | `/api/v1/health` | 健康检查 |

## 上传边界（调用方必须知道）

- 单图最大 **64 MiB**。
- 单批最大 **32 张**。
- 批量上传**逐图有界读取**，每次只保留一张图片的字节，不会先把整批图片
  全部读入 Python 内存。
- 支持格式：`.jpg` / `.jpeg` / `.png` / `.webp` / `.bmp`。

## 单图调用流程

### 1. 提交任务

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tasks \
  -F "image=@images/test_images/benchmark_fishing_clear.png" \
  -F "prompt=把正在钓鱼的人高亮"
```

返回（HTTP 202）：

```json
{
  "task_id": "6f3c9a2b1d4e5f07",
  "status": "queued"
}
```

### 2. 轮询状态

```bash
curl http://127.0.0.1:8000/api/v1/tasks/6f3c9a2b1d4e5f07
```

任务状态机：`queued` → `running` → `success` / `failed`。

成功时返回：

```json
{
  "task_id": "6f3c9a2b1d4e5f07",
  "status": "success",
  "prompt": "把正在钓鱼的人高亮",
  "image_name": "benchmark_fishing_clear.png",
  "result": {
    "summary": {
      "prompt": "把正在钓鱼的人高亮",
      "agent_response": "...",
      "plan": {
        "target_object": "person",
        "label": "正在钓鱼的人",
        "constraints": [{"text": "正在钓鱼", "route": "behavior"}],
        "action": {"type": "highlight"},
        "related_objects": []
      },
      "candidates_count": 3,
      "verified_subjects_count": 1,
      "targets_count": 1,
      "timings": {"grounding_dino_seconds": 1.2, "total_seconds": 15.4}
    },
    "artifacts": [
      {"name": "result_001.json", "url": "/api/v1/tasks/6f3c9a2b1d4e5f07/artifacts/result_001.json"},
      {"name": "result_001.jpg",  "url": "/api/v1/tasks/6f3c9a2b1d4e5f07/artifacts/result_001.jpg"}
    ],
    "result_image": "/api/v1/tasks/6f3c9a2b1d4e5f07/artifacts/result_001.jpg",
    "result_json": "/api/v1/tasks/6f3c9a2b1d4e5f07/artifacts/result_001.json"
  }
}
```

失败时 `status` 为 `failed`，并带 `error` 字段说明原因。

### 3. 下载产物

成功任务会枚举该任务 output 目录中的全部文件形成 `artifacts` 列表，
同时单独给出 `result_image` 与 `result_json` 的 URL：

```bash
curl -o result.jpg "http://127.0.0.1:8000/api/v1/tasks/6f3c9a2b1d4e5f07/artifacts/result_001.jpg"
curl -o result.json "http://127.0.0.1:8000/api/v1/tasks/6f3c9a2b1d4e5f07/artifacts/result_001.json"
```

`result_001.json` 是结构化结果（plan / candidates / targets / timings）；
有 segmentation 的目标还会产出 `result_001_mask_A.png` 等 mask 文件。

## 批量调用

```bash
curl -X POST http://127.0.0.1:8000/api/v1/batches \
  -F "prompt=框出穿红色衣服的人" \
  -F "images=@img1.jpg" \
  -F "images=@img2.jpg" \
  -F "images=@img3.jpg"
```

返回（HTTP 202）：

```json
{
  "batch_id": "a1b2c3d4e5f60718",
  "status": "queued",
  "total": 3,
  "queued": 3,
  "completed": 0,
  "failed": 0
}
```

查询进度：

```bash
curl http://127.0.0.1:8000/api/v1/batches/a1b2c3d4e5f60718
```

```json
{
  "batch_id": "a1b2c3d4e5f60718",
  "status": "completed",
  "total": 3,
  "queued": 0,
  "running": 0,
  "completed": 3,
  "failed": 0,
  "items": [
    {"image_name": "img1.jpg", "task_id": "...", "status": "success", "error": null},
    {"image_name": "img2.jpg", "task_id": "...", "status": "failed", "error": "..."},
    {"image_name": "img3.jpg", "task_id": "...", "status": "success", "error": null}
  ]
}
```

批量语义：同一 prompt 作用到多张图片；**单张失败只标记该任务为 `failed`**，
不影响批次中的其他图片。

## 运维注意

- **任务状态不持久化**：`_jobs` 与 `_batches` 只是 `JobManager` 的内存字典。
  进程重启后任务索引消失，旧 `task_id` / `batch_id` 查询返回 404。
  图片与结果文件可能仍留在磁盘，但 API 已不知道这些任务。
- **产物不自动清理**：`api/storage/` 下累积的上传与产物没有 TTL 清理逻辑
  （`demo_ui` 有 24 小时清理，`api/` 没有）。长期运行需要自行定期清理，
  或通过 `--data-dir` 把产物指到独立目录。
- **健康检查**：`GET /api/v1/health` 返回
  `{"ok": true, "service": "visual-agent-api"}`。
- **交互文档**：启动后访问 `http://127.0.0.1:8000/docs` 可交互调试每个端点。

## 非目标（V1 明确不做）

- 认证 / 鉴权（trusted / LAN 部署假设）
- 持久化 job store、分布式队列（Redis/Celery）
- Rate limiting、Artifact TTL、崩溃恢复
- 多实例协调

这些不是当前项目缺陷：它们不属于视觉 Agent 核心目标，不要为了
"生产化"在收尾阶段引入新的工程面。