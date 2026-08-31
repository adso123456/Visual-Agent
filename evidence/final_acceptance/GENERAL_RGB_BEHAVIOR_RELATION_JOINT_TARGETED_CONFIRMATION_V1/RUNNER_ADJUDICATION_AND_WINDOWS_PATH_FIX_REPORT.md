# Joint Targeted Confirmation Runner 修正报告

状态：`IMPLEMENTED / REVIEW REQUIRED / MODEL EXECUTION NOT AUTHORIZED`

## 代码绑定

- Branch：`general-rgb-behavior-relation-joint-confirmation-v1`
- Previous reviewed runner：`0aa9e45766dcaa846b4f22b1eea6d66ebe27e546`
- 修正提交：`a1c61c3b4d38c25bafd841fc3b8c52fecbdbb897`
- 修改文件：
  - `benchmark/joint_targeted_confirmation_v1/runner.py`
  - `benchmark/test_joint_targeted_confirmation_runner.py`
- Production 文件修改：0
- 模型调用：0

## 修正内容

1. Relation artifact 目录通过确定性的 Windows-safe slug 生成，替换 `<>:"/\\|?*` 与控制字符；`RELATION|F4::fishing_017.jpeg|r1` 固定映射为 `RELATION_F4__fishing_017.jpeg_r1`。
2. Behavior candidate-level baseline 固定为执行前 synthesis 的 15 个状态。
3. `new_false_assignment` 只统计相对 baseline 新出现的错误 satisfied；已有 FP 不再误计为 new。
4. `fallback_harm` 只统计 baseline 原本合法/正确、执行 fallback 后变为非法/错误的回归；unchanged incorrect/uncertain 不再误计为 harm。
5. 新增 `F1_candidate_regression=max(0,5-current)` 与 `F1_task_regression=max(0,3-current)`，并纳入 Gate。
6. `F2::fishing_024` 与 `core_003` existing-positive 独立要求唯一成功 observation 且 retained；缺失或失败不再因空集合 `all()` 得到 true。
7. Behavior/Relation component Gate 分别要求完整的 35/13 successful observations，避免不完整执行被局部指标掩盖。

## 验证

```text
python -m pytest -q benchmark/test_joint_targeted_confirmation_runner.py
22 passed in 16.74s
```

首次执行命令 `pytest -q ...` 在 test collection 前因仓库根不在模块路径而失败，0 tests；随后使用项目入口 `python -m pytest` 成功。没有因此修改代码或环境。

对首次批次 35 条 Behavior raw records 进行纯内存 corrected adjudication，结果为：

```text
F1 candidate correct = 5/10
F1 task correct = 3/6
F1 candidate regression = 0
F1 task regression = 0
new false assignment = 0
fallback harm = 0
Behavior Gate = true

F2::fishing_024 retained = false  # 原 terminal failure，不再空集合误判 true
Relation Gate = false / inconclusive execution failure
Joint = false
```

该纯内存重算没有修改或覆盖 `469914a...` 的 raw records / summary，不构成新执行批次。

## 授权边界

```text
RUNNER REVIEW = PENDING
MODEL EXECUTION = NOT AUTHORIZED
PRODUCTION MODIFICATION / MERGE = NOT AUTHORIZED
```

后续若审查通过，必须用新的 authorization 绑定 `a1c61c3...`；旧 authorization 只能授权旧 runner `0aa9e457...`，不得复用。
