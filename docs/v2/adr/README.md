# V2 Architecture Decision Records

> 状态：ADR 0001-0007 Accepted；ADR 0008 保留生产证据门禁

ADR 在用户批准前均不得视为实现授权。

| ADR | 主题 | 状态 |
| --- | --- | --- |
| [0001](./0001-agent-runtime-deployment.md) | Agent Runtime、部署和持久化拓扑 | Accepted |
| [0002](./0002-web-search-provider.md) | Web Search Provider 与降级策略 | Accepted |
| [0003](./0003-identity-and-auth-bootstrap.md) | 默认开发身份与正式鉴权 | Accepted |
| [0004](./0004-frontend-presentation-stack.md) | 前端 Runtime 与视觉组件 | Accepted |
| [0005](./0005-observability-and-prompt-source.md) | LangSmith/Langfuse 与 Prompt 发布源 | Accepted |
| [0006](./0006-production-slo-retention-and-outcome.md) | 生产 SLO、保留、删除与 Outcome 门禁 | Accepted |
| [0007](./0007-launch-and-financial-product-boundary.md) | 上线范围与金融产品边界 | Accepted |
| [0008](./0008-production-deployment-profile.md) | 生产部署 Profile 与退出方案 | Provisionally Accepted，证据门禁 |

状态只能按以下顺序变化：

```text
Proposed -> Accepted -> Superseded/Deprecated
```

每个 Accepted ADR 必须记录批准日期和批准人；修改已接受决策必须新增 ADR，不直接改写历史结论。
