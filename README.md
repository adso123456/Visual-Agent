# Visual Agent

Visual Agent 是一个根据自然语言在图片中定位、分割并处理目标的最小 Demo。

当前架构：`deepseek-v4-pro` 通过受控 Tool Call 将指令拆成基础目标、语义约束和操作，Grounding DINO Base 定位候选，`qwen3-vl-flash` 群组验证完整视觉语义，SAM 2.1 Base Plus 根据验证通过的 bbox 生成像素级 mask，OpenCV 确定性执行操作，最后由 DeepSeek 汇总结构化结果。关系组合目标 v1 仅支持一个主体与最多一个 `held_by_target` 手持物体，组件 mask 使用 OR 合并，组合分数取组件最低 SAM score（不是重新预测的 composite IoU）。

当前仅支持图片，操作白名单为：目标标红 `highlight`、目标描边 `outline`、模糊目标 `blur_target`、背景变暗 `dim_background`、透明背景抠图 `cutout`。输出按编号保存；抠图为透明 PNG，其余操作为 JPG，同时保留 JSON 和 binary mask PNG。

Qwen结构化输出使用严格Python契约校验；仅空响应、非法JSON或schema错误允许一次format-only retry，不对合法视觉判断结果重试或宽容转换。

## 运行

设置环境变量 `DEEPSEEK_API_KEY` 和 `DASHSCOPE_API_KEY`，安装依赖后执行：

```bash
python -m venv .venv
.venv\Scripts\python -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu130
.venv\Scripts\python -m pip install -r requirements.txt
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
## Demo UI（PRD §18）

本地零依赖 Web 演示界面（仅标准库，无需 Flask/Gradio）：

```bash
.venv\Scripts\python -m demo_ui.server --host 127.0.0.1 --port 8080
# 打开 http://127.0.0.1:8080
```

- 完整链路：设置 `DEEPSEEK_API_KEY` + `DASHSCOPE_API_KEY`，输入自然语言执行。
- 本地调试：粘贴预编译 plan JSON（或使用示例计划），仅运行 DINO → SAM2 → Action，无需 API Key。
- 界面包含结果图片与 Agent plan / candidate bbox / semantic verification / final targets 调试面板。

## Instance Quality Benchmark v1（PRD §22）

24 张 Test + 5 张 Calibration，八类场景，GT 已冻结。
122 个 raw candidate 的六分类视觉复核草稿与官方基线已生成：

```bash
.venv\Scripts\python benchmark\instance_quality_v1\scripts\evaluate.py
# 基线报告：benchmark/instance_quality_v1/reports/grounding_dino_base_v1.json / .md
```

基线指标（draft，待人工确认 candidate review）：Instance Recall 0.733、
Instance Purity 0.685、Mixed-box Rate 0.098、Duplicate Rate 0.043。

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
