# 联合流量容差核定

白班按确切冻结修订和合法原预算签发 V2 校准件。夜班关站后收到单件原文和一组具名流量容差，签出满足整组容差至少需要的总残差平方和及其原预算资格。现有变比业务及其历史成果沿用 README.md 的接口。

## 核定口径

沿用 V1 归一化、设计列满秩条件及预算签件规则。若冻结修订的实测向量为 y、设计矩阵为 X，校准参数 β 的总残差平方和为 ‖Xβ−y‖²。每个公开通道按该修订的归一化接线，从同一个 β 得到读值。原预算单位为 `(mL/s)²`，申请端点单位为 `mL/s`。

V2 件须自足地保全公开读值的完整联合可达关系，以及每个可达公开读值组合的精确最低总残差平方和，包括零余量时高于原预算的费用。正文移交公开通道、公开读值与费用证据、原预算和出处。原测、设计行和私有参数名留站。数学载荷的表示由实现选择。

核定在该修订的全部实参数上求满足整组闭区间的最低总残差平方和。区间两端均计入，允许单点，未列出的通道自由取值。恒定或线性依赖的通道继续服从原接线关系。先核定最低费用，再和原预算精确比较。合法申请若在任何预算下都不可满足，仍签发报告，最低值为 `None`、预算资格为 `False`。有解时返回精确 `Fraction`，恰等原预算也签 `True`。

## 调用与交换

- 沿用 `BenchLedger.initialize()`、`IssueRegister.initialize()` 和 `reports.publish.initialize_archive(connection)` 初始化。以 `ledger.load_revision(revision_id)` 取指定修订，并用原 `fit_frozen_revision(revision, limit)` 拟合。新增 `evidence.issue.issue_tolerance_calibration(fitted, register)`，使用冻结接线签发 V2。返回对象具有 `artifact_id`、`revision_id` 和 `revision_fingerprint` 属性。以 `register.get(artifact_id)` 领取登记原文。有效更正产生新修订，按原件号仍领同一正文。未知件号沿用 `KeyError`。
- 交换正文为 JSON 对象，带整数 `version` 值 `2` 和顶层 `artifact_id`、`revision_id`、`revision_fingerprint`。出处字段沿用 V1 类型。核定拒绝混入 V1 件、重复 JSON 字段以及缺失、非精确或与 V2 数学表示不自洽的证据。旧件字节及变比入口保留原口径。
- 新增 `review.assess.assess_tolerance_and_publish(connection, artifact_text, intervals)`。归档连接独立于源库，`artifact_text` 为 `register.get()` 返回的字符串。`intervals` 是非空列表或元组，每项是 `[name, lower, upper]` 或其元组形式。端点沿用 V1 精确有理输入，支持非布尔整数、有理字符串和 `Fraction`。重复或未知通道、反向区间、非法端点、非法申请结构及坏件均报 `ValueError`，且无本次成果。
- 签发返回 `(report, receipt)`。报告属性为 `report_id`、`artifact_id`、`revision_id`、`revision_fingerprint`、`limit`、`intervals`、`minimum_residual_sum`、`within_budget`。`limit` 为原预算的 `Fraction`。`intervals` 是按通道名升序排列的三元组序列，端点均为 `Fraction`。回执沿用 `reports.receipts.Receipt` 及其 `report_id`、`receipt_id` 属性。报告号为正整数。
- 新增 `reports.retrieve.retrieve_tolerance_report(connection, report_id)`，返回已提交的原报告和对应回执，未知号报 `reports.retrieve.ReportNotFound`。领取只访问归档。报告和回执由同一次 SQLite 事务提交，失败无部分成果且可重试。SQLite 写入错误按 V1 方式传播。勘误、重新初始化和重开归档后，按号领取固定结果与出处。

## 样例与运行

`samples/tolerance.json` 的每项是一份独立样例。用 `ledger.accept_batch(**case['batch'])` 入账，冻结后按 `limit` 拟合并签件。关闭源库，将正文与 `requests` 中的 `intervals` 交给离线核定入口。样例中的精确最低值写成有理字符串或 `null`，分别对应 Python 的 `Fraction` 或 `None`。

`zero-soft` 与 `zero-stiff` 同样按零预算出件，收到 `[["A", "1", "2"]]` 后分别签出 1 和 4，均超预算。`dependent` 的关系为 C=A+B，D 恒为 5。一致的三通道单点申请以恰等预算的 2 通过，矛盾申请签空最低值。只限制 C=3 时最低值为 9/2。`residual-floor` 首次签 4，按样例的 `correction` 更正后用新修订和同一预算给同一申请另签，最低值为 0。重开归档后仍能按最初报告号领取 4 和原回执。

保留 `python3 -B check_project.py` 的原回归和 `python3 -B demo.py workday` 的原演示。沿用 `.pointwise-runtime.json` 的版本和启动约定，令 `verify` 实际检查原回归及联合容差业务，失败返回非零。`demo` 展示关站后签发及勘误和重开后领取，输出实际费用、预算资格和报告出处。可参照 `tests/test_archive.py` 的 SQLite 失败注入方式核对新区间报告和回执的共同提交。
