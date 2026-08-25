# Visual Agent

Visual Agent 是一个自然语言驱动的通用视觉执行 Demo。开发者上传图片并输入自然语言，系统通过通用 Detector、VLM、Relation、SAM 和确定性 Action 组合用户视觉意图，定位、分割并处理目标。

项目的核心目标是减少“每出现一个新视觉业务需求，就重新收集数据、标注并训练专项 Detector”的需要。它是 best-effort open-world perception Demo，不宣称完全替代专项训练，也不保证所有场景零样本完美识别。

**Visual Agent v1 已正式关闭并验收，产品范围冻结为 General RGB static-image visual execution。** 水污染 RGB 图片识别已移出产品范围；历史 P1～P4 仅作为研究证据保留，不再作为后续优化 Gate。完整冻结口径见 [`docs/PROJECT_CLOSURE_V1.md`](docs/PROJECT_CLOSURE_V1.md)。

当前架构：`deepseek-v4-pro` 通过受控 Tool Call 将指令拆成基础目标、语义约束和操作，Grounding DINO Base 定位候选，可配置的 OpenAI-compatible VLM（默认 `qwen3-vl-flash`，也可切换已验证的 Local VLM）验证完整视觉语义，SAM 2.1 Base Plus 根据验证通过的 bbox 生成像素级 mask，OpenCV 确定性执行操作，最后由 DeepSeek 汇总结构化结果。关系组合目标 v1 仅支持一个主体与最多一个 `held_by_target` 手持物体，组件 mask 使用 OR 合并，组合分数取组件最低 SAM score（不是重新预测的 composite IoU）。

当前仅支持图片，操作白名单为：目标标红 `highlight`、目标描边 `outline`、模糊目标 `blur_target`、背景变暗 `dim_background`、透明背景抠图 `cutout`。输出按编号保存；抠图为透明 PNG，其余操作为 JPG，同时保留 JSON 和 binary mask PNG。

Qwen结构化输出使用严格Python契约校验；仅空响应、非法JSON或schema错误允许一次format-only retry，不对合法视觉判断结果重试或宽容转换。

## Production API（Batch V1）

`api/` 是独立的生产接口层，不依赖 Demo UI。单图和批量任务都会进入
后台 worker queue，调用同一个 `visual_agent.pipeline.run_pipeline()`；
V1 默认 `MAX_CONCURRENT_JOBS=1`，先保证接口、状态、失败隔离和产物正确。

```powershell
$env:DEEPSEEK_API_KEY = "你的 DeepSeek API Key"
$env:DASHSCOPE_API_KEY = "你的 DashScope API Key"
$env:MAX_CONCURRENT_JOBS = "1"
python -m api.server --host 0.0.0.0 --port 8000
```

端点：

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/tasks` | 单图任务，multipart：`image` + `prompt`，立即返回 `task_id` |
| `GET` | `/api/v1/tasks/{task_id}` | 查询任务状态、结果摘要与产物地址 |
| `GET` | `/api/v1/tasks/{task_id}/artifacts/{name}` | 下载结果图片 / JSON / mask |
| `POST` | `/api/v1/batches` | 批量任务，multipart：`prompt` + `images[]`，立即返回 `batch_id` |
| `GET` | `/api/v1/batches/{batch_id}` | 查询 `total / completed / failed` 与逐图状态 |

Batch 异步执行，单张图片失败只标记该任务为 `failed`，不影响批次中的其他图片。
V1 上传边界：单图最大 64 MiB，单次 batch 最多 32 张；图片按张有界读取，
不会先把整批图片同时读入内存。

## Developer Demo

### 1. 配置环境

设置环境变量 `DEEPSEEK_API_KEY` 和 `DASHSCOPE_API_KEY`，安装依赖后执行：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu130
.venv\Scripts\python -m pip install -r requirements.txt
$env:DEEPSEEK_API_KEY = "你的 DeepSeek API Key"
$env:DASHSCOPE_API_KEY = "你的 DashScope API Key"
```

### 2. 启动页面

```powershell
.venv\Scripts\python.exe -m demo_ui.server --host 127.0.0.1 --port 8080
```

浏览器打开 `http://127.0.0.1:8080`，选择 Full Chain，上传图片、输入 Prompt、点击 Run，等待 `Queued → Running → Completed`，即可查看 Original / Result、Agent Plan、Detector Candidates、Semantic Verification、Relation、Final Targets 和 Timing。

Full Chain 必须同时配置 `DEEPSEEK_API_KEY` 和 VLM 凭据。默认 Cloud 配置可继续使用 `DASHSCOPE_API_KEY`；切换自定义 OpenAI-compatible endpoint 时必须显式配置：

