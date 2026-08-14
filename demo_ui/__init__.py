"""Visual Agent Demo UI —— 本地零依赖 Web 演示界面。

仅使用 Python 标准库（http.server），不引入 Flask/Gradio 等第三方依赖，
满足 PRD §18 最低需求：图片输入、自然语言输入、执行按钮、结果图片，
并附加 Agent plan / candidate bbox / semantic verification / final targets
调试信息面板。

完整链路（DeepSeek Planner + Qwen 验证）需要设置环境变量：

    DEEPSEEK_API_KEY
    DASHSCOPE_API_KEY

未设置时自动降级为「本地调试模式」：使用用户提供的预编译计划
（plan JSON），仅运行 Detector → SAM2 → Action 本地栈，不做语义验证。
"""
