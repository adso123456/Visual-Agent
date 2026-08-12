# Visual Agent

Visual Agent 是一个根据自然语言在图片中定位目标的最小 Demo。

第一版架构：图片与指令由 `qwen3-vl-flash` 理解并转换为目标描述，Grounding DINO 根据描述输出 bbox，OpenCV 在原图上画框和添加说明，最终生成 `outputs/result.jpg` 与 `outputs/result.json`。

当前仅支持图片，组件仅包含 Qwen3-VL、Grounding DINO 和 OpenCV。

## 运行

设置环境变量 `DASHSCOPE_API_KEY`，安装依赖后执行：

```bash
python -m venv .venv
.venv\Scripts\python -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu130
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py --image path/to/image.jpg --prompt "找到正在钓鱼的人"
```
