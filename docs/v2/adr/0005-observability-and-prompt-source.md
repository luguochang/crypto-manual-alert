# ADR 0005：LangSmith/Langfuse 与 Prompt 发布源

> 状态：Accepted
>
> 日期：2026-07-12
>
> 批准：用户，2026-07-13

## 背景

项目要求同时接入 LangSmith 和 Langfuse，但双平台容易造成重复 generation、双重手工埋点、敏感数据泄漏和观测故障阻断主链。Prompt 也不能由两个平台同时发布。

## 决策

- LangSmith 使用 LangChain/LangGraph 原生自动 Trace，承担 Graph/Agent 调试、Dataset、Experiment、Evaluator 和 Release Gate。
- Langfuse 使用一个集中创建的官方 LangChain CallbackHandler，承担生产 session/user/cost/latency/error 视图。
- Callback 只在 observability bootstrap 装配一次；业务 Node/Tool 不手工创建重复 generation。
- `tenant_id`、匿名 `user_id`、`thread_id`、`task_id`、`run_id`、environment 和 version metadata 在根调用传播到所有 child runs。
- masking 在出口前执行；敏感租户可关闭 I/O 或整条 Trace；观测发送异步、失败不影响业务结果。
- 首版 Prompt 发布源选择代码仓库中的版本化 Prompt 文件和 Git commit；LangSmith 用于实验与候选评测，不在运行时远程拉取 Prompt。
- 若后续改为 LangSmith Prompt Hub 作为发布源，必须新增 ADR、缓存/降级策略和回滚证明。Langfuse 不作为 Prompt 发布源。

## 采样

- LangSmith 对 release proof、failed、blocked、negative feedback 全量保留。
- Langfuse 初期全量采集并设置 retention；流量和成本达到阈值后再通过配置启用统计采样。
- 即使 Langfuse 采样，Product Audit 和 LangSmith 的强制证据不能丢失。

## 不采用

- 同一次模型调用同时使用 Callback 和手工 generation。
- 在每个 Tool/Node 中分别调用两个观测 SDK。
- 观测平台反写最终 RiskVerdict、Outcome 或产品状态。
