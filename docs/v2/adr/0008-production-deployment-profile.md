# ADR 0008：生产部署 Profile 与退出方案

> authority_class: superseded
>
> superseded_by: docs/v2/adr/0011-aegra-self-hosted-agent-server.md
>
> 状态：Superseded by ADR 0011（2026-07-21）
>
> 日期：2026-07-12

> 本文保留为 hosted 商业部署评估历史。用户已明确拒绝商业授权，当前生产候选改为
> [ADR 0011](./0011-aegra-self-hosted-agent-server.md) 的 Aegra 自托管开源 Profile；
> 本文的生产证据项目仍作为部署审计输入，但不再要求购买 LangSmith Deployment。

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

- 先完成上表部署 Profile preflight 与退出证据；这只允许创建 Task 14 Step 7 的 acceptance candidate。Hosted RED 仍被禁止，直到该候选依次通过 Task 0 specification/authority、plan-executability、official-framework 三路串行复审，新 `normative-baseline.json` 将本 ADR 从 `proposed_gate` 提升为 `approved_normative`，原稳定 gate ID 在 registry 中完成无重建转换、受影响映射重新验证，并提交 transition attestation。
- ADR 状态 Accepted 只证明选定的部署 Profile 可进入真实验证，不等于 hosted release gate 已通过；后者仍必须完成真实部署、Playwright、恢复和回滚证据。
- 任何 P0 不通过：不得进入公开生产；新增自管/混合部署 ADR。
- 只有架构偏好、没有实际账户/网络/恢复证据时，不能把本 ADR 标记 Accepted。
