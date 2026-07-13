# ADR 0008：生产部署 Profile 与退出方案

> 状态：Provisionally Accepted，生产发布仍需证据门禁
>
> 日期：2026-07-12

## 推荐目标

初始 hosted production proof 优先使用官方 LangSmith Deployment Cloud，以最小化自建 Thread/Run/Protocol/worker 基础设施。若以下任何证据不满足，则保持 Internal Alpha，提交替代 ADR 评审自管 Agent Server；不能静默改成自建 FastAPI Runtime。

## Accepted 前必须填写

| 项目 | 必须证据 |
| --- | --- |
| 许可/套餐 | Agent Server、custom routes、Auth、Cron、Webhook、容量和保留能力的书面/控制台证据 |
| 区域/数据驻留 | 实际 region、数据类别、跨境与备份位置 |
| 网络 | 对模型 base URL、Tavily、交易所、Langfuse/Bark 的真实出站探测 |
| Auth | BFF 身份、Agent Server authenticate/resource auth、custom route 显式 AuthZ |
| Persistence | Checkpoint/Store 与 Product DB 的数据库、权限、备份和恢复边界 |
| 版本组 | Agent Server image、Python/JS SDK、React 和 protocol package 的 contract test |
| HA/SLO | capacity、滚动升级、RTO/RPO、监控和错误预算 |
| 成本 | 月度固定/变量成本、预算和超限策略 |
| 退出 | 导出 Thread/Checkpoint/Store/业务数据并切换部署而不改前端/DTO 的演练 |

## 决策规则

- 先完成上表部署 Profile preflight 证据；全部通过后状态改为 Accepted，才允许执行 Phase 6 hosted runtime proof。
- ADR 状态 Accepted 只证明选定的部署 Profile 可进入真实验证，不等于 hosted release gate 已通过；后者仍必须完成真实部署、Playwright、恢复和回滚证据。
- 任何 P0 不通过：不得进入公开生产；新增自管/混合部署 ADR。
- 只有架构偏好、没有实际账户/网络/恢复证据时，不能把本 ADR 标记 Accepted。
