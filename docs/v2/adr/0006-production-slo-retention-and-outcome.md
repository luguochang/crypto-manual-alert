# ADR 0006：生产 SLO、保留、删除与 Outcome 门禁

> authority_class: approved_normative
>
> 状态：Accepted
>
> 日期：2026-07-12
>
> 批准：用户，2026-07-13

## 决策

采用 `12-production-proof-slo-and-lifecycle.md` 作为量化基线。由于 ADR 0007 在法律/产品风险评审前禁止 External Beta/GA，V2 Final 本次唯一发布层级是 `internal_alpha`，必须完整验证该列，不允许从不同层级拼接指标：

- API/Agent Server 月度 availability 先测量不承诺，但必须产生真实 hosted 时间窗和查询证据。
- 请求确认 p95 <= 1 秒，首个可见阶段事件 p95 <= 3 秒。
- market analysis p95 <= 150 秒，硬 deadline 180 秒。
- reconnect 成功率 >= 98%，重复产品事件率 < 0.1%。
- Structured Output 成功率 >= 97%，allowed 结果 Evidence 引用完整率 100%，checkpoint/recovery 成功率 >= 95%，跨租户/密钥泄漏为 0。
- Product DB 默认保留 365 天；Checkpoint/技术 projection 在 Task 完成后默认 30 天；原始 Prompt/Response 默认不保存。
- 删除请求 30 天内完成在线系统删除，备份按 35 天轮换完成传播，并披露合法保留例外。
- 单个成熟 outcome 只证明管道；External Beta 至少 50 个可评分样本，GA 金融质量报告至少 200 个样本、覆盖 30 天和 3 个首发标的。

## 调整规则

性能基线可以修改具体数值，但必须在开始对应生产阶段前通过新 ADR 批准。不能删除指标、样本量、时间窗、失败规则或真实 hosted 证据要求。
