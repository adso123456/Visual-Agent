# Visual Agent

Visual Agent 是一个根据自然语言在图片中定位目标的最小 Demo。

第一版架构：`qwen3-vl-flash` 将图片指令拆成基础目标和语义约束，Grounding DINO Base 定位基础目标候选，Qwen3-VL 逐候选验证完整语义，OpenCV 只绘制验证通过的目标，最终生成 `images/output_images/result.jpg` 与 `images/output_images/result.json`。

当前仅支持图片，组件仅包含 Qwen3-VL、Grounding DINO 和 OpenCV。

## 运行

设置环境变量 `DASHSCOPE_API_KEY`，安装依赖后执行：

```bash
python -m venv .venv
.venv\Scripts\python -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu130
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py --image images/test_images/image.jpg --prompt "找到正在钓鱼的人"
```