```powershell
$env:VLM_MODEL = "你的模型名"
$env:VLM_BASE_URL = "http://你的服务地址/v1"
$env:VLM_API_KEY = "显式凭据或本地服务占位值"
$env:VLM_TIMEOUT = "120"  # 可选
```

自定义 `VLM_BASE_URL` 不会回退使用 `DASHSCOPE_API_KEY`，避免把云端凭据发送给自定义 endpoint。缺少凭据时页面会显示真实错误，不会自动降级并冒充完整链路。

三个示例：

- `只给穿红色衣服的人描边`
- `把拿雨伞的人单独抠出来`
- `把正在钓鱼的人高亮`

Local Debug 使用预编译 Plan，只运行 Detector → SAM2 → Action；Agent 与 Qwen Semantic Verification 均为 `SKIPPED`，仅供开发者调试，不代表完整自然语言能力。

### 3. 当前能力边界

推荐使用基本清晰、正常大小的主体，适用于清晰单人属性、普通多人属性、明显行为、多目标、简单 `held_by_target`、普通遮挡和 Negative / 0-target 任务。

明确不承诺：密集人群 exhaustive recall、极小远距离目标、严重运动模糊、极端遮挡，以及图中所有实例一个不漏。详细状态见 [`docs/DEMO_STATUS.md`](docs/DEMO_STATUS.md)。

水面垃圾、漂浮塑料瓶、漂浮物和污染区域等 P1～P4 水污染 RGB 任务属于历史研究资产，不属于 v1 产品承诺。Sentinel-2 / Landsat `.tif` 的水质九参数反演是未来独立项目，不进入当前 Pipeline。

### CLI

```powershell
.venv\Scripts\python main.py --image images/test_images/image.jpg --prompt "找到正在钓鱼的人"
.venv\Scripts\python main.py --image images/test_images/image.jpg --prompt "把正在钓鱼的人以外的背景变暗"
.venv\Scripts\python main.py --image images/test_images/image.jpg --prompt "把正在钓鱼的人单独抠出来"
```

## 延迟测量

模型（DINO + SAM2）默认在进程内只加载一次（`visual_agent/models.py` 常驻注册表），后续调用直接复用。
本地栈（Detector→SAM2→Action，不含 LLM API）冷启动约 20s，热复用约 0.7s/图（RTX 4060）：

```bash
.venv\Scripts\python benchmark\measure_latency.py \
    --image images/test_images/benchmark_fishing_clear.png --image images/test_images/commons_umbrella.jpg \
    --plan-map benchmark/latency_plan_map.json --no-verify --no-final-response --runs 2 \
    --json benchmark/latency_report.json
```

全链路（含 DeepSeek/Qwen API）需设置 `DEEPSEEK_API_KEY` 与 `DASHSCOPE_API_KEY` 后，去掉 `--plan-map` 并传 `--prompt`。
`main.py --profile` 可输出单次运行各阶段耗时。
## Instance Quality Benchmark v1（Research / Diagnostic Artifact）

24 张 Test + 5 张 Calibration，八类场景，GT 已冻结。
122 个 raw candidate 的六分类视觉复核草稿与官方基线已生成：

```bash
.venv\Scripts\python benchmark\instance_quality_v1\scripts\evaluate.py
# 基线报告：benchmark/instance_quality_v1/reports/grounding_dino_base_v1_1.json / .md
```

Grounding DINO Base Baseline v1.1 历史结果：Instance Recall 0.821138、
Instance Purity 0.827869、Mixed-box Rate 0.098361、Duplicate Rate 0.040984；
预声明语义约束 Downstream Usability 0.914894。

该 Benchmark 是历史 Detector instance-quality 研究与诊断资产；已知 GT completeness 仍有待修订的问题，当前不作为 Developer Demo readiness gate，也不在本阶段继续修复。当前 Demo readiness 以正常清晰场景的端到端 Acceptance 结果为准。

详见 `benchmark/instance_quality_v1/README.md` 与 `VISUAL_AGENT_PERCEPTION_CONTRACT_V1.0.md`。
## Demo Showcase（PRD §7）

一条命令用本地栈跑通五种确定性操作的示例：

```bash
.venv\Scripts\python demo_showcase.py
# 输出到 demo_showcase_output/：outline / cutout / highlight / blur / dim + manifest.json
```

注意：本地栈模式 verify=False，不做 Qwen 语义验证（关系/约束任务只展示
定位与分割链路）；完整语义链路请使用 main.py 或 Demo UI 并设置 API Key。

## PRD §29 验收对照

逐条证据见 `docs/PRD_ACCEPTANCE_EVIDENCE.md`。
