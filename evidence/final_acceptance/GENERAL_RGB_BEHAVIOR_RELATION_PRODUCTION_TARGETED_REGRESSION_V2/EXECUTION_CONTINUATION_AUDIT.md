# V2 执行连续性审计

- 首次进程已写入 slot 1–14 的唯一 terminal success 记录；在 slot 15 开始后，执行进程因外部会话中断而消失。
- 中断时 slot 15 没有 terminal 记录，只留下空 artifact 目录；不存在可被替换的成功或失败结果。
- 用户随后明确授权“继续跑”。
- 第一次续跑启动在导入 Pipeline 前因当前默认 Python 缺少 NumPy 而退出；pipeline、VLM、DINO、SAM 调用均为 0，raw execution 未变化。
- 复用项目原有 `.venv` 中已安装的依赖包，并以 ABI 兼容的系统 Python 3.12 启动；没有安装、升级或修改依赖。
- Runner 机械跳过 slot 1–14。空的 slot 15 artifact 残留被完整移动到独立的 `interrupted_artifacts` 目录后，slot 15 首次完成 terminal 执行。
- 最终 raw execution 包含 34 个唯一 slot ID、34 条 terminal success、0 条 terminal error；不存在 terminal slot 覆盖或失败结果替换。
- 执行期间没有修改 Production、prompt、routing、模型参数、selection、schedule 或 Gate。

`failed_execution_replacement = false` 保持成立。
