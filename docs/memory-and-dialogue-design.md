# 记忆与多轮对话设计

## 目标

支持多轮对话和重复的 crypto 决策运行，同时避免旧的市场结论污染后续判断。

## 核心原则

系统不能把过去的交易结论当成当前市场事实。

只有当前 episode 的内容可以影响当前决策。实时市场事实必须每轮重新刷新。

## 记忆分层

### 1. 会话记忆

用途：

- 记录当前用户意图
- 记录当前 symbol 和 horizon
- 记录当前持仓状态
- 记录当前 episode 的短摘要

允许内容：

- “用户在问 ETH”
- “当前周期是 6h”
- “用户当前持有 ETH 多单”

不允许内容：

- 旧价格
- 旧 funding
- 旧 OI
- 旧的方向性结论当成事实

### 2. 事件记忆

用途：

- 只保留未解决的 active events
- 记录事件状态和最后一次观察到的反应

允许内容：

- FOMC 活动窗口
- 未更新完的 ETF 流入/流出
- 正在发生的交易所事件

不允许内容：

- 过时的历史事件结论
- 旧市场价位当成事实

### 3. 经验记忆

用途：

- 记录长期流程经验
- 记录重复出现的错误模式

允许内容：

- “不要复用 stale OI”
- “缺少 mark/index 时必须压低置信度”
- “reviewer 必须彼此独立”

不允许内容：

- “昨天看多，所以今天也应该看多”
- 把原始交易建议直接当成下一轮输入

### 4. 审计日志

用途：

- 追加式记录事实、工具调用、agent 输出、审查结果和最终计划

允许内容：

- 完整追踪链路
- 证据包
- 决策元数据

不允许内容：

- 默认参与下一轮 live decision
- 隐式修改之前的结论

## Episode 模型

把一段连续对话看成一个 `Episode`。

一个 episode 可以跨多个轮次，但每一轮都必须重新刷新市场事实后再产出新的决策。

### 何时开启新 episode

- symbol 变化
- horizon 明显变化
- 用户持仓状态变化
- 重大事件改变上下文

### 何时沿用当前 episode

- 用户只是在澄清同一个 symbol 和同一个交易设置
- 用户要求对当前决策做更深审查

## 多轮流转

```text
用户输入
  -> DialogueManager
  -> Episode 识别
  -> 会话摘要读取
  -> 活动事件读取
  -> 经验记忆读取
  -> 刷新实时市场事实
  -> Agent workflow
  -> DecisionPlan
  -> 写入审计日志
  -> 更新会话摘要
```

## 防污染规则

1. 不要把旧价格、funding、OI、清算数据当成 live 数据复用。
2. 不要让前一轮的看多/看空结论变成后续偏见。
3. 不要让历史 agent 输出跳过新的事实采集。
4. 不要让审计日志直接影响 live direction。
5. 不要让会话记忆覆盖最新市场证据。

## 推荐数据对象

### SessionContext

```json
{
  "session_id": "uuid",
  "episode_id": "uuid",
  "symbol": "ETH-USDT-SWAP",
  "horizon": "6h",
  "position_state": "long",
  "latest_user_intent": "manual operation plan",
  "latest_summary": "用户当前持有 ETH 多单，希望看 6 小时内的操作方案"
}
```

### EpisodeSummary

```json
{
  "episode_id": "uuid",
  "symbol": "ETH-USDT-SWAP",
  "active_events": ["CPI 窗口", "ETF flow update"],
  "latest_facts": {
    "mark": null,
    "oi": null
  },
  "latest_conclusion": "trigger long",
  "conclusion_time": "2026-06-25T00:00:00Z"
}
```

### LessonEntry

```json
{
  "topic": "freshness-cap",
  "lesson": "missing mark/index must block high-confidence leverage calls",
  "severity": "high"
}
```

## 运行规则

每次新的决策都必须：

- 读取会话上下文
- 读取活动事件
- 读取经验记忆
- 刷新市场事实
- 运行 agents
- 写入新的审计记录

不要把上一轮结论直接当成 live fact。

## 设计选择

为避免过度复杂，v1 只保留以下四层：

- 会话记忆
- 事件记忆
- 经验记忆
- 审计日志

v1 不加入长文本向量记忆，也不加入自由聊天式长期语义记忆。

## 总结

系统应该记住：

- 当前在和谁讨论
- 当前 active episode 是什么
- 形成了哪些流程经验
- 最终做了什么判断以及为什么

系统不应该记住：

- 过时的市场事实
- 过时的方向结论
- 过时的模型输出当成新信号

