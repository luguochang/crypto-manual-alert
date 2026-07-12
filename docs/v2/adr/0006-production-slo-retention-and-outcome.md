# ADR 0006：生产 SLO、保留、删除与 Outcome 门禁

> 状态：Proposed
>
> 日期：2026-07-12

## 决策

采用 `12-production-proof-slo-and-lifecycle.md` 作为首版量化基线：

- 月度 API/Agent Server availability 目标 99.9%。
- 请求确认 p95 不超过 1 秒，首个可见阶段事件 p95 不超过 3 秒。
- 普通 market analysis p95 不超过 120 秒，硬 deadline 180 秒。
- reconnect 成功率不低于 99%，重复产品事件率低于 0.01%。
- Product DB 默认保留 365 天；Checkpoint/技术 projection 在 Task 完成后默认 30 天；原始 Prompt/Response 默认不保存。
- 删除请求 30 天内完成在线系统删除，备份按 35 天轮换完成传播，并披露合法保留例外。
- 单个成熟 outcome 只证明管道；External Beta 至少 50 个可评分样本，GA 金融质量报告至少 200 个样本、覆盖 30 天和 3 个首发标的。

## 调整规则

性能基线可以修改具体数值，但必须在开始对应生产阶段前通过新 ADR 批准。不能删除指标、样本量、时间窗、失败规则或真实 hosted 证据要求。
