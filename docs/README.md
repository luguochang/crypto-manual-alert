# 文档入口

开发前请优先阅读：

- `formal/00-文档索引.md`
- `formal/01-v1需求边界.md`
- `formal/02-v1架构设计.md`
- `formal/10-实施计划.md`
- `implementation/2026-07-09-current-delivery-checklist.md`
- `implementation/2026-07-09-main-flow-production-recovery-checklist.md`
- `implementation/2026-07-09-main-flow-module-ownership.md`

`docs/formal/` 是当前正式文档集。

日常交付以 current delivery checklist 和 main-flow production recovery checklist 为准：先证明人工提醒主流程、生产配置、真实 `prod-actionable`、hosted visual gate 和 real outcome；不要把 fixture/mock/staging/hosted-runtime 绿色结果写成生产成功。

后端改动先对照 main-flow module ownership：只有人工提醒主链模块可以推进生产 MVP，AgentSwarm、candidate、eval、raw observability 和 replay 仍按 sidecar/audit/diagnostic 处理。

根目录下其他早期设计文档仅作为历史参考，后续开发不直接以它们为准。
