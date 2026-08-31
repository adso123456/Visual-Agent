# Joint targeted-confirmation runner

该目录只实现冻结的 `GENERAL_RGB_BEHAVIOR_RELATION_JOINT_TARGETED_CONFIRMATION_V1` benchmark runner。

- Execution base：`be54f3c89171d8b16f53c82397e9f468fb4b4c97`
- Frozen evidence head：`30fa9cddd851f376831b2bd3d940f6ab1165c084`
- Frozen schedule：35 个 Behavior candidate observations + 13 个 Relation policy executions，严格串行。
- Behavior：读取并复核冻结 R3 evidence bytes，执行确定性 identity/uncertain/long-range routing。
- Relation：先走 `run_pipeline(..., plan=..., final_response=False)` 正式路径；仅在 existing secondary stage 后仍无 satisfied 时执行一次 hand-conditioned fallback；新增候选进入全局唯一 candidate universe，对全部 relation-eligible subjects 建立 binding matrix，再原样复用 Production focused ownership 与 relation outcome resolver。
- Result：一个 slot 只允许一个 terminal record；成功与失败都不补跑覆盖。

当前合同中的 `model_execution_authorized=false` 保持不变。正式执行必须另有代码审查后的 authorization JSON；运行时 Git `HEAD` 必须与其中的 `runner_review_sha` 完全相等。缺失、字段不匹配或 descendant commit 均会在创建模型 client、Detector 或 SAM 前失败。

本实现提交只运行 stub/mock 单测，不产生模型、Detector 或 SAM 调用结果。
