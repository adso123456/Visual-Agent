# Visual Agent

Visual Agent 是一个根据自然语言在图片中定位、分割并处理目标的最小 Demo。

当前架构：`deepseek-v4-pro` 通过受控 Tool Call 将指令拆成基础目标、语义约束和操作，Grounding DINO Base 定位候选，`qwen3-vl-flash` 群组验证完整视觉语义，SAM 2.1 Base Plus 根据验证通过的 bbox 生成像素级 mask，OpenCV 确定性执行操作，最后由 DeepSeek 汇总结构化结果。关系组合目标 v1 仅支持一个主体与最多一个 `held_by_target` 手持物体，组件 mask 使用 OR 合并，组合分数取组件最低 SAM score（不是重新预测的 composite IoU）。

当前仅支持图片，操作白名单为：目标标红 `highlight`、目标描边 `outline`、模糊目标 `blur_target`、背景变暗 `dim_background`、透明背景抠图 `cutout`。输出按编号保存；抠图为透明 PNG，其余操作为 JPG，同时保留 JSON 和 binary mask PNG。

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
