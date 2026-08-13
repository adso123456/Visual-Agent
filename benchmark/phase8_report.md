# Phase 8 Qwen 结构化输出协议可靠性报告

- Core：15/15
- Candidate 专项：{'total_calls': 10, 'first_attempt_success': 10, 'contract_retries': 0, 'recovered_retries': 0, 'unrecovered_structured_failures': 0}
- Relation 专项：{'total_calls': 5, 'first_attempt_success': 5, 'contract_retries': 0, 'recovered_retries': 0, 'unrecovered_structured_failures': 0}
- structured_output_runtime_failure_count：0
- challenge_004：PASS，首次响应通过，2 个目标，完整链路正常完成。
- challenge_005：FAIL，仍为密集小目标 Grounding Recall 问题。

## 契约结论

- 最大 2 次尝试；只对空响应、非法 JSON、严格契约校验失败重试。
- correction 只包含格式错误、原结构提示及禁止改变语义的约束。
- 合法 uncertain/not_satisfied 不重试；Python 不做 dict 到 list 的宽容转换。
- 两次失败后抛出带错误分类的 RuntimeError；API/网络异常不由本机制重试。
- DINO、SAM2、Action、Renderer、Qwen 视觉判断语义、Relation 判断语义均未修改。
