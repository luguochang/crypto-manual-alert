# ADR 0002：Web Search Provider 与降级策略

> 状态：Proposed
>
> 日期：2026-07-12

## 背景

用户要求交易分析必须包含真实 Web Search 和可验证来源。当前 OpenAI-compatible 端点未证明支持 Responses built-in web search，不能仅因接口兼容就假设该能力存在。

## 决策

- 启动时运行 provider capability probe，验证 Responses built-in `web_search`、Tool Calling、Structured Output、streaming 和 usage。
- built-in web search 通过真实探测时可作为首选，使用 LangChain Provider Tool 接口。
- 不支持时显式切换到 LangChain Tavily 官方集成；生产 readiness 必须要求 Tavily Key 和连通性。
- 开发/CI 可使用确定性 fixture tool，但 UI、Trace 和测试必须明确标记 fixture，不能当作真实搜索证明。
- 搜索结果必须保存 query、URL、标题、发布时间、抓取时间、摘要、引用和来源质量。
- 搜索不可用时 Run 显示 `research_unavailable` 或明确降级，不生成伪来源，不用模型常识冒充搜索结果。

## 不采用

- 自写通用 Search Runtime/Provider Registry。
- 无来源的模型内置知识作为实时 Web Search。
- 自动在多个 Provider 间静默 fallback。

## 评审点

- 若评审希望固定单一生产 Provider，可将 Tavily 改为强制主 Provider；其余证据和失败规则不变。
