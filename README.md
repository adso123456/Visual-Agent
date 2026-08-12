# Visual Agent

Visual Agent 是一个根据自然语言在图片中定位并分割目标的最小 Demo。

当前架构：`qwen3-vl-flash` 将指令拆成基础目标和语义约束，Grounding DINO Base 定位候选，Qwen3-VL 群组验证完整语义，SAM 2.1 Base Plus 根据验证通过的 bbox 生成像素级 mask，OpenCV 绘制 mask、轮廓、bbox 和标签。

当前仅支持图片，输出按编号保存为 `result_NNN.jpg`、`result_NNN.json` 和 `result_NNN_mask_ID.png`。

## 运行

设置环境变量 `DASHSCOPE_API_KEY`，安装依赖后执行：

```bash
python -m venv .venv
.venv\Scripts\python -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu130
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py --image images/test_images/image.jpg --prompt "找到正在钓鱼的人"
```
