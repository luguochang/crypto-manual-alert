# 万物云 Agent 平台面试深度辅导（对标 pi）

> 本文档用多 agent 编排生成，基于过去辅导文档（Step 23-32 + 心智模型 + MultiAgent 5 模式 + Command 全量总结 + 面试技术准备手册）深化，对标热门项目 pi（earendil-works/pi，TypeScript coding agent 工具链，7.1 万星）提升架构高度。
>
> **对标定位**：pi 是 coding agent 工具链（类 Claude Code，开发者本机跑，npm 包无服务端），万物云是业务 agent 平台（Python，服务端多实例）。两者形态不同，对标是**架构思想对标不是代码移植**。每个模块都给"万物云怎么做 + 对标 pi 怎么做 + 对比表 + 面试追问应答"。
>
> **诚实边界**：🟢 官方/已确认　🟡 后端类比/通用 spec/重述　🔴 推断待核。🔴 项被追问时口述"推断依据/待确认"，绝不编。综合块第五节有 🔴 项速查表。
>
> **结构**：
> - 块1：项目全景 + 架构总览
> - 块2：Agent Loop + 统一 LLM 接入
> - 块3：多 Agent 编排 + 状态管理
> - 块4：长期记忆 + Agentic RAG + 上下文工程
> - 块5：HITL + MCP + 权限沙箱 + Tool calling 可靠性
> - 块6：生产实战与坑 + 部署
> - 块7（综合）：万物云 vs pi 大对比表 + 20 条面试追问 + 数字口径 + 陈述模板 + 🔴 项速查
>
> **看法顺序**：先块1 建立全景，再块2-6 各模块深入，最后块7 冲刺速查。面试前块7 的 30 秒/3 分钟陈述模板 + 🔴 项速查必背。

---
## 1. 项目一句话定位

万物云（深圳市万睿智能科技）**园区智能客服 / 座席辅助 Agent 平台**：把园区运营的高频场景（咨询、报修、工单查询、访客、车辆、设备告警）封装成可被 Agent 调用的原子 Skill，用 LangGraph StateGraph 编排多 Agent 协作链路，服务园区座席与管理员，覆盖"用户提问 → 意图路由 → 检索/工具调用 → HITL 审核 → 流式回复"的完整闭环。🟢（公司、定位口径已确认）

> 一句话面试版："我做的是园区运营助手 Agent 平台，用 LangGraph StateGraph 做多 Agent 编排，把物业咨询/报修/工单这些业务能力封装成 Skill 给 Agent 调，服务园区座席和管理员，日均约 3000 次调用。"

---

## 2. 业务场景与典型对话流

### 服务谁、解决什么问题

- **服务对象**：园区座席（一线客服）、园区管理员 🟢。不是 C 端海量用户，是园区级内部工具，使用人数有限。
- **解决什么**：座席面对的咨询跨多个业务域（物业、报修、工单、访客、车辆、设备），原来要切多个后台查；Agent 把这些能力聚合成一个对话入口，自动查、自动填草稿、写入动作走人工确认。🟡（业务定位重述）

### 典型对话流（端到端，背熟这条链）

```
用户提问
  │
  ▼
[意图分类节点] 小模型分类 + 规则风险标记（写入类/高风险关键词打标）
  │
  ▼ 条件边路由（add_conditional_edges）
  ├─ 简单查询 ──────────────► 单 Agent + Skill 直接答
  └─ 跨域/写入/高风险 ──────► 多 Agent 协作链路：
        [Supervisor/Planner] 拆任务
              │
              ▼
        [Executor] ReAct 循环调 Skill（Thought→Act→Observe）
              │   缺槽位 → 追问补全
              │   需知识 → [知识检索节点] RAG 召回园区规则/SOP
              ▼
        [风险控制节点] 写入/高风险校验
              │
              ▼
        [写入节点前] interrupt_before 暂停 ──► 前端弹确认卡（HITL）
              │                                  │
              │  ◄──────────────────────────────  用户确认/修改
              ▼
        Command(resume=...) 恢复执行写入
              │
              ▼
        [生成节点] 流式输出（SSE）逐 token 推前端
              │
              ▼
        任务结束 ──► 异步回写长期记忆（pgvector，similar merge + TTL）
```

### 后端类比（🟡，帮你把这条链映射到熟悉的东西）

| Agent 链路环节 | 后端类比 |
|---|---|
| 意图分类 + 条件路由 | API 网关按规则路由 / Activiti 排他网关（XOR） |
| Supervisor/Planner 拆任务 | 工作流里"任务规划"节点 |
| Executor ReAct 循环 | Spring 里带重试的 service 调用循环 |
| interrupt_before 暂停 | Activiti receiveTask 挂起等 signal / SseEmitter 暂停等用户输入 |
| Command(resume=) 恢复 | 跨请求读档续跑（不是线程 await，是存档退出+新请求读档） |
| 长期记忆 pgvector | Redis 用户画像（跨 session 持久） |
| Checkpointer | ACT_RU_EXECUTION 持久化表 / HttpSession |

---

## 3. 规模数字（带口径，被追问怎么算）

| 指标 | 值 | 口径 / 标注 |
|---|---|---|
| Agent 日均调用 | 约 3000 次 | 🟢 园区级内部工具，服务座席/管理员，按 trace_id 统计；不是上限是真实使用量 |
| 峰值 QPS | 约 2-3 QPS | 🟡 工作时段集中；Agent 瓶颈是 LLM 推理不是吞吐，QPS 本不高 |
| 月 token 量 | 约 2.7 亿 | 🟡 加权均约 3k token/次 × 3000 次/天 × 30 天 |
| 月成本 | 数百元至近千元 | 🟡 DeepSeek 定价估算 |
| 单次 token | 简单 1-2k / 复杂 5-15k | 🟡 简单=意图分类+一次生成；复杂=多次 LLM 调用 |
| 端到端延迟 | 简单 2-4s / 复杂 5-10s | 🟡 瓶颈是 LLM 推理 |
| 复杂任务成功率 | 约 70% | 🟡 150 条评测样本正确完成占比，人工+LLM-judge |
| 意图分类准确率 | 约 88% | 🟡 离线样本测的小模型分类准确率 |
| Skill 数 | 约 12 个 | 🟢 咨询/报修/工单/访客/车辆/告警等 |
| recursion_limit | 约 25 | 🟢 框架自带兜底，万物云调了阈值 |

> ⚠️ **关键区分（别穿帮）**：万物云 Agent 平台的"约 3000 次/天、2-3 QPS"是**用户请求**量级；万物云还有个 IoT PaaS 项目，那里"约 2000 条/秒"是**设备消息上报吞吐**（万余台设备心跳/遥测聚合），**不是用户请求 QPS**。两个项目的数字别混。🟢（边界 12）

---

## 4. 技术栈与分层

### 万物云技术栈（按 LangGraph 分层）

| 层 | 技术 | 标注 |
|---|---|---|
| 编排框架 | LangGraph StateGraph（Python） | 🟢 生产口径；框架选型经原型验证 |
| Agent runtime | create_agent（LangChain v1，替代 create_react_agent） | 🟢 |
| LLM 接入 | 国产模型为主（DeepSeek/Qwen/GLM），function calling 降级链路 | 🟡 |
| 短期记忆 / Checkpointer | PostgresSaver 或 Redis | 🔴 待确认（见万物云口径小节） |
| 长期记忆 | pgvector + similar merge + TTL（自建 cron 触发整理） | 🟢 主体已确认；cron🔴推断 |
| HITL | interrupt_before（静态）+ Command(resume=) 恢复 | 🟢 |
| 工具层 | MCP 自建（tools/list + tools/call 等价），非官方 SDK | 🟢 |
| 知识检索 | pgvector(HNSW) 向量召回（园区规则/SOP） | 🟡 万物云有知识检索节点；完整 Agentic RAG 是中建项目 |
| 流式输出 | SSE（FastAPI StreamingResponse） | 🟢 |
| 可观测 | 自研 trace_id 全链路（数据合规不出公网） | 🟢 |
| 并发控制 | FastAPI 异步 + 限流 + Redis 锁（double-texting 自建） | 🟡 主体；Redis 锁🔴推断 |
| 循环兜底 | recursion_limit（框架自带，约 25） | 🟢 |

### 对标 pi 的 monorepo 分层（架构思想对标，非代码移植）

pi（TypeScript coding agent 工具链，类 Claude Code）的 monorepo 分层 🟢（pi 根 README 核对）：

| pi 包 | 职责 | 万物云对应层 |
|---|---|---|
| pi-ai | 统一多 provider LLM API（OpenAI/Anthropic/Google） | LLM 接入层（国产模型 + 降级链路） |
| pi-agent-core | Agent runtime + tool calling + state management | Agent runtime（create_agent） |
| pi-orchestrator / pi-coding-agent | 编排 + 上层应用 | 编排层（StateGraph） |

**关键差异（边界 13，面试别讲混）**：

| 维度 | pi（coding agent） | 万物云（业务 agent 平台） |
|---|---|---|
| 语言/定位 | TypeScript，coding agent 工具链 | Python，业务 agent 平台 |
| 权限 | 无内置，靠容器（Gondolin/Docker/OpenShell） | 自建（allowed_skills + risk_flags 配置化） |
| HITL | 无内置 | interrupt_before + Command(resume=) |
| RAG | 无（coding agent 用文件系统） | 有（pgvector 知识检索节点） |
| 记忆 | AGENTS.md 文件 + session-resources | pgvector + similar merge + TTL（非文件式） |
| 对标性质 | 架构思想对标，**不是代码移植** | — |

> 一句话：pi 是"给开发者用的 coding agent"，万物云是"给园区座席用的业务 agent"，分层思想可以借鉴（LLM 接入 / runtime / 编排三层分离），但万物云的 HITL、RAG、长期记忆、权限这几层都是 pi 没有而万物云自建的。

---

## 5. 你的角色与负责模块

### 角色口径（核心开发，非 owner）🟢

- **公司**：深圳市万睿智能科技有限公司
- **时间**：2023.05 - 2025.11
- **角色**：核心开发（非 tech lead / 非 owner）
- **职级**：后端开发工程师，2025.01 起转 AI 应用方向

### 负责模块（按辅导文档口径）

- **后端服务化**：把园区业务能力封装成 Skill（注册 + 元数据 + 触发条件 + 执行逻辑），对接后端业务接口
- **多 Agent 编排链路**：StateGraph 节点/边设计、条件路由、Supervisor/Planner/Executor 协作链路（**这是我主导设计的子模块**）
- **工具接入层**：MCP 自建（tools/list + tools/call 等价 + 鉴权审计 + 懒加载）
- **可观测**：自研 trace_id 全链路 + 离线评测集

### 架构谁拍板（追问应答）

> "整体架构 lead 拍板，我参与方案讨论并负责我这块的设计与实现，比如多 Agent 协作链路、工具接入层是我主导设计的子模块。" 🟡（角色口径）

> ⚠️ **别踩**：别说"主导整个平台"，问团队规模/owner 就穿。"主导子模块"可以。

---

## 6. 架构总览图（ASCII）

```
                          ┌─────────────────────────────────┐
                          │   用户（座席 / 管理员）           │
                          └──────────────┬──────────────────┘
                                         │ HTTP（带 trace_id）
                                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FastAPI 网关（异步 + 限流 + Redis 锁 double-texting 自建🔴推断）       │
│  TracingMiddleware 拦截 → 恢复 trace 上下文 → contextvar              │
└──────────────┬───────────────────────────────────────────────────────┘
               │ graph.invoke(init, {thread_id, recursion_limit=25})
               ▼
════════════════════════ LangGraph StateGraph（Custom workflow 🔴推断）═════
║  State: messages(+add_messages) / intent / slots / plan /            ║
║         scratchpad / risk_flags / allowed_skills                     ║
║                                                                       ║
║  START                                                               ║
║    │                                                                  ║
║    ▼                                                                  ║
║  [intent_node] 意图分类(小模型) + 规则风险标记                          ║
║    │                                                                  ║
║    ▼ add_conditional_edges                                            ║
║    ├─"single"─────────────► [executor] ReAct 调 Skill 直接答          ║
║    └─"multi"──────────────► [supervisor] LLM 决定下一个 worker        ║
║                                  │                                    ║
║              ┌───────────────────┼───────────────────┐                ║
║              ▼                   ▼                   ▼                ║
║         [planner]           [executor]          [knowledge]          ║
║          拆任务            ReAct 调 Skill        RAG 召回             ║
║              │            (调 MCP 工具层)       pgvector             ║
║              │                   │                   │                ║
║              └───────────────────┼───────────────────┘                ║
║                                  ▼                                    ║
║                            [risk_node] 写入/高风险校验                ║
║                                  │                                    ║
║                                  ▼                                    ║
║                  ╔═══════════════════════════╗                       ║
║                  ║ interrupt_before=["risk"] ║  ◄── HITL 静态暂停    ║
║                  ║   暂停 → state 落 Checkpointer                   ║
║                  ║   HTTP 返回 → 前端弹确认卡                         ║
║                  ╚═══════════════════════════╝                       ║
║                                  │ 用户确认                           ║
║                                  ▼ Command(resume={approved:True})   ║
║                            [执行写入]                                 ║
║                                  │                                    ║
║                                  ▼                                    ║
║                            [generate] SSE 流式输出                    ║
║                                  │                                    ║
║                                  ▼                                    ║
║                               END                                     ║
╚═══════════════════════════════════════════════════════════════════════╝
        │                                          │
        ▼                                          ▼
┌───────────────────────┐              ┌───────────────────────────┐
│  Checkpointer          │              │  长期记忆 pgvector         │
│  (PostgresSaver 或     │              │  namespace+key JSON       │
│   Redis 待确认🔴)      │              │  + 向量索引(HNSW)          │
│  按 thread_id 存 state │              │  similar merge + TTL      │
│  支撑多轮/中断恢复      │              │  自建 cron 整理🔴推断       │
└───────────────────────┘              │  跨 thread 用户画像/工单摘要│
                                       └───────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  MCP 工具层（自建，非官方 SDK）🟢                          │
│  Skill 注册中心(=tools/list) + 执行调度(=tools/call)      │
│  + 元数据懒加载 + 统一鉴权审计                             │
│  约 12 个 Skill：咨询/报修/工单/访客/车辆/告警/规则检索... │
└───────────────────────────────────────────────────────────┘
```

### 图里 8 个关键件（逐个对应后端类比 🟡）

| 件 | 后端类比 |
|---|---|
| StateGraph | Activiti 工作流引擎（自定义流程图） |
| State（TypedDict） | 流程变量 Process Variable |
| Node（普通函数，装 agent/逻辑/检索） | ServiceTask（delegate 代码随便装） |
| 条件边 add_conditional_edges | 排他网关 XOR gateway |
| interrupt_before | receiveTask 挂起等 signal |
| Checkpointer | ACT_RU_EXECUTION 持久化表 / HttpSession |
| Command(resume=) | 跨请求读档续跑（非线程 await） |
| 长期记忆 pgvector | Redis 用户画像（跨 session） |

---

## 7. 30 秒电梯陈述模板（直接背）

> "我做的是万物云的园区运营助手 Agent 平台，用 LangGraph 的 StateGraph 做多 Agent 编排。把物业咨询、报修、工单查询这些业务能力封装成大约 12 个 Skill 给 Agent 调。用户提问进来，先经意图分类加规则风险标记做条件路由，简单查询走单 Agent，跨域或写入类走多 Agent 协作链路——Supervisor 拆任务、Executor 用 ReAct 调 Skill、需要知识走 RAG 检索、写入动作前用 interrupt_before 暂停等人工确认，确认后用 Command resume 恢复。短期记忆靠 Checkpointer 按 session 续接，长期记忆用 pgvector 做相似合并加 TTL 治理。日均约 3000 次调用，复杂任务成功率约 70%。我在团队是核心开发，负责多 Agent 编排链路和工具接入层这两块的设计和实现。"

---

## 8. 3 分钟深入陈述模板

> **（0-30s）定位与规模**：万物云园区运营助手 Agent 平台，服务园区座席和管理员，日均约 3000 次调用，峰值 2-3 QPS——Agent 类应用瓶颈是 LLM 推理不是吞吐，量级本来就不大。月 token 约 2.7 亿，成本几百到近千元。
>
> **（30-90s）编排核心**：编排用 LangGraph StateGraph，本质是个图执行引擎，类比 Activiti。我定义了一个共享 State——messages 用 add_messages 累加，加意图、槽位、plan、scratchpad、risk_flags、allowed_skills 这些结构化字段。每个 Agent 是图上一个 node（node 是普通函数，里面装 create_agent）。意图分类后用条件边路由：简单查询走单 Agent，跨域或写入类走多 Agent 链路。多 Agent 用 Supervisor 模式——Supervisor 节点用 LLM 决定下一步调哪个 worker，循环到 FINISH；Executor 内部是 ReAct 循环调 Skill。这对应官方 5 种 multi-agent 模式里的 Custom workflow。
>
> **（90-150s）生产化关键件**：写入类动作前用 interrupt_before 静态暂停，state 落 Checkpointer，HTTP 请求结束返回前端，用户确认后发新请求带 Command(resume=) 读档续跑——这是跨请求的中断恢复，不是线程 await。短期记忆靠 Checkpointer 按 thread_id 续接多轮，长期记忆用 pgvector 存用户常用园区、关注设备、历史工单摘要，做相似合并去噪加 TTL 淘汰，自建 cron 触发整理。工具层是自建的 MCP 等价实现——只做了 tools/list 和 tools/call，加了鉴权审计和懒加载，没接官方 SDK。
>
> **（150-180s）可观测与角色**：可观测是自研 trace_id 串全链路——用户原始问题、意图分类、槽位、Skill 调用链、推理摘要、异常原因，因为园区数据不能出公网所以没用 Langfuse。搭了约 150 条评测样本，复杂任务成功率约 70%，主要失败在槽位歧义和跨域拆解。我在团队是核心开发不是 owner，整体架构 lead 拍板，我主导设计了多 Agent 协作链路和工具接入层这两个子模块。

---

## 万物云口径（诚实边界，单独小节，面试照这个讲）

> 这一节是"哪些是确认的、哪些是推断待核"的清单。被追问到细节时，照标注讲，别把🔴推断说成已确认。

| # | 项 | 口径 | 标注 |
|---|---|---|---|
| 1 | 生产框架 | 用 LangGraph StateGraph（Python）；遇"自研 vs 调包"追问口述"框架选型经原型验证" | 🟢 |
| 2 | 长期记忆 | pgvector + similar merge + TTL（**不是** RedisStore、**不是** AGENTS.md 文件式）；Store 无内置 TTL，万物云自建 cron 触发整理 | 🟢 主体 / 🔴 cron 实现 |
| 3 | MCP | 自建，非官方 SDK，只实现 tools/list + tools/call 等价（没接 Resources/Prompts） | 🟢 |
| 4 | recursion_limit | 用框架自带（万物云=25），口径"用框架自带兜底并调了阈值" | 🟢 |
| 5 | HITL | 用 interrupt_before（静态），官方推荐 interrupt()+HumanInTheLoopMiddleware 但万物云用 interrupt_before；恢复用 Command(resume=) | 🟢 |
| 6 | multi-agent 模式归类 | Custom workflow（StateGraph） | 🔴 推断（基于 StateGraph + interrupt_before + create_agent，源文档没明确归类） |
| 7 | Deep Agents | 没用（用 StateGraph + create_agent 自建） | 🟢 |
| 8 | Checkpointer 后端 | PostgresSaver 还是 Redis | 🔴 待用户确认（文档标"待确认"，面试按真实讲，别瞎称 PostgresSaver 被表结构追问翻车） |
| 9 | 路由实现 | 主要用条件边 add_conditional_edges；是否用 Command(goto) | 🟢 条件边为主 / 🔴 Command(goto) 待核 |
| 10 | double-texting | 4 策略是 Agent Server only（非 OSS），万物云自建 Redis 锁 | 🔴 推断 |
| 11 | 公司/角色 | 深圳市万睿智能科技；2023.05-2025.11；核心开发（非 owner）；后端开发工程师（2025.01 起转 AI 应用方向） | 🟢 |
| 12 | 数字 | Agent 日均约 3000 次（园区级，服务座席/管理员），峰值 2-3 QPS，月约 2.7 亿 token（月数百元至近千元）；IoT 2000 条/秒是设备消息上报吞吐（非用户请求并发） | 🟢 |
| 13 | pi 对标 | pi 是 TypeScript coding agent 工具链，万物云是 Python 业务 agent 平台；架构思想对标不是代码移植；pi 无内置权限/HITL/RAG，记忆靠 AGENTS.md 文件 | 🟢 |

**三色含义**：🟢 官方/已确认　🟡 后端类比/通用 spec/重述　🔴 推断待核（讲时标明"我推断的"，别当确认事实）

---

## 检查题（答得出再进下一块）

1. **项目一句话定位**：万物云 Agent 平台服务谁？解决什么问题？日均调用多少？为什么 QPS 这么低？
2. **典型对话流**：用户提问后到流式回复，经过哪些节点？interrupt_before 在哪个节点前停？停完怎么恢复？为什么说"不是线程 await 是存档读档"？
3. **技术栈对标**：pi 的 monorepo 三层（pi-ai / pi-agent-core / pi-orchestrator）对应万物云哪三层？pi 没有而万物云自建的有哪些层？
4. **角色边界**：你是 owner 还是核心开发？架构谁拍板？你主导设计的子模块是哪两个？被问"团队多少人/谁拍板"怎么答不穿帮？
5. **诚实边界**：Checkpointer 后端是 PostgresSaver 还是 Redis？multi-agent 归类为 Custom workflow 是确认的还是推断的？被追问到这两个🔴项怎么诚实应答？

### 检查题答案要点（面试口径）

**Q1**：服务园区座席和管理员（不是 C 端海量）；把物业咨询/报修/工单聚合成一个对话入口；日均约 3000 次；QPS 低因为 Agent 瓶颈是 LLM 推理不是吞吐，且是园区级内部工具使用人数有限。

**Q2**：意图分类 → 条件路由 → 单/多 Agent 链路（Supervisor→Planner→Executor ReAct→知识检索→风险控制）→ 写入节点前 interrupt_before 暂停 → Command(resume=) 恢复 → SSE 流式生成。停的是写入类节点前。不是线程 await：interrupt 时 state 落 Checkpointer，HTTP 请求结束返回，用户确认后发新请求带 Command(resume=) 读档续跑，是跨请求的中断恢复。

**Q3**：pi-ai↔LLM 接入层、pi-agent-core↔Agent runtime（create_agent）、pi-orchestrator↔编排层（StateGraph）。pi 没有而万物云自建：HITL（interrupt_before）、RAG（pgvector 知识检索）、长期记忆（pgvector+merge+TTL，非 AGENTS.md 文件）、权限（allowed_skills+risk_flags）。

**Q4**：核心开发非 owner；整体架构 lead 拍板，我参与方案讨论；主导设计多 Agent 协作链路 + 工具接入层两个子模块。别说"主导整个平台"。

**Q5**：Checkpointer 后端待确认🔴——口述"短期记忆用 Checkpointer 按 thread_id 持久化，具体后端是 PostgresSaver 还是 Redis 我按实际讲"，别瞎称 PostgresSaver 被表结构追问翻车。multi-agent 归类 Custom workflow 是🔴推断——口述"我们用 StateGraph 自定义执行流，对应官方 Custom workflow 模式，混合确定性节点和 agentic 节点"，别说成已确认归类。

---

**相关素材路径**（自己复习用）：
- 主辅导 Step24（Multi-Agent 体系化）：`F:\file\claudework\ragProject\resume\agent\Agent工程逐步辅导记录.md`（第 2716 行起）
- 心智模型地基：`F:\file\claudework\ragProject\resume\agent\Agent工程LangGraph心智模型.md`
- Multi-Agent 5 模式：`F:\file\claudework\ragProject\resume\agent\Agent工程MultiAgent模式.md`
- 面试技术准备手册（角色口径/数字备忘）：`F:\file\claudework\ragProject\resume\面试技术准备.md`
- pi 根 README（monorepo 分层核对）：`C:\Users\admin\.claude\jobs\cbe4f308\tmp\pi_readme.md`

---

## 万物云 Agent Loop 怎么转：create_agent 组装的 ReAct 循环

### 一句话定位

Agent 底层就是一个 `while(true)`：把上下文喂给模型 -> 模型决定调不调工具 -> 调就执行工具、把结果塞回 messages -> 再喂给模型……直到模型返回纯文本（没有 `tool_calls`）就跳出。🟢 这就是 ReAct（Reasoning-Action-Observation 循环）。LangChain 的 `create_agent` 帮你把这张图组装好；万物云生产是**手动用 LangGraph StateGraph 搭等价的图**（原因见第5步：需要非标准拓扑 + 当时 create_agent 不成熟），但单 agent 内部的循环语义和 create_agent 完全一样。🟢

> 诚实边界：万物云生产用「手动 StateGraph」而非直接调 `create_agent`，但二者搭出来的 ReAct 循环是同一个东西。下面伪代码用 create_agent 的视角讲循环体（最干净），万物云生产等价于把同样的 agent 节点 + tool 节点 + 条件边手动写进 StateGraph。🟢

### 生产伪代码（万物云单 agent 的循环体，Python）

```python
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain_core.messages import SystemMessage
from langgraph.errors import GraphRecursionError

# 1. 模型 + 工具绑定（LLM 接入见下一节）
model = init_chat_model("openai:gpt-4o")          # 🟡 通用工厂，万物云具体哪家🔴待确认
bound = model.bind_tools(tools, tool_choice="auto") # 绑工具 + 调用策略

# 2. 组装成 agent（create_agent 内部就是搭一张 ReAct 图）
agent = create_agent(
    model=bound,
    tools=tools,
    system_prompt="你是万物云客服。先查后答，禁止不查就编。",  # 防幻觉硬约束
)

# 3. 跑循环，带 recursion_limit 兜底
try:
    result = agent.invoke(
        {"messages": [HumanMessage("查订单 ORD-001，没发货就退款")]},
        config={"recursion_limit": 25},   # 🟢 框架自带兜底，万物云调过阈值
    )
except GraphRecursionError:
    result = {"messages": [SystemMessage("任务过于复杂，已记录，转人工。")]}  # 🟡 触发兜底要降级，不能直接报错
```

### 逐行解释

| 行 | 作用 | 关键点 |
|---|---|---|
| `init_chat_model("openai:gpt-4o")` | 通用模型工厂，`"provider:model"` 字符串指定 provider+模型 | 🟡 LangChain 1.0 推荐入口，换 provider 只改字符串 |
| `bind_tools(tools, tool_choice=...)` | 把工具清单 + 调用策略绑到模型实例上 | 🟢 绑死后这个 model 实例每次调用都带这套工具 |
| `create_agent(model=..., tools=..., system_prompt=...)` | 组装标准 ReAct 图（agent 节点 + tool 节点 + 条件边回环） | 🟢 万物云生产手动搭等价图，循环语义相同 |
| `config={"recursion_limit": 25}` | 框架层防死循环兜底 | 🟢 口径：「用框架自带的兜底并调了阈值」 |
| `except GraphRecursionError: 降级` | 撞到 25 轮不能直接报错给用户 | 🟡 返回友好降级 + 记录，类似 Java 兜底 catch |

### 循环里到底跑什么（一轮 = 2 条消息）

```
[0] SystemMessage("你是客服…")
[1] HumanMessage("查订单 ORD-001…")
─── 第1轮 ───
[2] AIMessage(content="好的先查", tool_calls=[{search_order, ORD-001, id=call_a}])
[3] ToolMessage("订单已发货", tool_call_id="call_a")   ← 必须带 id 关联
─── 第2轮 ───
[4] AIMessage("您的订单已发货，暂不支持退款…")          ← 没有 tool_calls → 循环结束
```

三个铁律（🟢）：
1. **每轮模型看到的是「到目前为止的全部 messages」**，不是只看上一条——这是 agent 能「接着上次继续」的基础。
2. **一轮通常加 2 条**：一条 `AIMessage(tool_calls)` + 一条 `ToolMessage(结果)`；最后一轮只加 1 条无 tool_calls 的 AIMessage。
3. **messages 只增不减**（除非主动裁剪）——`add_messages` reducer 是「追加」不是「覆盖」。

### 循环怎么停：4 种终止 + 死循环三层防护

| # | 终止条件 | 谁决定 | 性质 |
|---|---|---|---|
| 1 | 模型返回纯文本、无 tool_calls | 模型自己 | 正常结束（默认） |
| 2 | 达到 recursion_limit=25 | 框架兜底 | 防死循环 |
| 3 | 条件边显式路由到 END | 你的代码 | 业务主动收口 |
| 4 | interrupt 暂停 / 未捕获异常 | 人工 / 异常 | HITL 场景 |

**死循环三层防护**（万物云生产真实做法 🟢）：

- **第一层 `recursion_limit=25`（框架层）**：LangGraph 自带，最多 25 个 super-step 硬截断。口径「用框架自带兜底并调了阈值」，25 是复杂度 vs 成本的平衡点（太低做不完、太高烧钱+延迟）。🟢
- **第二层 证据增量检测（业务层）**：每次工具返回后检查 `scratchpad` 有没有新信息，连续两次无实质区别 = 原地打转，注入换思路提示，重复 2 次强制 `Command(goto="end")`。🟢
- **第三层 多步检索最多 3 跳（RAG 层）**：防无限深挖（结果一直在变但跟问题无关），到 3 跳强制停、用已有信息综合回答。🟢

为什么不只靠第一层：25 轮触发时已经烧了 25 次模型调用 + 25 次工具执行，第二三层能在第 2-3 轮就提前止损。🟡

### 后端类比表

| Agent 循环概念 | Java 后端类比 |
|---|---|
| `while(true)` 循环体 | Activiti 工作流的「用户任务节点重入」——节点执行完看条件边回不回到自己 |
| 模型决定下一步调哪个工具 | Activiti 里条件网关由**运行时变量**决定走哪条边，不是编译期写死 |
| `tool_calls` 为空 = 循环结束 | 条件边路由到 END 节点 |
| `recursion_limit=25` | 你写 IoT 后端时重试机制的 `maxRetries` 上限兜底 |
| 证据增量检测 | 重试时检测「响应有没有变化」，没变化就提前 break，不傻等到 maxRetries |
| 多步检索 3 跳 | JPA 懒加载的 `@FetchDepth(maxDepth=3)` / 递归 CTE 的深度上限 |
| `GraphRecursionError` 降级 | `catch(超时异常)` 返回降级响应而非 500 |

**最本质的认知转变**：普通 Java `while` 里每一步做什么是你写死的代码决定的；Agent `while` 里每一步做什么（调不调工具、调哪个、何时停）是**模型在运行时决定的**。你不是写每一步的代码路径，而是「设计循环框架 + 给一堆工具，让模型自己选路」。🟢

---

## 万物云 LLM 接入：多模型 / provider 管理 / 模型路由 / 失败降级

### 诚实边界先说清

万物云**具体用哪家模型（OpenAI / 通义 / DeepSeek / GLM / 豆包…）🔴待用户确认，不编**。文档里伪代码出现 `gpt-4o` 是教学示例，**不是生产口径**。下面讲的是「LangChain 体系下多模型接入的通用工程做法」，万物云按这套模式做，具体模型名面试被问就答「具体模型以项目配置为准，我不展开」。🟡

### 1. provider 管理：`init_chat_model` 通用工厂

LangChain 1.0 推荐用 `init_chat_model("provider:model")` 统一入口，换 provider 只改字符串，业务代码不动：🟡

```python
from langchain.chat_models import init_chat_model

# 同一段业务代码，换 provider 只改这一行字符串
m_openai   = init_chat_model("openai:gpt-4o")
m_anthropic= init_chat_model("anthropic:claude-sonnet-4-5")
m_qwen     = init_chat_model("tongyi:qwen-max")        # 🟡 通义
m_deepseek = init_chat_model("deepseek:deepseek-chat") # 🟡 DeepSeek
```

- 字符串格式 `"provider:model"`：冒号前是 provider id，后面是模型名。🟢
- 工厂内部根据 provider id 路由到对应 `ChatXxx` 类（`ChatOpenAI` / `ChatAnthropic` / `ChatTongyi`…）。🟢
- API key 走环境变量（`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`…），不硬编码。🟡

### 2. 模型路由：分类后路由到不同 agent（万物云做法 🟢）

`bind_tools` 的 `tool_choice` 是建 agent 时绑死的，不能一个 agent 一会儿 required 一会儿 auto。万物云做法是**意图分类后路由到不同 model 实例 / 不同 agent**：

```python
# 同一个底模，绑不同 tool_choice → 两个 model 实例
base    = init_chat_model("openai:gpt-4o")
chat_m  = base.bind_tools(tools, tool_choice="auto")       # 闲聊：自己决定
query_m = base.bind_tools(tools, tool_choice="required")  # 查询：必须查（防不查就编）

# 两个 agent
chat_agent  = create_agent(model=chat_m,  tools=tools, system_prompt="…")
query_agent = create_agent(model=query_m, tools=tools, system_prompt="…")

# 分类 → 路由
def classify(state):
    state["intent"] = llm_classify(state["messages"][-1].content)  # 业务查询 / 闲聊
    return state

def route(state):
    if state["intent"] == "业务查询":
        return "query_agent"   # required，首轮强制查防幻觉
    return "chat_agent"        # auto，省 token 省延迟
```

- **首轮 `required` 防幻觉**：业务查询类第一轮强制模型必须调检索/查询工具再回答，防止不查就编——万物云防幻觉硬手段之一。🟢
- **寒暄 `auto`/`none`**：用户说「你好」没必要调工具，省 token 省延迟。🟢
- **跨 provider 取值不同**：OpenAI 用 `"required"`，Anthropic 用 `"any"`，换模型要改。🟢 生产踩坑点。

后端类比：`bind_tools(tool_choice=...)` = 给 Service 注入「操作权限配置」；不同 model 实例 = 不同配置的 Service Bean；分类路由 = 前置 Controller 按请求类型转发到不同 Service。🟡

### 3. 失败降级：`wrap_model_call` 中间件重试 + fallback agent

模型调用可能失败（限流 429 / 超时 / provider 抖动）。万物云用 Middleware 的 `wrap_model_call` 钩子做重试（指数退避），重试耗尽走 fallback agent 降级：🟢

```python
import asyncio
from langchain.agents.middleware import AgentMiddleware

class RetryMiddleware(AgentMiddleware):
    async def wrap_model_call(self, request, handler):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return await handler(request)          # handler = 调模型
            except Exception as e:
                wait = 2 ** attempt                     # 指数退避：1s/2s/4s
                await asyncio.sleep(wait)
        raise last_error                               # 重试耗尽抛出
```

- `wrap_model_call` 完全包裹模型调用，像 Java 的 `@Around`——你拿到 `ProceedingJoinPoint`，由你决定是否 `proceed()`、调几次。🟢
- 重试耗尽后：① 走 fallback agent（换 provider 重试一遍，类似 `with_fallbacks`）；② 还失败则返回降级文案「服务繁忙，已转人工」。🟡
- **工具失败不抛异常**：工具执行失败时返回错误信息字符串而非 raise，这样模型能理解工具失败、决定换方案，不会直接打断整个循环。🟢

### 4. 万物云多模型接入的完整链路（通用做法 🟡）

```
请求进来
  → 意图分类（LLM 轻量分类器，便宜模型）
  → 路由到对应 agent（chat_agent / query_agent / admin_agent…）
    → 该 agent 的 model 实例（bind_tools 绑好的 tool_choice）
      → wrap_model_call 包裹：重试(指数退避) → 失败换 provider fallback
        → 进入 ReAct 循环（recursion_limit=25 兜底）
```

---

## 对标 pi：pi-agent-core 的 agent-loop.ts 怎么做循环

### 一句话定位

pi（TypeScript coding agent）的 `@earendil-works/pi-agent-core` 提供 `Agent` 类 + 底层 `agentLoop()` async generator。循环语义和万物云一样是 ReAct，但用 TS 的 async iterator + 事件流实现，且把「消息转换」「工具并发」「运行时打断」做成了显式机制。🟢 以下是 pi README 的事实，对标用。

### pi 的循环结构（一个 turn = 一次 LLM 调用 + 工具执行）

```
prompt("Read config.json")
├─ agent_start
├─ turn_start                              ← 一个 turn 开始
├─ message_start/end  { userMessage }
├─ message_start      { assistantMessage with toolCall }
├─ message_update...                       ← LLM 流式吐 token
├─ message_end        { assistantMessage }
├─ tool_execution_start  { toolCallId, toolName, args }
├─ tool_execution_end    { toolCallId, result }
├─ message_start/end  { toolResultMessage }
├─ turn_end           { message, toolResults: [...] }
│
├─ turn_start                              ← 下一个 turn（模型看 tool 结果再决策）
├─ message_start      { assistantMessage }
├─ message_update...
├─ message_end
├─ turn_end
└─ agent_end                               ← 循环结束
```

🟢 一次 `turn` = 一次 LLM 调用 + 这次调用触发的工具执行；多个 turn 串成 loop，直到没有 toolCall 走到 `agent_end`。和万物云「一轮 = AIMessage(tool_calls) + ToolMessage」完全同构。

### pi 消息流（关键设计：AgentMessage vs LLM Message）

```
AgentMessage[] -> transformContext() -> AgentMessage[] -> convertToLlm() -> Message[] -> LLM
                  (可选:裁剪/注入)        (必须:过滤自定义类型)
```

🟢 pi 的关键抽象：
- **`AgentMessage`** 是 agent 内部的富消息类型，可包含标准 LLM 消息（`user`/`assistant`/`toolResult`）+ 应用自定义类型（通过 declaration merging 扩展）。
- **LLM 只认 `user`/`assistant`/`toolResult`**，所以每次调 LLM 前用 `convertToLlm` 过滤掉 UI-only 消息、把自定义类型转成 LLM 格式。
- **`transformContext`** 在 convertToLlm 前跑，做裁剪/压缩（对应万物云的上下文裁剪/摘要，第18步）。

### pi 工具执行与控制

- **并发模式**：`parallel`（默认，工具并发执行，结果按 assistant 源序回写）/ `sequential`（逐个执行）。🟢 万物云 ToolNode 默认也是并发执行同一批 tool_calls。
- **`beforeToolCall` / `afterToolCall` 钩子**：前者可 block 执行（权限），后者可改结果、可返 `terminate: true`。🟢 对应万物云的 `wrap_tool_call` Middleware（权限+审计）。
- **`terminate: true`**：工具结果暗示「不用再调 LLM 了」，跳过 follow-up。🟡 万物云没有等价物，靠条件边路由到 END 实现。
- **`shouldStopAfterTurn`**：turn 结束后判断要不要优雅停（如压缩前停）。🟡 万物云靠 recursion_limit + 条件边。
- **`continue()`**：从现有 context 恢复（重试），最后一条必须是 user 或 toolResult。🟡 万物云靠 checkpointer + thread_id 恢复。
- **steering / follow-up**：运行中打断注入消息 / 完成后追加任务。🟡 万物云靠 interrupt + Command(resume) 做类似事。

### pi 的 stop reason（对应万物云终止条件）

pi 的 `AssistantMessage.stopReason`：🟢

| pi stopReason | 万物云对应 |
|---|---|
| `"stop"` 正常结束 | 模型无 tool_calls，循环结束 |
| `"toolUse"` 要调工具 | 有 tool_calls，继续循环 |
| `"length"` 撞 max tokens | （万物云类似，模型输出被截断） |
| `"error"` 出错 | 工具/模型异常 |
| `"aborted"` 被 abort | interrupt / 取消 |

---

## 对标 pi：pi-ai 的统一多 provider API

### 一句话定位

pi 的 `@earendil-works/pi-ai` 是一套「统一 LLM API」：一个 `Models` 集合持有多个 `Provider`，按 model 归属自动路由，统一了 auth、模型目录、流式协议、token/成本追踪、跨 provider 切换。🟢 这是 pi 作为通用 coding agent 工具链必须做的（要支持几十家 provider）；万物云是业务 agent 平台，只需接少数几家，用 LangChain 的 `init_chat_model` + `bind_tools` 就够。对标是**架构思想对标**，不是代码移植。🟡

### pi-ai 核心设计（README 事实 🟢）

**1. Provider = 运行时单元**
一个 provider 拥有：自己的 model catalog + 自己的 auth（API key 解析 / OAuth 流）+ 自己的 stream 行为。`Models` 集合持有 providers，每次请求按 model 归属路由到 owning provider。

**2. API 实现共享（wire protocol 复用）**
- `anthropic-messages`：Anthropic 模型用
- `openai-responses`：OpenAI 用
- `openai-completions`：xAI / Groq / Cerebras / OpenRouter / DeepSeek 等大量 OpenAI 兼容 provider 共享
- 混合 API provider（GitHub Copilot、OpenCode Zen）按 model 分派到不同 API 实现

🟡 类比：LangChain 的 `ChatOpenAI` 类被很多 OpenAI 兼容 endpoint 复用（改 `base_url` + `api_key`），同一个思路。

**3. Auth 解析优先级**（🟢）
```
explicit per-request apiKey  >  stored credential  >  env var
```
- 存储凭证优先于环境变量：一旦存了凭证，环境变量不再被查阅。
- OAuth 自动 refresh：`getAuth()` 和请求路径在 credential-store 锁内刷新过期 token，**并发请求和进程不会 double-refresh**。🟢
- `getApiKey: async (provider) => refreshToken()`：动态解析 expiring OAuth token。

**4. Header 合并顺序**（🟢）
```
provider auth headers → model.headers → explicit options.headers → transformHeaders → Provider.stream()
```
显式 > auth/model，transformHeaders 最后兜底有最终控制权。

**5. Token / 成本追踪**（🟢）
每次响应带 `usage.input` / `usage.output` / `usage.cost.total`。万物云对应：用 LangSmith integration 自动记 token 用量和成本（per-trace 账单）。

**6. 跨 provider 切换（Cross-Provider Handoff）**（🟢）
同一对话中途换模型，库自动转换消息兼容性：
- user / toolResult 消息原样透传
- 同 provider 的 assistant 消息原样保留
- **不同 provider 的 assistant 消息：thinking blocks 转成 `<thinking>` tagged text**（因为别家模型不认原生 thinking block）
- tool calls 和普通 text 不变

🟡 万物云对应：切 provider 时 tool_calls / ToolMessage 结构跨 provider 兼容性靠 LangChain 的统一消息抽象兜底；thinking block 跨家基本不传（业务 agent 少用 thinking）。

**7. compat flags（处理 OpenAI 兼容服务器差异）**（🟢）
`compat` 字段处理各家细微差异：`supportsDeveloperRole`（用 system 还是 developer 角色）、`supportsReasoningEffort`、`maxTokensField`（`max_completion_tokens` vs `max_tokens`）、`thinkingFormat`（openai/openrouter/deepseek/qwen…）、`requiresToolResultName` 等。
🟡 类比：万物云跨 provider 时遇到的「OpenAI 用 required、Anthropic 用 any」就是同类差异，LangChain 在 `bind_tools` 层做兼容。

**8. 自建 provider**：`createProvider({ id, auth, models, api })` 给本地推理服务器 / 代理 / 任意 OpenAI 兼容 endpoint 用。🟢 万物云接私有部署模型也走类似思路（`ChatOpenAI(base_url=..., api_key=...)` 指向自建网关）。

---

## 对比表

### Agent Loop 对比（万物云 vs pi agent-loop）

| 维度 | 万物云（LangGraph / create_agent） | pi（pi-agent-core） |
|---|---|---|
| 语言 | Python | TypeScript |
| 循环实现 | StateGraph 的 agent 节点 + tool 节点 + 条件边回环 | `agentLoop()` async generator + 事件流 |
| 一个 turn | 一次 LLM 调用 + 工具执行（加 AIMessage + ToolMessage） | `turn_start` → LLM → tool_execution → `turn_end`（同构） |
| 消息类型 | SystemMessage/HumanMessage/AIMessage/ToolMessage 四类 🟢 | AgentMessage（含标准 + 自定义类型），`convertToLlm` 过滤后喂 LLM 🟢 |
| 工具并发 | ToolNode 默认并发执行同一批 tool_calls 🟡 | `parallel`(默认)/`sequential` 显式可选 🟢 |
| 工具权限 | `wrap_tool_call` Middleware（权限+审计）🟢 | `beforeToolCall`(可 block)/`afterToolCall` 钩子 🟢 |
| 提前停 | 条件边路由到 END / recursion_limit / 证据增量 🟢 | `terminate:true`（工具暗示停）/ `shouldStopAfterTurn` 🟢 |
| 运行中打断 | interrupt + Command(resume) 🟢 | steering（注入消息改方向）🟢 |
| 重试/恢复 | checkpointer + thread_id 恢复 🟢 | `continue()` 从现有 context 恢复 🟢 |
| 死循环兜底 | recursion_limit=25 + 三层防护 🟢 | （README 未显式提循环上限，靠 stop reason + shouldStopAfterTurn）🟡 |
| 流式输出 | astream_events + SSE 🟢 | subscribe 事件流（message_update/text_delta）🟢 |

### LLM 接入对比（万物云 vs pi-ai）

| 维度 | 万物云（LangChain 体系） | pi（pi-ai） |
|---|---|---|
| 统一入口 | `init_chat_model("provider:model")` 🟡 | `Models` 集合 + provider factories 🟢 |
| provider 粒度 | 每个 `ChatXxx` 类 = 一个 provider 🟡 | `Provider` = 运行时单元（catalog+auth+stream）🟢 |
| API 协议复用 | `ChatOpenAI` 被 OpenAI 兼容 endpoint 复用 🟡 | `openai-completions` 等共享 wire protocol 🟢 |
| Auth 解析 | 环境变量为主 🟡 | stored credential > env var，OAuth 锁内防 double-refresh 🟢 |
| 模型路由 | 意图分类 → 路由到不同 agent（不同 model 实例）🟢 | `Models` 按 model 归属自动路由到 owning provider 🟢 |
| 跨 provider 切换 | 靠统一消息抽象兜底 🟡 | 显式 Cross-Provider Handoff（thinking→text）🟢 |
| 兼容性差异处理 | `bind_tools` 层（required vs any）🟡 | `compat` flags（supportsDeveloperRole 等）🟢 |
| 成本追踪 | LangSmith integration 自动记 🟢 | 每响应带 usage.input/output/cost.total 🟢 |
| 失败重试 | `wrap_model_call` Middleware 指数退避 🟢 | （README 未显式提，靠 error stopReason + continue 重试）🟡 |
| 自建 provider | `ChatOpenAI(base_url=...)` 指向自建网关 🟡 | `createProvider({id,auth,models,api})` 🟢 |

**核心差异**：pi-ai 是「通用工具链必须支持几十家 provider」所以把 provider/auth/compat 抽象做得很重；万物云是「业务平台只接少数几家」所以用 LangChain 通用工厂 + 分类路由就够，重的是业务侧的意图分类和防幻觉策略，不是 provider 适配层。🟡

---

## 面试追问应答

**Q1：你们 agent loop 怎么防死循环？**
答：三层防护。第一层 `recursion_limit=25`，框架自带的兜底，我调过阈值——太低复杂任务做不完，太高烧钱+延迟高，25 是平衡点。第二层业务层证据增量检测，连续两次工具结果无实质区别就判定原地打转，注入换思路提示，重复 2 次强制结束。第三层多步检索最多 3 跳，防 RAG 无限深挖。三层各管一段：第一层防停不下来，第二层防原地打转，第三层防无限深挖。撞到 recursion_limit 不能直接报错，要 `except GraphRecursionError` 返回降级文案转人工。

**Q2：多模型怎么接入？换 provider 要改很多代码吗？**
答：用 LangChain 的 `init_chat_model("provider:model")` 通用工厂，换 provider 只改字符串，业务代码不动。API key 走环境变量不硬编码。模型路由是意图分类后路由到不同 agent：业务查询类首轮 `tool_choice="required"` 强制查防幻觉，闲聊类走 `auto` 省 token。跨 provider 有兼容差异要注意（OpenAI 用 required、Anthropic 用 any）。
（被追问具体用哪家）「具体模型以项目配置为准，我不展开。」🔴

**Q3：模型调用失败怎么处理？**
答：用 Middleware 的 `wrap_model_call` 钩子做重试，指数退避（1s/2s/4s），max_retries=3。重试耗尽走 fallback agent（换 provider 再试），还失败返回降级文案转人工。工具失败不抛异常，返回错误信息字符串给模型，让模型自己决定换方案——这点很重要，抛异常会直接打断整个循环。

**Q4：和 pi 的统一 LLM API 比你怎么做？**
答：pi-ai 是通用 coding agent 工具链，要支持几十家 provider，所以把 provider/auth/compat 抽象做得很重（Provider 运行时单元、shared wire protocol、OAuth 锁内防 double-refresh、cross-provider handoff 把 thinking 转 text、compat flags 处理各家差异）。万物云是业务 agent 平台只接少数几家，用 LangChain 的 `init_chat_model` 通用工厂 + `bind_tools` 分类路由就够，重的是业务侧意图分类和防幻觉，不是 provider 适配层。架构思想对标（统一入口 + 按 model 路由 + auth 解析优先级 + 成本追踪），但实现轻重不一样——这是场景决定的，不是谁好谁坏。

**Q5：你们 agent loop 和 pi 的 agent loop 本质一样吗？**
答：本质一样，都是 ReAct 循环：一次 LLM 调用 + 工具执行 = 一个 turn，多个 turn 串成 loop，直到没有 toolCall 走到结束。差异在实现语言和机制：万物云用 Python 的 LangGraph StateGraph（agent 节点 + tool 节点 + 条件边回环），pi 用 TypeScript 的 async generator + 事件流。pi 多了 `terminate:true`（工具暗示停）、`shouldStopAfterTurn`（优雅停）、steering（运行中打断）这些显式机制；万物云靠条件边路由到 END + interrupt + Command(resume) 实现等价能力。死循环兜底万物云有 recursion_limit=25 + 三层防护，pi 靠 stop reason + shouldStopAfterTurn。

---

## 万物云口径

- **框架**：生产用 LangGraph StateGraph（Python），单 agent 内部循环语义 = create_agent 组装的 ReAct 循环；手动建图是为了拿非标准拓扑控制权（意图分类在循环前、风控在路由层、Plan-and-Execute 骨架）。🟢
- **Agent Loop**：`while(true)` 的 LLM决策 → tool调用 → ToolMessage 回写 → 再决策；终止靠模型无 tool_calls（默认）/ recursion_limit=25（框架兜底）/ 条件边跳 END / interrupt。🟢
- **recursion_limit=25**：口径「用框架自带的兜底并调了阈值」，25 是复杂度 vs 成本的平衡点；触发要降级不能报错。🟢
- **死循环三层防护**：recursion_limit=25（框架层）+ 证据增量检测（业务层）+ 多步检索 3 跳（RAG 层）。🟢
- **LLM 接入**：`init_chat_model("provider:model")` 通用工厂 + `bind_tools(tool_choice=...)` 分类路由 + `wrap_model_call` Middleware 重试降级。🟡 通用做法
- **具体用哪家模型 🔴待用户确认，不编**：文档伪代码的 `gpt-4o` 是教学示例，面试被问答「具体模型以项目配置为准」。
- **multi-agent = Custom workflow (StateGraph) 🔴推断**：基于 StateGraph + interrupt_before + create_agent 推断，不要说成已确认。
- **对标 pi**：架构思想对标（统一 LLM 入口 + 按 model 路由 + auth 优先级 + 成本追踪 + ReAct 循环），不是代码移植。pi 是通用 coding agent 工具链必须支持几十家 provider 所以 provider 抽象重；万物云是业务平台接少数几家所以重业务侧分类防幻觉。🟡

---

## 检查题

**题1**：万物云 Agent Loop 的一个 turn 通常往 messages 里加几条消息？分别是什么？最后一个 turn 为什么例外？

**题2**：`recursion_limit=25` 已经能保证不死循环了，为什么万物云还要加第二层（证据增量检测）和第三层（多步检索 3 跳）？只靠第一层会有哪三个实际问题？

**题3**：万物云做模型路由时，为什么用「分类后路由到不同 agent」而不是「一个 agent 运行时动态切 tool_choice」？首轮 `required` 用在什么场景、又会在什么场景反而造幻觉？

**题4**：模型调用失败时，万物云的 `wrap_model_call` 重试耗尽后怎么处理？工具执行失败时为什么不抛异常而是返回错误信息字符串？

**题5**：pi-ai 的 Auth 解析优先级是什么？为什么「存储凭证优先于环境变量」且 OAuth refresh 要放在 credential-store 锁内？这解决了什么并发问题？万物云对应做法是什么？

（答案要点：题1—2条 AIMessage(tool_calls)+ToolMessage，最后轮只加1条无tool_calls的AIMessage因为循环结束；题2—只靠第一层会①浪费成本25轮②用户体验差干等③抓不住原地打转vs无限深挖两种失控；题3—bind_tools建agent时绑死不能运行时切，required防不查就编但用在寒暄会逼模型编订单号造幻觉；题4—重试耗尽走fallback agent换provider再试还失败降级转人工，工具失败抛异常会打断整个循环而返回字符串让模型自己换方案；题5—explicit apiKey>stored credential>env var，存储凭证优先保证不会env泄漏覆盖配置，锁内refresh防并发请求double-refresh轮换token，万物云用环境变量为主+wrap_model_call重试）


---

## 1. 万物云 multi-agent 编排：StateGraph + 条件路由（Custom workflow 🔴推断）

### 1.1 编排选型：为什么用 StateGraph 不用 Subagents/Handoffs middleware

万物云 multi-agent 口径是 **Custom workflow（StateGraph 自定义执行流）**🔴推断。依据三条已确认事实：用 StateGraph 🟢、用 interrupt_before 做人工审核 🟢、用 create_agent 🟢。源文档没明确把万物云 multi-agent 归类到官方 5 种哪一种，所以"Custom workflow"是推断，面试时按真实讲、被追问就口述"基于 StateGraph + interrupt_before + create_agent 推断"。

为什么不用官方另两种主流模式：

| 候选 | 机制 | 为啥万物云不用 |
|---|---|---|
| **Subagents（=老 Supervisor）** 🟢 | 主 agent 把子 agent 包成 `@tool`，主 agent 自己 LLM 动态决定调谁 | 主 agent 是"完整 agent + LLM 调度"，调度本身耗 LLM 调用且不可控。万物云业务流程是**确定性编排**（先分类→查单→分析→报告），要硬路由不要 LLM 临场决策 |
| **Handoffs（middleware）** 🟢 | 单 agent + middleware，靠 `current_step` state 变量驱动配置切换 | 是"一个 agent 切配置"，不是真多 agent。万物云要的是不同节点装不同 agent（chat_agent / query_agent / refund_node），节点职责彻底隔离 |
| **Custom workflow（StateGraph）** 🟢 万物云用 | 图结构完全自控，节点可以是函数/LLM/agent/子图，条件边硬路由 | 业务流程确定性 + 关键节点插人工审核（interrupt_before）+ 混合确定性和 agentic 节点，StateGraph 直接定义节点边最可控 |

一句话：**Subagents/Handoffs 是"让 LLM 当调度员"，万物云要"让图当调度员"**——路由逻辑写在条件边里是硬的、可测的、不烧 token 的。

> 官方提醒 🟢："not every complex task requires this approach - a single agent with the right tools and prompt can often achieve similar results." 别为了 multi-agent 而 multi-agent。万物云上 multi-agent 是因为单 agent 上下文杂（既查订单又写 SQL 又生成报告，工具多、system prompt 臃肿，LLM 选错工具）。

### 1.2 生产伪代码：StateGraph 骨架（add_node / add_edge / add_conditional_edges / compile）

万物云客服场景：用户消息进来 → 分类节点判意图 → 条件路由到 chat_agent / query_agent / refund_node → 退款节点前 interrupt_before 暂停等人工审核。

```python
from typing import TypedDict, Annotated
from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver   # 🔴 待确认：PostgresSaver 还是 RedisSaver
from langgraph.graph.message import add_messages

# ---- 1. State：类型化流程变量（跨节点共享 + checkpointer 持久化）----
class ServiceState(TypedDict):
    messages: Annotated[list, add_messages]   # 对话历史（短期记忆，自动合并）
    intent: str            # 当前阶段：业务查询 / 闲聊 / 退款
    user_id: str           # 记忆引用：拉长期记忆（Store）用
    review_status: str     # 审核状态：pending / approved / rejected

# ---- 2. 节点：4 种皆可（确定性函数 / LLM / agent / 子图）----
def classify(state: ServiceState) -> dict:                       # 确定性分类节点
    intent = llm_classify(state["messages"][-1].content)         # LLM 分类，但路由是硬的
    return {"intent": intent}

chat_agent  = create_agent(model=chat_model,  tools=chat_tools,  system_prompt="你是万物云客服...")
query_agent = create_agent(model=query_model, tools=query_tools, system_prompt="你是万物云客服...")  # tool_choice=required 防不查就编

def chat_node(state):   return chat_agent.invoke({"messages": state["messages"]})
def query_node(state):  return query_agent.invoke({"messages": state["messages"]})
def refund_node(state): ...                                       # 高风险退款（interrupt_before 拦截）

# ---- 3. 条件路由：add_conditional_edges（= Activiti 条件网关）----
def route_intent(state: ServiceState) -> str:
    if state["intent"] == "业务查询":  return "query_node"
    if state["intent"] == "退款":     return "refund_node"
    return "chat_node"

# ---- 4. 编译成图：挂 checkpointer + interrupt_before ----
builder = StateGraph(ServiceState)
builder.add_node("classify",   classify)
builder.add_node("chat_node",  chat_node)
builder.add_node("query_node", query_agent)        # agent 直接当节点也行
builder.add_node("refund_node", refund_node)

builder.add_edge(START, "classify")
builder.add_conditional_edges(                                    # 条件网关：按 intent 硬路由
    "classify", route_intent,
    {"chat_node": "chat_node", "query_node": "query_node", "refund_node": "refund_node"},
)
builder.add_edge("chat_node",   END)
builder.add_edge("query_node",  END)
builder.add_edge("refund_node", END)

checkpointer = AsyncPostgresSaver.from_conn_string(DB_URL)       # 🔴 待确认后端
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["refund_node"],    # 退款节点执行前暂停，等人工审核
)
```

### 1.3 逐行解释

1. `ServiceState(TypedDict)` — 类型化流程变量。`messages` 用 `Annotated[list, add_messages]` 表示自动合并（新消息追加而非覆盖），其余字段（intent/user_id/review_status）是自定义流程变量。🟢 LangGraph 标准写法。
2. `classify` 节点 — 确定性分类（虽然内部调 LLM 分类，但路由决策不在 LLM 手里，在条件边里）。类比 Activiti 的脚本任务。
3. `chat_agent` / `query_agent = create_agent(...)` — 两个独立 agent，各自 prompt + tools 精简隔离。`query_model` 用 `tool_choice="required"` 强制首轮必须调查询工具防幻觉 🟢（万物云防幻觉硬手段）。
4. `chat_node` / `query_node` — 把 agent 包成节点函数（node 里调 `agent.invoke`）。🟢 官方："可以在任何 LangGraph node 里直接调 LangChain agent"。
5. `route_intent(state)` — 条件路由函数，读 state 返回下一节点名。**这是硬路由，不耗 LLM 调用**。
6. `builder.add_conditional_edges("classify", route_intent, {...})` — 把 classify 节点的出口接成条件网关，按 route_intent 返回值走对应边。🟢 这就是万物云 multi-agent 路由的主要机制。**是否同时用 `Command(goto=...)` 做路由 🔴待核**（honesty 边界：主要用条件边已确认，Command(goto) 是否用没确认，不编）。
7. `builder.compile(checkpointer=..., interrupt_before=["refund_node"])` — 编译成可执行图。checkpointer 让 state 跨 turn 持久化；interrupt_before 在 refund_node 执行前打静态断点 🟢（万物云 HITL 用 interrupt_before，honesty 边界 #5）。

### 1.4 后端类比（Activiti 流程图 / 条件网关）

| 万物云 StateGraph | Activiti / Spring |
|---|---|
| `StateGraph(State)` 建图 | `<process>` 定义流程图 |
| `add_node("classify", fn)` | 节点 = serviceTask / scriptTask |
| `add_edge(START, "classify")` | sequenceFlow 连线 |
| `add_conditional_edges(..., route_intent, {...})` | `<exclusiveGateway>` 条件网关 + 条件表达式 |
| `compile()` | 流程定义部署到引擎 |
| 节点函数读 state / return 更新 state | 节点读/写流程变量（`execution.setVariable`） |
| `interrupt_before=["refund_node"]` | userTask 前暂停等审批（流程跑到 userTask 挂起） |
| agent 节点（create_agent） | 智能任务节点（调外部 AI 服务） |

一句话：**万物云 multi-agent = Activiti 自定义工作流引擎，节点可以是普通函数/LLM/agent/子图，条件边当条件网关，人工审核节点当 userTask**。🟡 后端类比（非官方）。

### 1.5 检查题

1. 万物云 multi-agent 用官方 5 种模式的哪一种？为什么不用 Subagents（Supervisor）？
2. `add_conditional_edges` 和 `Command(goto=...)` 都能路由，万物云主要用哪个？另一个是否用了？（注意 🔴待核项怎么诚实答）
3. 一个 LangGraph node 可以是哪 4 种？万物云客服图里 classify / query_agent / refund_node 各属哪种？
4. 万物云用 interrupt_before 做人工审核，官方现在主推哪个 HITL 机制？面试怎么说才不显得老？

---

## 2. 万物云 State + Checkpointer：跨 turn 状态管理与恢复

### 2.1 State：类型化流程变量（4 类字段）

万物云的 State 是 `TypedDict`，所有节点读写**同一个 State 对象**，这是图级编排"状态怎么共享"的核心——不是消息传递，是共享内存。字段分 4 类（对应任务要求的 messages/当前阶段/记忆引用/审核状态）：

| 字段类 | 例子 | 作用 | 后端类比 |
|---|---|---|---|
| **messages（短期记忆）** | `messages: Annotated[list, add_messages]` | 当前会话对话历史，LLM 看的 | HttpSession 内存里的会话数据 |
| **当前阶段** | `intent: str` / `current_step: str` | 标记流程走到哪、驱动条件路由 | 流程变量 `intent`（条件网关读它路由） |
| **记忆引用** | `user_id: str` | 拉 long-term memory（Store/pgvector）的钥匙 | 用户画像表的 userId 外键 |
| **审核状态** | `review_status: str` | interrupt 暂停后记录人工决策结果 | userTask 的审批结果变量 |

关键点：**State 不是只给 LLM 看的对话历史，是整个图的流程变量**。messages 只是其中一个字段。🟢 这是 LangGraph 和"纯 ReAct agent"的本质区别——ReAct agent 只有 messages，StateGraph agent 有任意自定义流程变量。

### 2.2 Checkpointer：持久化（PostgresSaver🔴 / Redis🔴 待确认）

Checkpointer 不是万物云自研概念，是 LangGraph 的内置持久化机制 🟢。机制：

- 每个 thread（会话）一个 `thread_id`（= JSESSIONID）
- 图**每跑完一个节点（super-step）就存一次 checkpoint**（版本化快照，含完整 state：messages + intent + review_status 全部）
- 下次用同一个 `thread_id` 拉，恢复到上次 state

```
thread_id="user_张三_session_1"
  ├─ checkpoint v1: {messages:[H1], intent:"业务查询", review_status:null}   # classify 跑完
  ├─ checkpoint v2: {messages:[H1,A1], intent:"退款", review_status:null}    # 路由到 refund_node 前
  └─ checkpoint v3: {messages:[...], intent:"退款", review_status:"approved"} # 人工批准后
```

**后端实现 🔴待确认**：LangGraph 支持 `AsyncPostgresSaver` / `RedisSaver` / 自研。万物云具体用哪个**没确认，不编**——面试按"honesty 边界 #8"答："checkpointer 后端我们用了持久化方案（PostgresSaver 或 RedisSaver），具体哪个我确认下再回你"，别瞎称 PostgresSaver 否则被表结构追问翻车。

> 生产坑 🟢：`InMemorySaver` 多实例部署拉不回（请求打到不同实例），C 端生产必须用 `AsyncPostgresSaver`（state 共享存 Postgres）。这是万物云自托管 StateGraph 必踩的坑——状态共享用 Postgres、并发保护自己加 Redis 锁（**不说框架白送**，honesty 边界：double-texting 并发锁是万物云自建 Redis 锁 🔴推断）。

### 2.3 跨 turn 恢复机制（interrupt_before + Command(resume=)）

万物云高风险操作（退款、改价、改权限）的完整恢复流程，**两次 HTTP 往返，不是一次连接挂着** 🟢：

**第 1 次往返（发起 + 暂停）**：
```python
# 前端: POST /chat { message: "帮我退款 ORD-001", thread_id: "abc123" }
result = graph.invoke(
    {"messages": [{"role": "user", "content": "帮我退款 ORD-001"}]},
    config={"configurable": {"thread_id": "abc123"}},   # thread_id = 会话钥匙
)
# agent 跑：classify -> 路由到 refund_node -> interrupt_before 暂停
# state 存 checkpointer（key=thread_id），invoke 返回，HTTP 连接断
# result 带暂停信息：refund_node 想执行，等审核
```

**第 2 次往返（resume）**：
```python
# 前端: 人工点"批准" -> POST /resume { thread_id: "abc123", decision: "approve" }
result = graph.invoke(
    Command(resume={"decision": "approve"}),            # 唯一能作 invoke 输入的 Command 🟢
    config={"configurable": {"thread_id": "abc123"}},   # 同一个 thread_id 拉回 state
)
# 框架用 thread_id 从 checkpointer 拉回暂停时的 state
# 注入决策 -> 执行 refund_node -> 继续跑 -> 完成
```

关键三点 🟢：
1. **`Command(resume=...)` 是唯一能作 `invoke()` 输入的 Command**。另外两个（`Command(goto=)` / `Command(update=)`）是节点函数 return 用的，别混。
2. **resume 不"goto"任何节点**——它恢复暂停的节点从头重跑（interrupt 前的代码会再跑一遍，别放副作用代码或做幂等）。
3. **HTTP 连接断了不影响**——state 不在连接里、不在进程内存里，在 checkpointer 后端。第一个 invoke 返回后连接关闭，state 还在 checkpointer 里，key=thread_id。人工可以想 5 分钟、第二天再批准都行（只要 checkpoint 那行没被 TTL 清）。

### 2.4 后端类比（流程变量落 ACT_RU_VARIABLE）

| 万物云 StateGraph | Activiti / Spring |
|---|---|
| `ServiceState` TypedDict | 流程变量集合 |
| 节点 return `{"intent": ...}` 更新 state | `execution.setVariable("intent", ...)` |
| state 存 checkpointer（thread_id + 版本） | 流程变量落 `ACT_RU_VARIABLE` 表（按 processInstanceId） |
| `thread_id` | `processInstanceId` |
| checkpoint 版本 v1/v2/v3 | Activiti 历史变量表 `ACT_HI_VARINST`（每次变更留痕） |
| interrupt_before 暂停 | 流程跑到 userTask 挂起，存 DB，HTTP 早返回 |
| `Command(resume=)` + 同 thread_id | 审批人 complete task，引擎按 processInstanceId 拉回继续 |
| checkpointer 后端 Postgres/Redis 🔴 | Activiti 数据源（MySQL/Postgres） |

一句话：**万物云 State + Checkpointer = Activiti 流程变量 + 流程持久化**。state 是流程变量，checkpointer 是流程引擎的持久化层，thread_id 是 processInstanceId，interrupt_before 是 userTask 挂起，Command(resume=) 是 complete task。🟡 后端类比。

### 2.5 检查题

1. 万物云 State 有哪 4 类字段？为什么说 State 不是只给 LLM 看的对话历史？
2. checkpointer 什么时候存？是只在 interrupt 时存吗？（接"游戏每过一关自动存档"的比喻）
3. `Command(resume=...)` 和 `Command(goto=...)` / `Command(update=...)` 有什么本质区别？哪个能作 invoke 输入？
4. 万物云 checkpointer 后端是 PostgresSaver 还是 Redis？（注意 🔴待确认怎么诚实答，被表结构追问怎么办）
5. 跨 turn 恢复为什么"两次 HTTP 往返"能接上？thread_id 在这里扮演什么角色？

---

## 3. 对标 pi：进程级 orchestrator vs 图级 StateGraph

### 3.1 pi-orchestrator 是实验性 stub（🟢 已读）

读 `pi-orchestrator` README（`C:\Users\admin\.claude\jobs\cbe4f308\tmp\pi\readme_orchestrator.md`）：**整个包 README 只有 3 行有效内容**——"Experimental. This package is under active development and may change or be removed without notice... Orchestrator package for pi." + 一个 `orchestrator --help` CLI 提示。

🟢 已确认：pi-orchestrator 是**实验性包，README 是 stub，没暴露 supervisor.ts / rpc-process / ipc / storage 的 API 细节**。任务里提到的"supervisor.ts 进程级编排"在 orchestrator README 里**找不到对应文档**——不编。

但 pi 的"多 agent / 多进程编排"实际机制能从其他 README 提炼（🟢 已读）：

| pi 编排三件套 | 来源 README | 机制 |
|---|---|---|
| **多进程 spawn** | coding-agent README | 明确哲学 "**No sub-agents**. Spawn pi instances via tmux, or build your own with extensions" |
| **IPC（进程间通信）** | coding-agent README | RPC mode："`pi --mode rpc` uses strict LF-delimited JSONL framing" over stdin/stdout |
| **storage（状态持久化）** | agent-core README + coding-agent README | session = JSONL 文件（tree 结构，每条 `id` + `parentId`），存 `~/.pi/agent/sessions/` |

所以 pi 的"orchestrator"不是图，是**进程级编排**：多个独立 pi 进程，每个进程内一个 AgentState，靠 RPC（stdin/stdout JSONL）通信，靠 JSONL session 文件持久化。这和万物云的图级编排是**两个范式**。

### 3.2 pi-agent-core 的 state management（🟢 已读）

pi 单 agent 的 state 是**进程内对象**，直接赋值改（`pi\readme_agent.md`）：

```typescript
interface AgentState {
  systemPrompt: string;
  model: Model<any>;
  thinkingLevel: ThinkingLevel;
  tools: AgentTool<any>[];
  messages: AgentMessage[];            // 对话历史（= 万物云的 messages 字段）
  readonly isStreaming: boolean;
  readonly streamingMessage?: AgentMessage;
  readonly pendingToolCalls: ReadonlySet<string>;
  readonly errorMessage?: string;
}

// 状态管理：直接赋值
agent.state.systemPrompt = "New prompt";
agent.state.messages = newMessages;     // 顶层数组被 copy 一份存
agent.state.messages.push(message);
agent.reset();
```

关键差异点 🟢：
1. **无 thread_id / checkpoint 版本概念**——pi 的 state 是单进程对象，没有"版本化快照"。
2. **持久化靠 JSONL session 文件**（tree 结构 `id`/`parentId`），不是 DB checkpoint。`/resume` 命令浏览历史 session 选一个加载。
3. **无共享 state**——每个 pi 进程独立 AgentState，进程间靠 RPC 消息传，没有万物云那种"所有节点读写同一个 State"。
4. **steering / follow-up 是进程内消息队列**（`steeringMode` / `followUpMode`），是单 agent 内的打断/排队，不是跨 agent 协作。
5. **transformContext + convertToLlm**：pi 在调 LLM 前做消息裁剪/转换（prune old / 注入外部 context / 过滤 UI-only 消息）。这是 pi 的"上下文管理"，对应万物云的上下文工程（摘要/卸载），但机制是消息流转换不是图节点。

### 3.3 pi 的"多 agent"实际靠 RPC + tmux + extension（🟢）

pi 明确**不内置 sub-agents**（coding-agent README Philosophy 节 🟢）：

> "No sub-agents. There's many ways to do this. Spawn pi instances via tmux, or build your own with extensions, or install a package that does it your way."

这意味着 pi 把"多 agent 怎么协作"**完全甩给用户**：
- 想要多 agent？**开多个 pi 进程**（tmux 窗口），各自独立 AgentState
- 想让它们通信？**用 RPC mode**（`pi --mode rpc`，stdin/stdout JSONL），外层程序读 RPC 事件流做调度
- 想要 supervisor 调度逻辑？**写 extension**（TypeScript 模块，注册 tool/command/handler）或装第三方 pi package
- 想要共享状态？**没有**——各进程独立 state，靠 RPC 消息传字符串

这是 pi 的设计哲学（honesty 边界 #13：pi 是 coding agent 工具链，万物云是业务 agent 平台，对标是架构思想对标不是代码移植）。pi 认为"sub-agents 怎么做没有唯一正解，不强行规定"，万物云认为"业务流程要确定性编排，必须图引擎兜底"。

### 3.4 检查题

1. pi-orchestrator 包的 README 有多少有效内容？（注意别把"supervisor.ts"说成已确认）
2. pi 的 state management 用什么数据结构？和万物云的 State + Checkpointer 有什么本质区别？
3. pi 怎么实现"多 agent 协作"？为什么说 pi 是进程级编排、万物云是图级编排？
4. pi 明确不内置什么？（Philosophy 节）这和万物云的选型反映了什么设计哲学差异？

---

## 4. 对比表

### 4.1 编排维度：万物云图级 StateGraph vs pi 进程级 orchestrator

| 维度 | 万物云（图级 StateGraph） | pi（进程级 orchestrator） |
|---|---|---|
| **编排单元** | 节点（node = 函数/LLM/agent/子图） | 进程（一个 pi 实例 = 一个 AgentState） |
| **路由机制** | `add_conditional_edges` 条件边硬路由 🟢（是否用 Command(goto) 🔴待核） | 无内置路由，靠 extension/RPC 外层程序调度 🟢 |
| **协作方式** | 共享 State（所有节点读写同一个 TypedDict） | RPC 消息（stdin/stdout JSONL），无共享 state 🟢 |
| **Supervisor 实现** | 不是标准 Subagents，是 Custom workflow：分类节点当调度 + 条件边路由 🔴推断 | 不内置，"No sub-agents"，靠 tmux spawn / extension 🟢 |
| **人工审核** | `interrupt_before` 静态断点 + `Command(resume=)` 🟢 | 无内置 HITL，靠 extension 自建 🟢（honesty 边界 #13） |
| **确定性 vs agentic** | 混合（确定性节点 + agentic 节点同图）🟢 | 单 agent 内 ReAct（transformContext + tool loop）🟢 |
| **后端类比** 🟡 | Activiti 自定义工作流引擎 | 多个独立 CLI 进程 + shell 脚本编排 |

### 4.2 状态维度：万物云 State+Checkpointer vs pi state management

| 维度 | 万物云（State + Checkpointer） | pi（AgentState + JSONL session） |
|---|---|---|
| **state 载体** | 类型化 `TypedDict`（messages + intent + user_id + review_status） | 进程内对象（systemPrompt/model/tools/messages/...）🟢 |
| **state 共享** | 图内所有节点共享同一个 State | 单进程私有，进程间不共享 🟢 |
| **持久化** | Checkpointer（thread_id + 版本化 checkpoint）🟢，后端 PostgresSaver🔴/Redis🔴待确认 | JSONL session 文件（tree，id/parentId）🟢，存 `~/.pi/agent/sessions/` |
| **恢复钥匙** | `thread_id`（= JSESSIONID / processInstanceId） | session 文件路径/UUID，`/resume` 命令选 🟢 |
| **版本化** | 有（每个 super-step 一个 checkpoint 版本）🟢 | 有（tree 结构，`/tree` 浏览分支，`/fork` 分叉）🟢 |
| **跨 turn 恢复** | `invoke(Command(resume=), config={thread_id})` 🟢 | `pi -c` / `pi -r` / `--session <id>` 加载历史 session 🟢 |
| **暂停-恢复** | interrupt_before 暂停 → Command(resume=) 恢复（同 thread_id）🟢 | steering（打断当前 turn）/ follow-up（排队）+ `/tree` 跳回任意点 🟢 |
| **上下文管理** | 上下文工程（摘要/卸载/Store 注入）作图节点 | transformContext（裁剪旧消息）+ convertToLlm（过滤）+ `/compact` 🟢 |
| **后端类比** 🟡 | HttpSession + session 持久化（Redis/DB） | 单机 CLI 工具的本地状态文件（如 vim 的 .swp + undo tree） |

---

## 5. 面试追问应答

### Q1：你的多 agent 怎么协作？状态怎么共享？

"万物云用 LangGraph StateGraph 做图级编排。多个 agent 各自是一个节点（create_agent 包成 node 函数），协作靠**共享 State**——一个类型化 TypedDict，所有节点读写同一个 State 对象，不是消息传递。比如 classify 节点把意图写进 `state["intent"]`，条件边读 intent 路由到 query_agent 或 refund_node，下游节点直接看到 intent 不用重新问。状态共享不需要 agent 之间发消息，是图引擎提供的共享内存。"

### Q2：Supervisor 模式怎么实现？

"我们不是标准 Subagents/Supervisor（主 agent 把子 agent 包 @tool、LLM 动态调度）。我们是 Custom workflow StateGraph 🔴推断——分类节点扮演类似 supervisor 的路由职责，但路由决策写在 `add_conditional_edges` 条件边里是硬的、确定性的，不让 LLM 临场决定调谁。原因是业务流程（先查单→分析→报告）是确定性编排，硬路由比 LLM 调度更可控、可测、省 token。面试补充：官方现在 Supervisor 是 Subagents 的别称，不是独立模式。"

### Q3：状态怎么持久化？跨 turn 怎么恢复？

"state 存 Checkpointer——LangGraph 内置的持久化机制，每个 thread 一个 thread_id，图每跑完一个节点存一个版本化 checkpoint。跨 turn 恢复用同一个 thread_id 拉。人工审核场景：refund_node 前 interrupt_before 暂停，state 存 checkpointer，HTTP 早返回；人工批准后第二次 invoke 传 `Command(resume={"decision":"approve"})` + 同一个 thread_id，框架从 checkpointer 拉回 state 继续。checkpointer 后端我们用了持久化方案（PostgresSaver 或 RedisSaver，具体我确认下）——InMemorySaver 多实例拉不回，C 端生产必须外部存储。"

### Q4：和 pi 的 orchestrator 比，你的方案有什么不同？

"pi 是**进程级编排**，万物云是**图级编排**，是两个范式。pi 明确不内置 sub-agents（它的 Philosophy 写 'No sub-agents, spawn pi instances via tmux'），多 agent 靠开多个 pi 进程 + RPC（stdin/stdout JSONL）+ extension 自建调度，各进程独立 AgentState、无共享 state、持久化靠 JSONL session 文件。万物云是单进程内 StateGraph，节点共享一个 State、条件边硬路由、checkpointer 持久化、interrupt_before 做人工审核。本质差异：pi 把'多 agent 怎么协作'甩给用户（coding agent 场景，流程不固定），万物云用图引擎兜底（业务场景，流程要确定性可控）。pi-orchestrator 包本身还是实验性的，README 是 stub。"

### Q5：为什么万物云不用 pi 那种进程级方案？

"场景不同。pi 是 coding agent，任务是探索性的（读写文件、跑命令），流程不固定，进程隔离 + 文件系统足够。万物云是业务 agent 平台（客服/IoT），业务流程是确定的（分类→查询→审核→执行），要硬路由 + 人工审核 + 共享流程变量 + 跨 turn 恢复，这些 StateGraph 开箱即用。进程级方案要自己写调度逻辑、自己管状态共享、自己做条件路由，等于重新造个图引擎。"

---

## 6. 万物云口径（按真实，不编）

**已确认 🟢**：
- 万物云用 LangGraph StateGraph（Python）做生产编排（honesty 边界 #1：口径"生产用 LangGraph"，遇"自研 vs 调包"追问口述"框架选型经原型验证"）
- multi-agent 路由主要用 `add_conditional_edges` 条件边
- 人工审核用 `interrupt_before`（静态断点），恢复用 `Command(resume=)`（honesty 边界 #5）
- 节点是 create_agent（混合确定性节点 + agentic 节点）
- recursion_limit 用框架自带（万物云=25），口径"用框架自带兜底并调了阈值"（honesty 边界 #4）

**🔴推断 / 🔴待核（不编，被追问口述）**：
- 万物云 multi-agent = Custom workflow（StateGraph）是 **🔴推断**，基于 StateGraph + interrupt_before + create_agent 三条已确认事实。被追问"怎么归类"口述："基于这三点推断为 Custom workflow，源文档没明确归类"。（honesty 边界 #6）
- checkpointer 后端是 PostgresSaver 还是 RedisSaver **🔴待确认**。面试答"用了持久化方案，具体我确认下"，别瞎称 PostgresSaver 否则被表结构追问翻车。（honesty 边界 #8）
- 是否同时用 `Command(goto=...)` 做路由 **🔴待核**。已确认主要用条件边，Command(goto) 没确认不编。（honesty 边界 #9）
- double-texting 并发锁是万物云自建 Redis 锁 **🔴推断**（Agent Server only 的功能，万物云自建）。（honesty 边界 #10）

**对标口径（honesty 边界 #13）**：
- pi 是 TypeScript coding agent 工具链（类 Claude Code，7.1万星），万物云是 Python 业务 agent 平台。对标是**架构思想对标不是代码移植**。
- pi 无内置 sub-agents（靠 tmux/extension/RPC）、无内置 HITL（靠 extension）、无 RAG（coding agent 用文件系统）、记忆靠 AGENTS.md 文件 + session-resources。
- 万物云有图级编排（StateGraph）、有 HITL（interrupt_before）、有 RAG（pgvector）、长期记忆 = pgvector + similar merge + TTL（honesty 边界 #2，NOT RedisStore / NOT AGENTS.md 文件式，Store 无内置 TTL 万物云自建 cron 🔴推断）。

---

## 7. 总检查题

1. 万物云 multi-agent 是图级还是进程级编排？和 pi 的根本范式差异是什么？（一句话答）
2. 万物云的"状态共享"靠什么机制？为什么不需要 agent 之间发消息？
3. `Command(resume=...)` 为什么能跨两次 HTTP 往返接上暂停的流程？thread_id 在其中起什么作用？
4. pi-orchestrator 包的真实状态是什么？（别把 supervisor.ts 说成已确认）pi 实际靠什么做"多 agent"？
5. 万物云 checkpointer 后端、是否用 Command(goto) 路由、multi-agent 归类——这三个 🔴 项面试怎么诚实答才不翻车？

> 答题口径：🟢 项直接答（已确认）；🔴 项按"honesty 边界"口述"推断依据 / 待确认"，不编。pi 对标只讲架构思想差异，不讲代码移植。

---

## 一、万物云长期记忆：pgvector + similar merge + TTL

> 一句话定位：跨会话/跨 thread 持久化的记忆，由 LangGraph **Store**（namespace+key 的 JSON 文档，可挂向量检索）承载；与"短期=checkpointer/上下文窗口"严格区分。万物云走**路径 A（LangGraph Store API）**，不用 Deep Agents 的 AGENTS.md 文件式记忆 🟢。

### 1.1 为什么是 pgvector（不是 RedisStore、不是 AGENTS.md）

先看 checkpointer 解决不了的三个痛点（这是长期记忆存在的根因）：

1. **用户换会话就失忆**：用户昨天在 thread-1 说"我偏好简洁回答"，今天开 thread-2，agent 又长篇大论。checkpointer 是 thread-scoped 的，`thread_id` 一换 checkpoint 完全隔离 🟢。用户偏好是**跨 thread**的，checkpointer 给不了。
2. **多用户/组织共享知识无处放**：运营给所有用户注入"公司合规政策"，难道每个 thread 都拷一份？这是"组织级"记忆，必须独立于任何 thread 🟢。
3. **纯向量召回不等于记忆**：光有 pgvector 召回没有**写入策略**（谁写、何时写、冲突怎么合并、过期怎么清），会退化成"记忆垃圾场"：重复/矛盾/过期/被污染的记忆全混在一起。万物云之所以明确做"similar merge + TTL"，正是因为光有 pgvector 召回不够 🟢（用户确认）/ 🔴（具体算法待核）。

万物云选 pgvector 的理由（🟢 用户确认用 pgvector / 🟡 后端常识补全）：

| 选型 | 为什么 | 来源 |
|---|---|---|
| **pgvector（Postgres 向量扩展）** | (1) 复用万物云已有的 Postgres 运维栈（备份/监控/主从一套熟）；(2) PostgresStore 官方支持向量检索，底层即 pgvector 🟡；(3) 一个库同时存结构化业务数据 + 向量，不用再引一个独立向量库（ES/Milvus）增加运维负担 | 🟢(万物云用 pgvector) 🟡(PostgresStore 用 pgvector 是后端常识，官方 fetched 页未点名) |
| **不用 RedisStore** | Redis 适合做短期/缓存（checkpointer 的 RedisSaver、并发锁），但长期记忆要持久 + 语义检索 + 可审计，Postgres 更稳；Redis 向量检索成熟度和生态不如 pgvector | 🟢 用户确认不用 RedisStore |
| **不用 Deep Agents AGENTS.md** | AGENTS.md 是"文件壳"——启动整份加载进 system prompt，记忆大了爆 token；万物云走 Store API 按需语义召回，省 token 且精准 | 🟢 用户确认不用 |

### 1.2 Store 的数据模型（先把抽象立住）

官方原话 🟢："LangGraph stores long-term memories as JSON documents in a store. Each memory is organized under a custom namespace (similar to a folder) and a distinct key (like a file name)."

```
namespace = ("user-123", "memories")   # 元组，类似文件夹路径
key       = "mem-001"                  # namespace 内唯一
value     = {"text": "用户喜欢简洁", "category": "preference"}  # dict
```

`Item` 对象 5 字段 🟢：`value`(dict)、`key`(str)、`namespace`(tuple)、`created_at`、`updated_at`。

官方 PostgresStore 的 SQL schema 🟢：
```sql
CREATE TABLE store_items (
  namespace   TEXT[] NOT NULL,
  key         TEXT NOT NULL,
  value       JSONB NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (namespace, key)
);
CREATE INDEX ON store_items USING gin(namespace);
-- pgvector 额外: 向量列 + ivfflat/hnsw 索引 🟡
```

**namespace 前缀匹配**是关键 🟢：`search(("user-123",))` 会返回 `("user-123",)`、`("user-123","memories")`、`("user-123","secrets")` 下所有 item。万物云按 user_id 隔离就靠这个 🔴（推断，基于路径 A 标准模式，万物云没明确说）。

### 1.3 similar merge 怎么做（语义去重合并）

核心思路：写一条记忆前，**先语义搜同 namespace 下有没有高度相似的**：
- 有（cosine 相似度 ≥ 阈值）→ **合并**（`put` 同 key 覆盖，把新事实并进原条目）
- 无 → **新建**（新 key）

为什么必须 merge 🟢：不 merge 的话，用户三次说"我喜欢简洁回答"，记忆库里就三条几乎一样的记忆，召回时 top-K 全被它们占满，反而把别的有用记忆挤掉——记忆库退化成垃圾场。

合并的具体算法（万物云确认有 similar merge 🟢，**具体合并算法/相似度阈值待核 🔴**，下面是通用实现思路）：
- 简化版：`merged_text = best.value["text"] + "\n---\n" + text`（直接拼接）
- 生产版：让 LLM 做语义合并（把旧 text + 新 text 喂给小模型，产出一条去重后的合并 text）🔴（万物云是否用 LLM 合并待核）

阈值 `SIM_THRESHOLD`：🔴 业务调参，官方无默认值。设高了同一条记忆被重复新建（漏合并），设低了不同记忆被错误合并（丢信息）。

### 1.4 TTL 自建 cron（Store 无内置过期）

关键事实 🟢：**LangGraph Store 没有内置 TTL 过期机制**。`created_at`/`updated_at` 只是时间戳字段，不会自动删数据。

官方对 checkpointer 明说 🟢："set a retention policy / cron job delete old"——Store 同理推断 🔴。所以万物云的 TTL 必须**自己跑 cron**：
- 每条记忆存自定义字段 `ttl_days`（如 30 天）
- cron 定时遍历所有 namespace，按 `updated_at + ttl_days` 判断过期，`delete` 过期条目
- 清理周期 🔴 待核（万物云具体 cron 周期未明确，不编）

为什么不内置 TTL 也要做 🟡：长期跑下来记忆库越来越大，检索变慢 + 召回 token 爆。TTL 清理 + similar merge 去重 + background consolidation 压缩，三者配合控膨胀。

### 1.5 生产伪代码（存/检索/合并/TTL）+ 逐行解释

**① 建 pgvector store**

```python
# ===== 1. 建 pgvector store（生产用 PostgresStore + 向量索引）=====
from langgraph.store.postgres import PostgresStore            # 官方生产后端 🟢
from langgraph.store.base import IndexConfig                  # 索引配置类型 🟢
from langchain.embeddings import init_embeddings              # embedding 工厂 🟢

DB_URI = "postgresql://app:***@pg:5432/agent?sslmode=require" # 生产连接串

def make_store():
    # PostgresStore.from_conn_string 内部会用 pgvector 扩展存向量
    # 🔴(官方页未点名 pgvector,但这是 Postgres 向量检索的唯一标准实现 🟡)
    with PostgresStore.from_conn_string(
        DB_URI,
        index=IndexConfig(
            embed=init_embeddings("openai:text-embedding-3-small"),  # embed 函数 🟢
            dims=1536,                                                # 必须和 embed 模型维度一致 🟢
            fields=["$"],                                             # "$" = 整个 value 都 embed 🟢
        ),
    ) as store:
        store.setup()   # 建表 + 建 GIN/向量索引,幂等 🟢
        return store

store = make_store()
```

逐行：
- `PostgresStore.from_conn_string`：用连接串建 store 实例，with 保证资源释放 🟢
- `index=IndexConfig(...)`：开启向量语义检索；不传 index 就是纯 KV store（只能 get/filter，不能 query 语义搜）🟢
- `embed`：把 text 转成向量的函数（这里用 OpenAI 的 embedding 模型）🟢
- `dims=1536`：embedding 向量维度，必须和 embed 模型输出维度一致，不一致建索引报错 🟢
- `fields=["$"]`：`"$"` 是 JSONPath，表示整个 value dict 都 embed；也可 `fields=["text"]` 只 embed 某字段 🟢
- `store.setup()`：建表 + 建索引，幂等（跑多次不报错），生产部署必调 🟢

**② 写记忆：带 similar merge**

```python
# ===== 2. 写记忆:带 similar merge(语义去重合并)=====
import uuid
from datetime import datetime, timezone

SIM_THRESHOLD = 0.92   # 相似度阈值,>=此值视为"同一条记忆"需合并
                     # 🔴(阈值是业务调参,官方无默认)

def write_memory(runtime, user_id: str, text: str, category: str):
    """
    写一条记忆。先语义搜同 namespace 下是否有高度相似的:
    - 有 -> 合并(update那条,把新事实并进去)
    - 无 -> 新建
    万物云"similar merge"的核心 🔴(万物云确认有 🟢,具体合并算法待核)
    """
    ns = (user_id, "memories")                       # user-scoped namespace 🟢
    # 2.1 语义检索:query=text,看有没有重复
    hits = runtime.store.search(
        ns,
        query=text,          # 走向量 cosine 召回 🟢
        filter={"category": category},  # 等值过滤,先按类别收窄 🟢
        limit=5,
    )
    # 2.2 按 score 找最相似的(score 越高越相似 🟢)
    best = max(hits, key=lambda it: getattr(it, "score", 0.0)) if hits else None
    if best and getattr(best, "score", 0.0) >= SIM_THRESHOLD:
        # 2.3 合并:把新 text 追加到原 value,更新 updated_at
        merged_text = best.value["text"] + "\n---\n" + text   # 简化:实际可让 LLM 做语义合并 🔴
        runtime.store.put(
            ns,
            best.key,                 # 用原 key -> 覆盖同一条 🟢(put 是 store or overwrite)
            {
                "text": merged_text,
                "category": category,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "ttl_days": 30,       # 自定义 TTL 字段(官方 store 无内置 TTL 🔴)
            },
            index=["text"],           # 只 embed text 字段 🟢
        )
        return "merged"
    else:
        # 2.4 新建
        runtime.store.put(
            ns,
            str(uuid.uuid4()),        # 新 key 🟢
            {
                "text": text,
                "category": category,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "ttl_days": 30,
            },
            index=["text"],
        )
        return "created"
```

逐行：
- `ns = (user_id, "memories")`：namespace 强制带 user_id，决定记忆隔离边界 🟢。**user_id 必须从 `runtime.context`/认证态取，绝不从用户消息里取**（防越权）🟢
- `runtime.store.search(ns, query=text, filter=..., limit=5)`：`query` 走向量语义召回，`filter` 走等值过滤，**两者可叠加** 🟢。先 filter 收窄类别，再语义搜，提高精度
- `max(hits, key=score)`：`search` 返回的 item 带 `score` 字段（cosine 相似度），取最高的 🟢
- `if best.score >= SIM_THRESHOLD`：超过阈值才合并，否则新建 🔴（阈值业务调参）
- `put(ns, best.key, {...})`：**用原 key 调 put = 覆盖同一条**，这就是 similar merge"更新原条目"的机制 🟢。put 是"store or overwrite"语义
- `merged_text = best.value["text"] + "\n---\n" + text`：简化版直接拼接 🔴；生产版应让 LLM 做语义合并去重
- `ttl_days: 30`：自定义 TTL 字段，官方 store 不认这个字段，是给自建 cron 用的 🔴
- `index=["text"]`：只 embed text 字段（category/时间戳不需要 embed）🟢
- 新建分支 `str(uuid.uuid4())`：新记忆用 UUID 当 key 🟢

**③ 读记忆：进对话前把相关记忆塞进 system prompt**

```python
# ===== 3. 读记忆:进入对话前把相关记忆塞进 system prompt =====
def recall_memory(runtime, user_id: str, current_query: str, top_k: int = 5):
    """
    用当前用户消息做 query,语义召回 top-K 相关记忆,拼进 system prompt。
    官方模式:node 里用 runtime.store.search 🟢
    """
    ns = (user_id, "memories")
    items = runtime.store.search(
        ns,
        query=current_query,          # 语义召回 🟢
        limit=top_k,
    )
    # 官方警告:别信默认排序,自己按 updated_at 排 🟢
    items = sorted(items, key=lambda it: it.value.get("updated_at",""), reverse=True)
    # 拼成 system prompt 片段
    memories_text = "\n".join(
        f"- [{it.value.get('category','?')}] {it.value['text']}" for it in items
    )
    return f"## 已知用户记忆\n{memories_text}" if memories_text else ""
```

逐行：
- `query=current_query`：用用户当前消息做语义查询，召回"和这次问题相关"的记忆，不是全量塞 🟢。这是"主动检索注入"——长期记忆不是自动进上下文，是每轮按需召回
- `limit=top_k`：只取 top-K，控制 token 🟢。注意 **limit 静默截断**（超 limit 的结果被丢，无 overflow 信号）🟢，top_k 要设大于预期上限
- `sorted(items, key=updated_at, reverse=True)`：**必须在应用层自己排** 🟢。InMemoryStore 按插入序、PostgresStore 按 updated_at 降序，跨后端不一致，官方明说"Do not rely on a specific order across implementations"
- 拼成 system prompt 片段：召回的记忆作为 system prompt 的一部分注入，模型这一轮就能看到

**④ TTL 清理：定时删过期记忆**

```python
# ===== 4. TTL 清理:定时删过期记忆(官方 store 无内置 TTL,自己跑 cron)=====
# 官方对 checkpointer 说"set a retention policy / cron job delete old" 🟢
# store 同理:靠 created_at/updated_at + 自定义 ttl_days 字段 🔴
def cleanup_expired(store):
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    # 4.1 列出所有 user namespace(前缀匹配所有用户 🟢)
    namespaces = store.list_namespaces(prefix=(), max_depth=2)  # ("user-xxx","memories")
    for ns in namespaces:
        if "memories" not in ns:
            continue
        # 4.2 该 namespace 下全量翻页 🟢(search 无 query=列举)
        offset = 0
        while True:
            page = store.search(ns, limit=100, offset=offset)   # 翻页 🟢
            if not page:
                break
            for it in page:
                ttl = it.value.get("ttl_days", 30)
                updated = datetime.fromisoformat(it.value["updated_at"])
                if now - updated > timedelta(days=ttl):
                    store.delete(ns, it.key)        # 过期就删 🟢
            offset += 100
```

逐行：
- `list_namespaces(prefix=(), max_depth=2)`：列出所有 namespace，前缀 `()` 匹配全部 🟢。万物云多用户场景下要遍历所有用户的 namespace
- `search(ns, limit=100, offset=offset)`：**search 不传 query = 纯列举**，用 offset 翻页 🟢
- `ttl = it.value.get("ttl_days", 30)`：取这条记忆的 TTL，默认 30 天 🔴（自定义字段，官方不认）
- `if now - updated > timedelta(days=ttl)`：判断过期——当前时间减去最后更新时间超过 ttl_days
- `store.delete(ns, it.key)`：过期就删 🟢。这整个函数挂在 cron 里定时跑（如每天凌晨）🔴（万物云具体 cron 周期待核）

**⑤ 接进 create_agent**

```python
# ===== 5. 接进 create_agent / StateGraph =====
from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from dataclasses import dataclass

@dataclass
class Ctx:
    user_id: str

@tool
def save_preference(preference: str, runtime: ToolRuntime[Ctx]) -> str:
    """把用户偏好存进长期记忆。"""
    return write_memory(runtime, runtime.context.user_id, preference, "preference")

agent = create_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[save_preference],
    store=store,                  # 注入 store,工具里 runtime.store 就能拿到 🟢
    context_schema=Ctx,
)

# 调用时带 user_id(决定记忆隔离边界)
agent.invoke(
    {"messages": [{"role":"user","content":"我以后回答都用中文,简洁点"}]},
    context=Ctx(user_id="user-123"),
)
```

逐行：
- `@dataclass Ctx`：上下文 schema，承载 user_id 🟢。user_id 从认证态来，不从消息来
- `@tool save_preference(..., runtime: ToolRuntime[Ctx])`：工具签名注入 `runtime`，工具内可拿 `runtime.store` 和 `runtime.context` 🟢
- `create_agent(..., store=store, context_schema=Ctx)`：store 注入 agent，工具里 `runtime.store` 就是这个实例 🟢
- `agent.invoke(..., context=Ctx(user_id="user-123"))`：调用时传 user_id，决定记忆隔离边界

### 1.6 后端类比表（长期记忆）

| Agent 长期记忆概念 | 后端类比（Spring/Activiti/Redis/JUC） | 说明 |
|---|---|---|
| **checkpointer（短期）** | Activiti `RuntimeService` 流程实例变量 + Redis session（按 sessionId） | 只在本次流程/会话内有效，换 thread = 换 sessionId，隔离 |
| **store（长期）** | MySQL `user_profile` 表 / Redis hash（key=user_id） | 跨 session 存在，用户下次登录还在 |
| **namespace 元组** | Redis key 前缀 `user:123:memories:*` / MySQL 分区键 | 层级隔离 + 前缀模糊检索 |
| **namespace 前缀匹配** | Redis `SCAN user:123:*` / MySQL `WHERE namespace LIKE 'user:123,%'` | 跨子命名空间召回 |
| **Item 的 key** | Redis hash 的 field / MySQL 主键 id | namespace 内唯一 |
| **Item 的 value(JSONB)** | MySQL JSON 列 / Redis hash 的 value(JSON 串) | 结构化但灵活 |
| **`created_at`/`updated_at`** | MySQL 审计字段 / Activiti 历史变量时间戳 | TTL 排序、冲突检测都靠它 |
| **语义检索（query + cosine）** | Elasticsearch dense_vector + cosine / pgvector | 按意思而非精确匹配召回 |
| **`index={embed,dims,fields}`** | ES 的 vector mapping + index_options | 决定哪些字段建向量索引 |
| **similar merge** | MySQL `INSERT ... ON DUPLICATE KEY UPDATE` + 版本合并 / Activiti 流程变量 merge | 相似就合并、不似就新建 |
| **TTL 清理 cron** | Redis `EXPIRE` / MySQL Event Scheduler 定时删 / Spring `@Scheduled` | 官方 store 无内置 TTL，等价于自己跑定时任务 |
| **background consolidation** | Spring Batch 定时 ETL 任务 / Activiti 定时服务任务 | 离线整理，避免 hot path 延迟 |
| **user-scoped namespace** | `@PreAuthorize` + `principal.id` 隔离 / MyBatis 拦截器加 user_id 条件 | 强制按用户隔离，防越权 |
| **read-only 记忆（防注入）** | Spring 只读 Repository / DB 用户只授 SELECT 权限 | 共享数据只读，写只能走应用代码 |
| **last-write-wins** | JUC `ConcurrentHashMap` 无锁 put / MySQL 无版本号的 UPDATE | 并发写冲突的默认语义，需乐观锁才能避免 |

### 1.7 生产坑（长期记忆）

| 坑 | 现象 | 对策 | 来源 |
|---|---|---|---|
| **记忆污染（prompt injection）** | 恶意用户往共享/组织级记忆写指令，毒化所有用户的 agent | org/agent-scoped 记忆设**只读**；user-scoped 默认隔离；写共享记忆前加 interrupt 人工审核 | 🟢 Deep Agents memory 页 |
| **并发写 last-write-wins** | 同一记忆被多 thread 并发改，后写覆盖前写 | user-scoped 罕见；agent/org-scoped 用 background consolidation 串行化 | 🟢 |
| **默认排序不稳** | InMemoryStore 插入序、PostgresStore updated_at 降序，跨后端不一致 | **永远在应用层按 `updated_at` 排序** | 🟢 |
| **limit 静默截断** | 超 limit 的结果被丢，**无 overflow 信号** | limit 设大于预期上限，或用 offset 分页 | 🟢 |
| **namespace 前缀误召回** | `search(("alice",))` 把 `("alice","memories")` 和 `("alice","secrets")` 全召回 | 要单层就传完整 namespace，或应用层按 `item.namespace` 过滤 | 🟢 |
| **召回率低/噪声大** | 向量召回 top-K 里一堆不相关 | 调 `SIM_THRESHOLD`；按 `filter` 先收窄类别再语义搜 | 🔴 业务调参 |
| **隐私泄露** | A 用户的记忆漏到 B 用户 | namespace 强制带 user_id，且 user_id 从认证态取，**绝不从用户消息取** | 🟢 |

---

## 二、万物云 Agentic RAG：三类节点编排

> 诚实边界先讲清：**三类节点（Model Rewrite / Deterministic Retrieve / Agent 决策）是 LangGraph 官方的 RAG 管线编排模式 🟢**。万物云客服 agent 检索订单/物流/工单知识时会用这种"确定性 + agentic 混合编排"思想 🔴（推断，基于万物云用 StateGraph + create_agent + interrupt_before）。而"Agentic RAG"作为完整模式（多跳检索/查询改写/低置信拒答，最多 3 跳）的深度生产经验属于**中建/斯维尔 RAG 项目（2025.12 起）** 🟢——这两个口径要分开讲，不能把中建的 Agentic RAG 经验说成万物云的。

### 2.1 三类节点（LangGraph 官方 RAG 管线）🟢

官方把 RAG 管线里的节点分三类，万物云客服 agent 的检索流就是这三类的混合：

| 节点类型 | 是什么 | 有没有 LLM | 后端类比 |
|---|---|---|---|
| **Model node（Rewrite）** | 用 LLM + structured output 重写 query 改善检索 | 有 LLM | Activiti 脚本任务（调外部智能服务） |
| **Deterministic node（Retrieve）** | 向量相似度搜索 / BM25 / 精确匹配，**无 LLM** | 无 LLM，纯算法 | Activiti 服务任务（确定性调用） |
| **Agent node（Agent）** | `create_agent` 对检索上下文推理，可经 tools 取额外信息 | 有 LLM + tools + 决策循环 | Activiti 智能任务（自主决策） |

关键认知 🟢：**不是所有节点都要 LLM**。Retrieve 是确定性的（同 query 同结果，可复现可测试），Rewrite 和 Agent 才调 LLM。把确定性的留确定性、该智能的才智能，是图编排的核心思想。

### 2.2 和朴素 RAG 的区别

| | 朴素 RAG（Naive RAG） | Agentic RAG |
|---|---|---|
| **流程** | 直线函数：query → 向量检索一次 → 拼 prompt → 生成 | 状态机：判断 → 检索 → 评估 → （改写重检）→ 生成/拒答 |
| **跳数** | 单跳 | 该跳才跳（多跳最多 3 跳护栏） |
| **证据评估** | 不管够不够都走完 | LLM 评估证据覆盖率 + 置信度，够了生成、不够改写重检、仍不足拒答 |
| **决策者** | 固定 pipeline 写死 | LLM 自主决定是否再检索/改写/停止 |
| **后端类比** | 一个顺序执行的 Service 方法 | 一个带条件分支/循环/兜底的 Activiti 流程 |

一句话 🟢：**朴素 RAG = `检索→生成` 的函数；Agentic RAG = `判断→检索→评估→(改写重检)→生成/拒答` 的状态机**。

注意（防极端）🟢：不是所有 RAG 问题都需要多跳。客服场景大量是单跳（"我的订单 ORD-001 到哪了"一跳就够），**该跳才跳**才是 Agentic；无脑每题 3 跳是固定 pipeline 的另一个极端（浪费 token、越召越散）。

### 2.3 生产伪代码（三类节点管线）

```python
# ===== 万物云客服 agent 的 RAG 管线（三类节点混合）=====
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain.agents import create_agent

class State(TypedDict):
    question: str            # 原始用户问题
    rewritten_query: str     # 重写后的检索 query
    documents: list[str]     # 召回的文档
    answer: str              # 最终答案

# ----- ① Model node: Rewrite（LLM 重写 query 改善检索）-----
def rewrite_query(state):
    """Model node: 用 LLM + structured output 重写 query。
    多轮追问时补全检索条件:用户问'那物流呢',要结合上一轮订单号重写成'订单 ORD-001 的物流状态'"""
    messages = [
        {"role":"system","content":"把用户问题改写成适合向量检索的 query。多轮追问要补全指代。输出 JSON: {rewritten_query: str}"},
        {"role":"user","content": state["question"]},
    ]
    result = small_llm.invoke(messages)        # 用小模型省成本 🟡
    return {"rewritten_query": result["rewritten_query"]}

# ----- ② Deterministic node: Retrieve（向量检索,无 LLM）-----
def retrieve(state):
    """Deterministic node: pgvector 向量召回 + BM25 全文检索 + RRF 融合。
    无 LLM,同 query 同结果,可复现可测试 🟢"""
    vec_hits = vector_store.similarity_search(state["rewritten_query"], k=5)
    bm25_hits = bm25_retriever.search(state["rewritten_query"], k=5)
    fused = rrf_merge(vec_hits, bm25_hits)     # RRF 融合多路召回 🟡
    reranked = reranker.rerank(state["rewritten_query"], fused, top_n=3)  # cross-encoder 重排 🟡
    return {"documents": reranked}

# ----- ③ Agent node: Agent（create_agent 推理 + tools + 决策）-----
def call_agent(state):
    """Agent node: create_agent 对检索上下文推理。
    评估证据覆盖率,够了生成,不够可调 retrieve_more tool 再检索(Agentic 决策)"""
    agent = create_agent(
        model="anthropic:claude-sonnet-4-6",
        tools=[retrieve_more_tool],            # 可主动再检索的 tool
        system_prompt=f"基于以下文档回答:{state['documents']}\n证据不足时调 retrieve_more 补充,仍不足说明并拒答。",
    )
    result = agent.invoke({"messages":[{"role":"user","content": state["question"]}]})
    return {"answer": result["messages"][-1].content}

# ----- 组图:三类节点用条件边/循环串成状态机 -----
workflow = (
    StateGraph(State)
    .add_node("rewrite", rewrite_query)        # Model node
    .add_node("retrieve", retrieve)            # Deterministic node
    .add_node("agent", call_agent)             # Agent node
    .add_edge(START, "rewrite")
    .add_edge("rewrite", "retrieve")
    .add_edge("retrieve", "agent")
    .add_edge("agent", END)
    .compile()
)
```

逐行：
- `class State(TypedDict)`：图状态，question→rewritten_query→documents→answer 流转 🟢
- `rewrite_query`（Model node）：用小模型重写 query，多轮追问补全指代（"那物流呢"→"订单 ORD-001 的物流状态"）🟡。用 structured output 保证输出格式
- `retrieve`（Deterministic node）：**无 LLM**，纯算法——pgvector 向量召回 + BM25 全文检索 + RRF 融合 + Rerank 重排 🟡。同 query 同结果，可复现可测试
- `call_agent`（Agent node）：`create_agent` 推理 + tools，可调 `retrieve_more_tool` 主动再检索（这是 Agentic 的决策点）🟢
- `add_edge(START,"rewrite").add_edge("rewrite","retrieve").add_edge("retrieve","agent").add_edge("agent",END)`：线性串起来 🟢。生产里 `agent` 节点可能用条件边回边到 `retrieve`（多跳），用 `recursion_limit` 兜底防死循环 🟡

### 2.4 万物云口径（诚实边界）

| 维度 | 口径 | 来源 |
|---|---|---|
| **三类节点编排思想** | 万物云客服 agent 检索订单/物流/工单时，用 StateGraph 混合确定性节点（检索）+ agentic 节点（create_agent）+ 人工审核节点（interrupt_before） | 🔴 推断（基于 StateGraph + create_agent + interrupt_before 已确认事实） |
| **RAG 是否完整 Agentic（多跳/改写/拒答）** | 万物云客服场景大量是单跳（查订单/物流），是否实现完整多跳+拒答待核 | 🔴 待核，不编 |
| **Agentic RAG 多跳3跳/拒答深度经验** | 属于中建/斯维尔 RAG 项目（2025.12 起），**不是万物云** | 🟢 简历与项目笔记确认 |
| **检索后端** | 万物云客服 agent 检索用 pgvector（与长期记忆同库不同表） | 🟡 推断（万物云用 pgvector 已确认，客服知识检索具体表结构待核） |

**面试口径（万物云 vs 中建分开讲）**：
- 讲万物云时："客服 agent 的检索流用 StateGraph 把重写、检索、agent 决策串成管线，检索用 pgvector。客服场景大量是单跳查询，agentic 决策主要用在工具选择和人工审核打断上。"
- 讲中建项目时（如果面试官问到 RAG 深度）："完整 Agentic RAG 的多跳检索/查询改写/低置信拒答（最多 3 跳）是我在中建 RAG 项目做的，那是知识检索平台，和万物云客服 agent 是两个项目。"

---

## 三、上下文工程（context engineering）

> Agent 工程生产化第一个硬核专题。LLM context window 有限（如 200K token），Agent 运行中上下文会**不断膨胀**（多轮对话累积 + 工具大输出 + 子 agent 中间过程），不管理 → 超限报错/超时/成本飙升/LLM 注意力分散质量下降。

### 3.1 Deep Agents 四层上下文管理 🟢

| 层 | 是啥 | 机制 | 万物云用没用 |
|---|---|---|---|
| 1. 输入上下文 | system prompt + 用户输入 + 历史 | 基础，所有 agent 都有 | 🟢 有 |
| 2. 压缩 | 摘要 / 卸载 | 摘要旧消息 / 大输出卸载 | 🟢 滑动窗口+摘要；🔴 卸载到文件没用（没用 Deep Agents） |
| 3. 隔离 | 子代理隔离 | subagent 干活不污染主上下文，只回最终结果 | 🟡 通用做法，万物云是否用 subagent 隔离待核 |
| 4. 长期记忆 | 跨会话 | AGENTS.md（Deep Agents）/ 外部 store（pgvector） | 🟢 pgvector（不是 AGENTS.md） |

### 3.2 模型每轮看到的 5 部分（常被漏算）

| # | 部分 | 后端类比 |
|---|---|---|
| 1 | System prompt（角色+规则） | web.xml 全局配置 |
| 2 | 历史 messages（Human/AI/Tool 交替） | 会话日志 |
| 3 | **工具定义**（tools 的 JSON schema） | API 网关每次带全量接口文档 |
| 4 | 检索结果（RAG 外部知识） | 动态查的缓存数据 |
| 5 | 长期记忆（Store 取回的用户画像） | Redis 里的用户画像 |

**重点坑 🟢**：工具定义也占 token，且**每轮都发**（因为 LLM 无状态，每次都得重读工具清单才知道有哪些工具可用）。一个工具约 100-150 token，万物云 12 个 Skill ≈ 1500-2000 token/轮，20 轮就 4 万 token 光花在工具定义上。这是最常被漏算的大头。

### 3.3 三种解法：裁剪 / 摘要 / 外移

| 解法 | 做法 | 后端类比 | 缺点 |
|---|---|---|---|
| **裁剪 Trimming** | 直接删旧消息，只留最近 N 轮 | LRU 缓存淘汰 / 日志只留最近 N 条 | 暴力，可能删关键信息 |
| **摘要 Summarization** | 用小模型把旧对话压成一段摘要，替换旧消息 | 日志滚动压缩归档 | 有损，丢细节 |
| **外移 Offloading** | 把信息存外部（向量库/DB/Store），上下文只留指针，需要时检索回来 | 冷热分离（热 Redis，冷 DB） | 最复杂 |

**裁剪不能单独用** 🟢：用户最早说的订单号被裁掉，后面模型问"订单号是什么"——用户体验崩。裁剪**必须配合摘要或外移**：关键事实（订单号、日期）不能靠裁剪，要么压进摘要，要么外移到 Store 结构化记忆（`order_id: ORD-xxx`，不是塞在自然语言摘要里）。

### 3.4 trim_messages 滑动窗口（裁剪）

```python
def trim_messages(messages, max_recent=20):
    if len(messages) > max_recent:
        old = messages[:-max_recent]
        summary = llm.summarize(old)            # 旧消息摘要
        return [SystemMessage(f"之前对话摘要：{summary}")] + messages[-max_recent:]
    return messages
# 或用 LangChain 的 trim_messages 工具,按 token 数裁 🟡
```

后端类比 🟡：日志滚动（保留最近 N 条 + 旧日志归档摘要）/ LRU 缓存淘汰。

### 3.5 摘要压缩（SummarizationMiddleware 累积摘要）🟢

这是上下文工程的核心机制，面试会被追问底层。万物云就用这个：对话超过阈值，旧消息自动替换成摘要。

**触发条件：按 token，不按轮数** 🟢。参数 `max_tokens_before_summary`：messages 总 token 超过这个值才触发。为什么按 token 不按轮数：一轮可能 50 token（"好的"）也可能 5000 token（一个长工具结果），按轮数不精确。

**内部 before_model 钩子做的事**（伪代码）：

```python
def before_model(self, state):
    messages = state["messages"]
    if count_tokens(messages) > self.max_tokens_before_summary:
        # 1. 分割:保留最近 messages_to_keep 条,其余(含上次的摘要消息)拿去重新摘
        keep = messages[-self.messages_to_keep:]
        old  = messages[:-self.messages_to_keep]   # old 里已含上次的摘要消息
        # 2. 重新摘成 1 条新摘要(替换掉 old 里所有内容,含旧摘要)
        new_summary = self.summary_model.invoke([
            SystemMessage("把以下内容压成一段摘要,保留关键事实..."),
            *old
        ])
        # 3. 替换:新摘要 + 保留的近期消息(始终只有 1 条摘要,不拼接不增长)
        state["messages"] = [new_summary] + keep
    return state
```

**累积摘要（running summary）4 个关键设计点** 🟢：
1. **累积摘要**：每次把【上次摘要 + 这批新原始消息】一起喂摘要模型，产出 1 条新摘要替换旧的。不是零失真（最老信息经多次摘要），但比"只摘上一次摘要"的 naive 做法失真更慢
2. **保留最近 N 条不摘要**（`messages_to_keep`）：近期对话原样保留，只压缩老的
3. **用独立小模型做摘要**：主模型贵，摘要用便宜小模型（gpt-4o-mini）
4. **放在 before_model 钩子**：每轮主模型调用前压缩，主模型看到的就是压缩后的

**4 个生产坑** 🟢：
1. 阈值设太低 → 频繁触发摘要，成本反增 + 失真快。万物云按窗口约 60-70% 设
2. 累积摘要久了丢早期关键事实 → 订单号外移到 Store
3. ToolMessage 被摘要成自然语言丢结构 → 重要工具结果外移
4. 摘要模型太弱 → 摘要质量差，主模型基于烂摘要回答更差

### 3.6 subagent 隔离（工具大输出不污染主上下文）🟡

痛点：搜索返回 10KB、读文件 50KB，全塞主上下文 → 撑爆。
对策：subagent 内部处理大输出，**只回最终结果**给主上下文。主 agent 看到的只是 subagent 返回的精简结论，不是它处理过程中的全部中间数据。

后端类比 🟡：大查询结果别全加载内存，分页或落临时表；或像 Spring 里把重活委托给一个 service，主流程只拿返回值。

万物云是否用 subagent 隔离 🔴 待核（不编）。

### 3.7 Checkpointer TTL（防 state 快照膨胀）🟢

痛点：每个 super-step 存一份 state 快照，长对话/多线程 → DB 膨胀。
对策 🟢：给 checkpoint 设 TTL 过期时间，定期清理。

在 `langgraph.json` 里配 checkpointer TTL：
```json
{
  "checkpointer": {
    "ttl": "7d"    // checkpoint 7 天后过期 🟢
  }
}
```

后端类比 🟡：Redis `EXPIRE` / Activiti History Cleanup Job / 流程引擎 `ACT_RU_EXECUTION` 表定期清已结束流程实例。

万物云确认配了 checkpointer TTL 🟢。

### 3.8 万物云上下文工程配方

每轮发给模型的 = **System prompt + 工具定义 + [旧对话摘要 + 最近几轮(含当前 query)]**。检索结果用完即丢（外移）。关键事实外移到 Store 长期记忆。这是三种解法的组合，不是单用一种 🟡。

**面试口径** 🟢："上下文管理我们用滑动窗口 + 摘要控制多轮消息（SummarizationMiddleware，按 token 触发累积摘要），工具大输出靠 subagent 隔离 🔴。长期记忆用 pgvector 向量检索 + 相似合并 + TTL 清理。checkpointer 配 TTL 防快照膨胀。没用 Deep Agents 的 AGENTS.md / 虚拟文件系统卸载，自己用 pgvector 实现。"

---

## 四、对标 pi：文件系统 + AGENTS.md 式记忆，无 RAG

> 诚实边界：pi 是 TypeScript coding agent 工具链（类 Claude Code，7.1万星），万物云是 Python 业务 agent 平台。对标是**架构思想对标**，不是代码移植。pi 无内置权限（靠容器 Gondolin/Docker/OpenShell）、无内置 HITL、无 RAG（coding agent 用文件系统）、记忆靠 AGENTS.md 文件 + session-resources。

### 4.1 pi 的"记忆"= 文件系统 + AGENTS.md + session JSONL

读 pi-agent-core 和 pi-coding-agent README 得出 🟢（本地已抓取）：

**① AGENTS.md / CLAUDE.md（项目指令，启动加载）** 🟢
- pi 启动时从 `~/.pi/agent/AGENTS.md`（全局）+ 父目录往上走 + 当前目录加载 AGENTS.md（或 CLAUDE.md）
- 所有匹配文件 **concatenated**（拼接），整份加载进 system prompt
- 用途：项目指令、约定、常用命令
- 可 `--no-context-files` / `-nc` 禁用
- 还能用 `.pi/SYSTEM.md` 替换默认 system prompt，`APPEND_SYSTEM.md` 追加

**关键对比 🟢**：这和 Deep Agents 的 AGENTS.md memory 机制一样——**启动整份加载进 system prompt**。pi 没有"按需语义召回"，记忆/指令是 always loaded 的。记忆大了就爆 token（pi 靠控制文件大小 + Compaction 解决，不靠语义检索）。

**② Sessions JSONL（会话级历史）** 🟢
- 会话存为 JSONL 文件，**树结构**（每条有 `id` + `parentId`，支持原地分支不建新文件）
- 自动存到 `~/.pi/agent/sessions/`，按工作目录组织
- `/resume` 选历史会话继续，`/tree` 跳到任意点继续，`/fork` 从某点分叉
- 这是会话级（类似 checkpointer），**不是跨会话语义检索长期记忆**

**③ session-resources（会话级资源）** 🟢
- 会话作用域的资源，会话结束就没了
- 不是跨会话持久记忆

**结论** 🟢：pi **没有 pgvector 式长期记忆**。pi 的"记忆"三层都是会话级或文件级：
- AGENTS.md = 启动加载的指令文件（类似配置文件）
- session JSONL = 会话历史（类似 checkpointer）
- session-resources = 会话级资源

没有任何一层是"跨会话、按需语义召回、带写入策略（合并/TTL）"的长期记忆。pi 不需要——coding agent 的"知识"就是文件系统，read 工具直接读，不需要语义检索历史对话。

### 4.2 pi 无 RAG（coding agent 直接读文件）🟢

pi 默认给模型 4 个工具：`read`、`write`、`edit`、`bash`（还有 `grep`、`find`、`ls`）。

**pi 不需要 RAG** 🟢：coding agent 的知识源就是当前仓库的文件，模型用 `read`/`grep`/`find` 工具直接读文件，文件系统就是"知识库"。不需要把文档 chunk + embed + 向量检索——那是给"非结构化知识库问答"用的（如施工规范、客服知识库），coding 场景知识已在文件里，直接读更准更快。

pi 官方哲学 🟢（README Philosophy 节）：
- **No MCP**：用 CLI 工具 + READMEs（Skills）或扩展加 MCP
- **No sub-agents**：通过 tmux spawn pi 实例，或扩展自建
- **No permission popups**：跑容器里，或扩展自建确认流
- **No plan mode**：写计划到文件，或扩展自建
- **No built-in to-dos**：用 TODO.md 文件

万物云哲学相反：业务 agent 需要权限（HITL interrupt_before）、需要长期记忆（用户画像跨会话）、需要 RAG（客服知识库语义检索）——因为这些业务场景文件系统解决不了。

### 4.3 pi 的上下文工程（transformContext + Compaction）

pi-agent-core 提供两个钩子管上下文 🟢：

**① transformContext（裁剪 + 注入）** 🟢
```typescript
// Agent Options
transformContext: async (messages, signal) => pruneOldMessages(messages),
```
- 在 `convertToLlm` 之前跑，用于裁剪旧消息、注入外部上下文
- 类比万物云的 trim_messages + Store 注入

**② convertToLlm（过滤自定义消息）** 🟢
- AgentMessage（含自定义类型）→ LLM Message（只认 user/assistant/toolResult）的桥接
- 过滤掉 UI-only 的自定义消息类型

**③ shouldStopAfterTurn（compact 前停）** 🟢
```typescript
shouldStopAfterTurn: async ({ message, toolResults, context, newMessages }) => {
    return shouldCompactBeforeNextTurn(context.messages);
},
```
- turn 结束后检查是否需要 compact，需要就停下让外部做压缩
- 类比 SummarizationMiddleware 的触发检查

**④ Compaction（摘要压缩，pi-coding-agent 核心）** 🟢
- **Manual**：`/compact` 或 `/compact <custom instructions>`
- **Automatic**：默认开启，context overflow 时触发（恢复并重试），或接近上限时主动触发
- 摘要旧消息 + 保留近期消息，**有损**
- 完整历史保留在 JSONL 文件里，用 `/tree` 重访
- 可通过扩展自定义 compaction 行为

**对比** 🟢：pi 的 Compaction 和万物云的 SummarizationMiddleware 是同一思想（摘要旧消息保留近期），都按 token 触发、有损、完整历史另存。差异是 pi 完整历史在 JSONL 文件，万物云在 checkpointer。

---

## 五、对比表

### 5.1 长期记忆：万物云 pgvector vs pi 文件系统/AGENTS.md

| 维度 | 万物云（pgvector + similar merge + TTL） | pi（AGENTS.md + session JSONL） |
|---|---|---|
| **记忆载体** | PostgresStore + pgvector 向量索引 🟢 | AGENTS.md 文件 + session JSONL 文件 🟢 |
| **抽象层级** | LangGraph Store API（路径 A，put/get/search）🟢 | 文件系统（read/write/edit 文件）🟢 |
| **加载方式** | 按需语义召回（每轮 query 召回 top-K 注入）🟢 | 启动整份加载进 system prompt（always loaded）🟢 |
| **跨会话** | 是（namespace 带 user_id，跨 thread）🟢 | AGENTS.md 跨会话（文件持久）；session JSONL 会话级 🟢 |
| **语义检索** | 有（cosine 相似度召回）🟢 | 无（文件靠 read/grep，精确匹配）🟢 |
| **写入策略** | similar merge（语义相似合并）+ TTL cron 🟢/🔴 | edit_file 工具改文件，last-write-wins 🟢 |
| **去重** | similar merge 语义去重 🟢/🔴 | 无自动去重，靠人维护文件 🟢 |
| **过期清理** | TTL cron 定时删 🔴 | 无（文件不会自动过期）🟢 |
| **token 控制** | 按需召回 top-K，省 token 🟢 | 整份加载，文件大了爆 token 🟢 |
| **适用场景** | 业务 agent（客服/知识库，跨会话用户画像） | coding agent（项目指令/约定，知识在文件里） |
| **后端类比** | MySQL user_profile 表 + Redis hash | Spring application.yml / @ConfigurationProperties |

### 5.2 RAG：万物云 Agentic RAG vs pi 无 RAG

| 维度 | 万物云（Agentic RAG 三类节点） | pi（无 RAG） |
|---|---|---|
| **知识源** | pgvector 向量库 + BM25 全文检索 🟢 | 文件系统（仓库文件）🟢 |
| **检索方式** | 向量语义召回 + 全文 + RRF 融合 + Rerank 🟡 | read/grep/find/ls 工具直接读 🟢 |
| **查询改写** | Model node（Rewrite）LLM 重写 query 🟢 | 无（模型自己决定 grep 什么）🟢 |
| **多跳检索** | Agentic 决策（中建项目最多 3 跳）🟢 | 模型自主多次调 read/grep（无显式跳数护栏）🟢 |
| **证据评估** | LLM 评估证据覆盖率 + 置信度，不足拒答 🟢（中建） | 模型自己判断（无显式拒答机制）🟢 |
| **三类节点** | Model/Deterministic/Agent 混合编排 🟢 | 无（agent 直接用 tools）🟢 |
| **为什么这样** | 业务知识非结构化（规范/工单），必须 embed 才能语义召回 | coding 知识就是文件，直接读更准更快 |
| **适用场景** | 客服/知识库/规范问答 | 代码仓库操作 |

---

## 六、面试追问应答

### Q1：万物云长期记忆怎么做的？为什么不用 Redis？

**答**：长期记忆用 pgvector + similar merge + TTL，跑在 LangGraph Store API 上 🟢。
- **pgvector**：复用万物云已有 Postgres 运维栈，一个库同时存结构化业务数据 + 向量；Redis 适合做短期缓存（checkpointer、并发锁），但长期记忆要持久 + 语义检索 + 可审计，Postgres 更稳，且 Redis 向量检索生态不如 pgvector 🟢/🟡。
- **similar merge**：写记忆前先语义搜同 namespace 下有没有高度相似的（cosine ≥ 阈值），有就合并（put 同 key 覆盖），无就新建。防止重复记忆占满召回 🟢/🔴（算法待核）。
- **TTL**：官方 Store 没有内置过期机制，自建 cron 按 `updated_at + ttl_days` 判断过期并 delete 🔴。

### Q2：为什么 TTL 必须自己实现？官方 Store 不是有 created_at/updated_at 吗？

**答**：`created_at`/`updated_at` 只是时间戳字段，不会自动删数据 🟢。官方 Store 没有内置 TTL 过期机制，官方只对 checkpointer 明说"set a retention policy / cron job delete old"，Store 同理推断 🔴。所以 TTL 必须自己跑 cron：每条记忆存自定义 `ttl_days` 字段，cron 定时遍历 namespace，按 `updated_at + ttl_days` 判断过期并 `delete`。

### Q3：similar merge 具体怎么合并？阈值怎么定？

**答**：写记忆前先 `store.search(ns, query=text, filter={category}, limit=5)` 语义搜相似，取 score 最高的；若 `score >= SIM_THRESHOLD`（如 0.92）就合并——用原 key 调 `put` 覆盖（put 是 store or overwrite 语义），把新 text 并进原 value 🟢。合并具体算法简化版是拼接，生产版可让 LLM 做语义合并去重 🔴（万物云具体用哪个待核）。阈值是业务调参，设高了漏合并（重复记忆），设低了误合并（丢信息），要在 golden set 上调 🟡。

### Q4：checkpointer 和 store 有什么区别？用户跨会话的偏好存哪？

**答** 🟢：
- **checkpointer**：thread-scoped，存单个 thread 的 graph state 快照（含 messages），靠 `thread_id` 续接。换 thread 就隔离。
- **store**：cross-thread，存从对话里提炼出的、要带去下次对话的东西（用户偏好/画像），namespace + key 的 JSON 文档，可挂向量检索。

用户跨会话偏好（如"我对花生过敏"）必须存 store（namespace 带 user_id），下次会话用当前消息做 query 语义召回塞进 system prompt。checkpointer 给不了跨 thread 能力。

### Q5：Agentic RAG 和朴素 RAG 区别？万物云的 RAG 是 Agentic 吗？

**答** 🟢：朴素 RAG = `检索→生成` 直线函数，单跳，不管证据够不够都走完；Agentic RAG = `判断→检索→评估→(改写重检)→生成/拒答` 状态机，LLM 自主决定是否再检索/改写/停止。

**万物云口径**（诚实）：万物云客服 agent 的检索流用 StateGraph 把 Rewrite（Model node）、Retrieve（Deterministic node）、Agent 决策串成三类节点管线 🔴（推断）。但客服场景大量是单跳（查订单/物流），完整 Agentic RAG 的多跳3跳/查询改写/低置信拒答深度经验是我在**中建 RAG 项目**做的，那是知识检索平台，和万物云客服 agent 是两个项目 🟢。

### Q6：上下文工程怎么做？工具定义也占 token 吗？

**答** 🟢：上下文工程管模型每轮看到的 5 部分（System prompt + 历史 messages + 工具定义 + 检索结果 + 长期记忆）。工具定义**每轮都发**（LLM 无状态，每次得重读工具清单），一个工具约 100-150 token，12 个 Skill ≈ 2000 token/轮，是最常被漏算的大头。

万物云配方：滑动窗口 + 摘要（SummarizationMiddleware，按 token 触发累积摘要，用小模型）控制多轮消息；工具大输出靠 subagent 隔离 🔴；检索结果用完即丢（外移）；关键事实外移到 Store；checkpointer 配 TTL 防快照膨胀 🟢。没用 Deep Agents 的 AGENTS.md / 虚拟文件系统卸载。

### Q7：SummarizationMiddleware 底层怎么实现？为什么用累积摘要？

**答** 🟢：放在 before_model 钩子，每轮主模型调用前检查。按 token 触发（不按轮数，因为一轮可能 50 也可能 5000 token）。触发时保留最近 `messages_to_keep` 条，其余（含上次摘要）一起喂小模型重新摘成 1 条新摘要替换旧的。累积摘要：每次【上次摘要 + 这批新原始消息】一起摘，产出 1 条替换旧的——新原始消息是第一次被摘全保真，只有最老尾巴多次摘，比"只摘上一次摘要"失真更慢。用独立小模型省成本。

### Q8：和 pi 比，万物云的记忆和 RAG 有什么不同？

**答** 🟢：
- **记忆**：pi 用 AGENTS.md 文件 + session JSONL，启动整份加载进 system prompt（always loaded），无跨会话语义检索，无 similar merge，无 TTL。万物云用 pgvector Store，按需语义召回 top-K 省 token，similar merge 去重，TTL cron 清理。差异根因：pi 是 coding agent，知识就是文件，read 直接读；万物云是业务 agent，用户画像/客服知识要跨会话语义检索。
- **RAG**：pi 无 RAG，模型用 read/grep/find 直接读文件系统。万物云用三类节点管线（Rewrite/Retrieve/Agent），pgvector 向量召回 + BM25 + RRF + Rerank。差异根因：coding 知识在文件里直接读更准；业务知识非结构化（规范/工单），必须 embed 才能语义召回。

---

## 七、万物云口径汇总（三色标注，没明确说的标🔴不编）

| 维度 | 万物云口径 | 来源 |
|---|---|---|
| **长期记忆实现** | pgvector + similar merge + TTL | 🟢 用户确认 |
| **底层框架** | StateGraph + create_agent（不是 Deep Agents） | 🟢 用户确认 |
| **记忆抽象** | LangGraph Store API（路径 A），不用 AGENTS.md / 虚拟文件系统 | 🟢 用户确认 |
| **存储后端** | pgvector（Postgres 向量扩展） | 🟢(万物云用 pgvector) 🟡(PostgresStore 用 pgvector 是后端常识，官方未点名) |
| **similar merge** | 有此机制（语义相似则合并、否则新建） | 🟢 用户确认 / 🔴 具体合并算法、相似度阈值待核 |
| **TTL** | 有此机制（记忆过期清理） | 🟢 用户确认 / 🔴 官方 store 无内置 TTL，万物云具体实现（cron 字段/清理周期）待核 |
| **不用 RedisStore** | 明确不用 | 🟢 用户确认 |
| **不用 Deep Agents AGENTS.md** | 明确不用 | 🟢 用户确认 |
| **记忆隔离** | 按 user_id namespace 隔离 | 🔴 推断（路径 A 标准模式，万物云没明确说） |
| **background consolidation** | 是否用了"后台整理 agent"模式 | 🔴 待核，不编 |
| **三类节点 RAG 编排** | 客服 agent 检索流用 StateGraph 混合确定性+agentic 节点 | 🔴 推断（基于 StateGraph+create_agent+interrupt_before） |
| **RAG 是否完整 Agentic** | 客服场景大量单跳，是否多跳+拒答 | 🔴 待核 |
| **Agentic RAG 多跳3跳/拒答** | 属中建/斯维尔项目，不是万物云 | 🟢 简历确认 |
| **上下文压缩** | 滑动窗口 + SummarizationMiddleware 摘要 | 🟡 通用生产做法，万物云作为生产系统会用 |
| **checkpointer TTL** | 配了 TTL | 🟢 万物云确认 |
| **subagent 隔离** | 是否用 | 🔴 待核，不编 |

**核心口径一句话** 🟢：万物云长期记忆 = LangGraph Store（PostgresStore/pgvector）+ 自己实现的 similar merge + 自己实现的 TTL cron，跑在 StateGraph+create_agent 自建框架上，没用 Deep Agents 的 AGENTS.md 文件式记忆。上下文工程用滑动窗口 + 摘要 + checkpointer TTL。RAG 用三类节点（Rewrite/Retrieve/Agent）编排思想；完整 Agentic RAG 多跳/拒答经验属中建项目。

---

## 八、检查题（5 道，含预判疑问）

**题1**：用户昨天在 thread-1 告诉 agent"我对花生过敏"，今天开 thread-2 问"推荐午餐"。用 checkpointer 能让 agent 记住过敏吗？为什么？正确做法？
> 预判："checkpointer 不也是持久化吗，为什么跨 thread 不行？"
> 答：不能。checkpointer 是 **thread-scoped** 🟢，thread_id 一换 checkpoint 完全隔离。正确做法是把"花生过敏"作为一条记忆写进 **Store**，namespace 带 user_id，thread-2 里用当前消息做 query 语义召回，塞进 system prompt。

**题2**：万物云长期记忆用 pgvector + similar merge + TTL。这三个里哪个是官方 Store 内置、哪个是自己实现？为什么 TTL 必须自己实现？
> 预判："官方 Store 不是有 created_at/updated_at 吗，难道不能自动过期？"
> 答：**pgvector 向量检索**是官方 PostgresStore + `index` 配置支持的 🟢（底层 pgvector 🟡）；**similar merge** 是自己实现的业务逻辑（Store 只给 put/get/search，合并要自己写"先搜相似→决定合并还是新建"）🔴；**TTL 是自己实现的**，官方 Store 没有内置过期机制 🔴。`created_at`/`updated_at` 只是时间戳字段，不会自动删数据。TTL 必须自己跑 cron，按 `updated_at + ttl_days` 判断过期并 delete 🟢。

**题3**：朴素 RAG 和 Agentic RAG 区别？三类节点各是什么？哪个确定性、哪个 agentic？
> 答：朴素 RAG = `检索→生成` 直线函数，单跳不管够不够都走完；Agentic RAG = 状态机，LLM 自主决定是否再检索/改写/停止 🟢。三类节点：**Model node（Rewrite）** LLM 重写 query（有 LLM）；**Deterministic node（Retrieve）** 向量检索无 LLM（确定性）；**Agent node** create_agent 推理 + tools（agentic）🟢。万物云客服 agent 用这三类混合编排 🔴（推断）；完整 Agentic RAG 多跳/拒答经验属中建项目 🟢。

**题4**：上下文工程三种解法各是什么？为什么裁剪不能单独用？万物云每轮实际发给模型哪几部分？
> 答：裁剪（删旧消息留最近 N）/ 摘要（小模型压旧消息成摘要）/ 外移（存外部只留指针）🟡。裁剪不能单独用——会丢关键信息（订单号被裁掉后面模型问"订单号是什么"），必须配合摘要或外移 🟢。万物云每轮发：System prompt + 工具定义 + [旧对话摘要 + 最近几轮(含当前 query)]；检索结果用完即丢；关键事实外移 Store 🟡。

**题5**：pi 的记忆和万物云的 pgvector 长期记忆有什么本质区别？pi 为什么不需要 RAG？
> 答：pi 记忆 = AGENTS.md 文件（启动整份加载进 system prompt，always loaded）+ session JSONL（会话级历史），无跨会话语义检索、无 similar merge、无 TTL 🟢。万物云 = pgvector Store 按需语义召回 top-K + similar merge 去重 + TTL cron 清理 🟢。本质区别：pi 是 always loaded 整份加载（文件大了爆 token），万物云是按需语义召回（省 token）。pi 不需要 RAG：coding agent 的知识就是文件系统，read/grep/find 直接读更准更快；万物云是业务 agent，客服知识/规范非结构化，必须 embed 才能语义召回 🟢。根因是场景不同：coding 知识在文件里，业务知识在库里。

---

## 万物云 HITL（人工审核）：interrupt_before + Command(resume=)

### 为什么需要 HITL

Agent 跑到关键点暂停，等人工决策（批准/拒绝/修改），人工确认后才继续。用于**高风险、不可逆**操作——退款、改价、改用户权限——模型不能自作主张。退款错了追不回，所以执行前必须暂停等人确认。🟢

后端类比：HITL = **工作流的人工审批节点**（Activiti `userTask` / Camunda 用户任务）。流程跑到 userTask 暂停，等人审批，审批后继续。`interrupt_before` = userTask 前暂停等审批；checkpointer 存 state = Activiti 流程实例持久化（流程暂停时存 DB，重启不丢）。🟡

### 三种 HITL 机制对比（口径必须清楚）

| 机制 | 层级 | 怎么用 | 标注 |
|---|---|---|---|
| `HumanInTheLoopMiddleware` + `interrupt_on` | LangChain 1.0 middleware（官方主推） | 按工具调用拦截，`after_model` 钩子，四种决策（approve/edit/reject/respond），配置驱动 | 🟢 官方主推 |
| `interrupt_before` / `interrupt_after` | LangGraph 编译参数（较底层） | `compile(interrupt_before=["refund_node"])`，节点级**静态断点** | 🟢 官方但"不推荐用于 HITL" |
| `interrupt()` 函数 | 最底层原语 | 节点代码里主动调，**动态**，可条件触发 | 🟢 官方推荐 |

官方原话🟢："Static interrupts are not recommended for human-in-the-loop workflows. Use the interrupt [function]..." = `interrupt_before/after` 是静态断点，**官方明确说不推荐用于 HITL**（定位是调试/单步）。HITL 官方推荐用 `interrupt()` 函数（动态，节点里调，可条件触发）或 `HumanInTheLoopMiddleware`。

### 万物云为什么用 interrupt_before 不用 interrupt()

万物云用 `interrupt_before`（节点级，手动 StateGraph 按节点控制更自然）。🟢 确认

**为什么选它而不是官方主推的两种**：
- **不用 `HumanInTheLoopMiddleware`**：万物云是手动 StateGraph 自建编排（不是 `create_agent` 直接套 middleware），按节点控制更自然——"退款执行"是一个具名节点，在它前面暂停语义最清晰。🟡 后端类比：你用 Activiti 自己画流程图，在某个 Service Task 前加一个"前置审批"网关，比用一个通用拦截器按方法名匹配更直观。
- **不用 `interrupt()` 函数**：万物云的审核点是**固定**的（退款、改价、改权限这几个节点），不需要运行时动态判断"要不要暂停"。静态断点 `interrupt_before=["refund_node"]` 在 compile 时写死，够用且简单。🟡

**为什么是 before 不是 after**：before = 节点**执行前**暂停（执行前确认，节点还没跑）；after = 节点**执行后**暂停（执行后审核，节点已跑完）。退款这种不可逆操作必须**执行前**拦——after 已经扣了钱再审就没意义了。🟢

面试要点：万物云实际用 `interrupt_before`，但要知道官方现在主推 `interrupt()` / `HumanInTheLoopMiddleware`。别只说 `interrupt_before` 显得老。被追问"为什么不用官方推荐的"答："审核点是固定的几个具名节点，静态断点在 compile 时写死语义清晰、够用；如果是动态的（比如根据参数内容决定要不要审），会改用 `interrupt()` 在节点里条件调。"🟡

### 完整调用流程（两次 HTTP 往返，不是一次连接挂着）

核心：**两次 HTTP 往返**，不是一次连接挂着等人工。第一次 invoke 跑到暂停点返回，HTTP 连接断；人工想 5 分钟、5 小时都行；第二次 resume 用同一个 `thread_id` 从 checkpointer 拉回 state 接着跑。🟢

```
第 1 次往返（发起 + 暂停）：
前端: POST /chat { message: "退款 100 元", thread_id: "abc123" }
后端: result = graph.invoke(
        {"messages":[{"role":"user","content":"退款 100 元"}]},
        config={"configurable":{"thread_id":"abc123"}},
      )
      → agent 跑到 refund_node 前，interrupt_before 触发
      → state 存 checkpointer（key=thread_id）
      → invoke 返回，result 带中断信息（在哪个节点停、要审什么）
后端返回前端: { "status":"paused", "thread_id":"abc123", "node":"refund_node",
               "action":"退款 100 元给用户 X", "allowed":["approve","reject"] }

第 2 次往返（resume）：
前端: 人工点"批准" → POST /resume { thread_id:"abc123", decision:"approve" }
后端: graph.invoke(
        Command(resume={"approved": True}),          # 人工决策塞回去
        config={"configurable":{"thread_id":"abc123"}}, # 同一个 thread_id!
      )
      → 框架用 thread_id 从 checkpointer 拉回暂停时的 state
      → 注入 resume 值 → refund_node 执行 → 完成
后端返回最终结果
```

为什么两次请求能接上：第一次暂停时 state 存 checkpointer，key 是 `thread_id`；第二次 resume 用同一个 `thread_id` 拉回。`thread_id` = JSESSIONID，跨 HTTP 请求找会话状态。🟡

### 生产伪代码 + 逐行解释

```python
# ===== 万物云 HITL：interrupt_before + Command(resume) =====
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver   # 生产用 Postgres

# 1. 定义退款执行节点（这个节点前要暂停等审核）
def refund_node(state):
    # 走到这里说明已通过人工审核（resume 已注入 approved=True）
    if not state.get("approved"):
        return {"messages": [{"role":"assistant","content":"退款未批准，已取消"}]}
    amount = state["refund_amount"]
    call_refund_api(state["order_id"], amount)   # 真正扣款，不可逆
    return {"messages": [{"role":"assistant","content":f"已退款 {amount} 元"}]}

# 2. 建图
builder = StateGraph(dict)
builder.add_node("classify", classify_node)     # 意图分类
builder.add_node("refund", refund_node)          # 退款执行（这个前要停）
builder.add_edge(START, "classify")
builder.add_conditional_edges("classify", route, {  # 条件边路由
    "refund": "refund",
    "chat": END,
})
builder.add_edge("refund", END)

# 3. 关键：compile 时配 interrupt_before —— 在 refund 节点执行前暂停
checkpointer = AsyncPostgresSaver.from_conn_string(DB_URL)   # 🔴 PostgresSaver vs Redis 待用户确认
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["refund"],   # ← 静态断点：refund 跑之前停
)

# 4. 第一次调用（跑到 refund 前暂停，返回中断信息）
result = await graph.ainvoke(
    {"messages":[{"role":"user","content":"帮我把订单 ORD-001 退款 100 元"}]},
    config={"configurable":{"thread_id":"sess-abc123"}},
)
# result 此时在 refund 节点前停了，state 已存 checkpointer
# 把"需要审核退款 100 元"返回给前端

# 5. 第二次调用（人工批准后 resume）
result = await graph.ainvoke(
    Command(resume={"approved": True, "refund_amount": 100, "order_id":"ORD-001"}),
    config={"configurable":{"thread_id":"sess-abc123"}},   # 必须同一个 thread_id
)
# 框架从 checkpointer 拉回 state，注入 resume 值，refund_node 执行，完成
```

逐行重点：
- **`interrupt_before=["refund"]`**：compile 时写死的静态断点。🟢 后端类比：Activiti 流程定义 XML 里在某个 Service Task 前画一个"前置网关"，部署时定死。🟡
- **`Command(resume={...})`**：这是**唯一**能作 `invoke()` 输入的 Command（官方原话🟢："Command(resume=...) is the only Command pattern intended as input to invoke()"）。`Command(goto=)` / `Command(update=)` 是节点函数 `return` 用的，不能传给 invoke。别混。
- **`thread_id` 必须同一个**：第一次和第二次用同一个 `thread_id`，框架才能从 checkpointer 找回暂停的 state。换了就找不回——等于 JSESSIONID 丢了，session 全没。🟡
- **resume 不"goto"任何节点**：它恢复暂停的节点，refund_node 从头重跑。⚠️ 坑：如果用 `interrupt()` 函数（不是 `interrupt_before`），节点会**从头重跑**，`interrupt()` 前的代码会再跑一遍，别放副作用代码或做幂等。🟢 `interrupt_before` 没这个坑（节点还没开始跑）。
- **checkpointer 后端🔴待确认**：源文档 08 说用 PostgresSaver，但按诚实边界，**PostgresSaver vs Redis 待用户确认**，文档标"待确认🔴"。口径："checkpointer 用持久化后端（Postgres），多实例共享 state"。🟡

### 后端类比（Activiti receiveTask 挂起 / signal 恢复）

| 万物云 HITL | Activiti / Spring | 标注 |
|---|---|---|
| `interrupt_before=["refund"]` | 流程定义里在 Service Task 前加一个 `receiveTask`（或前置网关），部署时定死 | 🟡 |
| checkpointer 存 state | 流程实例持久化到 DB（`act_ru_execution` 表），暂停时存，重启不丢 | 🟡 |
| `thread_id` | `processInstanceId`（流程实例 ID），跨 HTTP 请求找回流程状态 | 🟡 |
| `Command(resume={...})` | `runtimeService.signal(processInstanceId, variables)`——给挂起的 receiveTask 发信号 + 带变量恢复 | 🟡 |
| 两次 HTTP 往返 | 触发流程的 HTTP 早返回，审批人第二天 complete task 都行，流程引擎按 processInstanceId 从 DB 拉回 | 🟡 |

一句话：**interrupt_before = receiveTask 前挂起，Command(resume) = signal 恢复带变量，checkpointer = 流程实例持久化表，thread_id = processInstanceId**。🟡

### 生产坑

- **checkpointer 用 InMemorySaver**：多实例部署拉不回（请求打到不同实例）→ 生产必须 PostgresSaver，state 共享存 DB。🟢
- **`thread_id` 要前端生成或网关分配并回传**：不能后端每次随机，否则第二次 resume 找不回。= JSESSIONID 要 cookie 带回来。🟡
- **第二天能 resume 吗**：PostgresSaver 后端，第二天、第二周都能 resume，只要那行还在（默认不自动删）。InMemorySaver 进程重启就丢。🟢
- **C 端多实例并发写同会话**：同一个 thread_id 同时来两个请求（用户连点），会并发改同一 state → 万物云自建 Redis 锁做 thread 级串行化（**不说框架白送**）。🟡 这是分布式系统经典问题，独立文档展开。🔴 万物云自建 Redis 锁是推断

---

## 万物云 MCP：自建非官方 SDK

### 痛点（为什么需要 MCP）

没有 MCP 之前，每个工具一次集成，N 个工具 N 套胶水代码，工具和 Agent 进程绑死，工具发现是手动的。类比 Spring：每个 RPC 调用都手写 `RestTemplate.exchange(...)`，没有统一 `@FeignClient`；没有服务注册中心（Nacos/Eureka），消费方硬编码提供方地址。🟡

**MCP 解决**：把工具暴露变成**独立进程（MCP Server）**，用**标准协议（JSON-RPC）**让任意 Client（Agent）**动态发现并调用**工具。一次实现，处处可用。🟢 一句话定位：**MCP 之于 Agent 工具，等于 HTTP/REST 之于微服务**。

### 万物云为什么自建不用官方 SDK

官方 SDK 两条路🟢：
- Client 端：`langchain-mcp-adapters` 的 `MultiServerMCPClient`，`get_tools()` 把 MCP 工具转成 LangChain 工具喂给 `create_agent`
- Server 端：`FastMCP` 库，`@mcp.tool()` 装饰器

万物云**没用官方 SDK，自建**，只实现 `tools/list` + `tools/call` 的等价。🟢 确认

**为什么自建（轻量只取需要）**🟡：
1. **只用 Tools 原语**：MCP 三大原语（Tools/Resources/Prompts），万物云只需要 Tools（可执行函数）。Resources（只读数据）和 Prompts（提示词模板）没用。🔴 推断（基于"只 tools/list+tools/call 等价"推断，官方文档无万物云细节）。自建只实现需要的两个方法，不背 Resources/Prompts 的包袱。
2. **不依赖额外库**：官方 `langchain-mcp-adapters` 引入 `MultiServerMCPClient` + 会话管理 + 拦截器等一整套。万物云自建就是手写 JSON-RPC 收发，几十行代码，依赖少、可控。
3. **万物云用不到官方拦截器**：官方 SDK 的拦截器（Interceptors）能在工具调用前后注入 LangGraph 运行时上下文（store/state/config）。万物云自建没有这个能力 🔴 推断——但万物云的工具权限/审计走自己的 ToolGuardMiddleware（middleware 层），不依赖 MCP 拦截器。🟡

后端类比：就像你不用 Dubbo 全家桶，自己用 Netty 写个轻量 RPC——只要请求-响应两个方法，不要注册中心、集群容错、负载均衡那些。能省则省。🟡

### JSON-RPC 2.0 协议

MCP 用 **JSON-RPC 2.0** 编码消息，UTF-8 编码。🟢 是**有状态会话协议**（stateful session protocol）——Client 和 Server 先建立会话（initialize 握手），会话内多次请求共享上下文。不是无状态 REST，更像带 Session 的长连接（WebSocket / Dubbo 长连接）。🟢

**万物云自建实现的就是这两个报文的等价**🟢：

`tools/list` 请求（Client 问"你有哪些工具"）：
```json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"cursor":null}}
```
`tools/list` 响应（Server 回工具数组 + 参数 schema）：
```json
{"jsonrpc":"2.0","id":1,"result":{"tools":[
  {"name":"get_weather","description":"Get current weather","inputSchema":
   {"type":"object","properties":{"location":{"type":"string"}}}}
]}}
```
`tools/call` 请求（Client 调某工具）：
```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_weather","arguments":{"location":"New York"}}}
```

关键点：工具参数描述用 `inputSchema`（JSON Schema），LLM 看到就知道怎么填。类比 OpenAPI/Swagger 参数描述，LLM 是消费方按 schema 构造请求。🟡

### 传输方式🔴待核

官方两种传输🟢：stdio（Client 把 Server 拉起成子进程，stdin/stdout 通信）和 Streamable HTTP（独立进程，HTTP POST/GET）。旧版"HTTP+SSE"已被 Streamable HTTP 取代（deprecated）🟢。

**万物云用哪种🔴待核**。源文档示例用了 stdio（子进程 + stdin/stdout），但万物云实际是 stdio 还是 HTTP 没明确确认。面试口径："传输方式待确认，stdio 适合本地工具同机部署，Streamable HTTP 适合远程 Server 多 Client。万物云按场景选。"🔴 不编。

### 生产伪代码（自建 Client 本质形态）

```python
# ===== 万物云自建 MCP Client 的本质（只 tools/list + tools/call 等价，stdio 传输） =====
import subprocess, json, asyncio

class McpClient:
    """自建 MCP Client：只实现 tools/list + tools/call 等价"""
    def __init__(self, server_cmd: list[str]):
        self.server_cmd = server_cmd          # ["python","math_server.py"] 拉起 Server 子进程
        self.proc = None
        self._next_id = 1                      # JSON-RPC 自增请求 id

    async def connect(self):
        # 拉起 Server 子进程，stdin/stdout 用管道
        self.proc = await asyncio.create_subprocess_exec(
            *self.server_cmd,
            stdin=asyncio.subprocess.PIPE,     # Client 写 -> Server stdin
            stdout=asyncio.subprocess.PIPE,    # Server stdout -> Client 读
            stderr=asyncio.subprocess.PIPE,    # Server stderr -> 日志
        )
        # ⚠️ 官方协议要求先 initialize 握手建会话，万物云是否做握手 🔴 待核

    async def _send(self, method: str, params: dict) -> dict:
        req = {
            "jsonrpc": "2.0",        # 协议版本固定 2.0
            "id": self._next_id,     # 请求 id，响应带回相同 id 匹配
            "method": method,        # "tools/list" 或 "tools/call"
            "params": params,
        }
        self._next_id += 1
        line = json.dumps(req) + "\n"   # 换行分隔，单条消息内禁止嵌套换行 🟢
        self.proc.stdin.write(line.encode("utf-8"))  # UTF-8 编码
        await self.proc.stdin.drain()
        resp_line = await self.proc.stdout.readline()  # 阻塞读一行响应
        return json.loads(resp_line.decode("utf-8"))

    async def list_tools(self) -> list[dict]:
        resp = await self._send("tools/list", {"cursor": None})  # 等价 tools/list 🟢
        return resp["result"]["tools"]   # [{name, description, inputSchema}]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        resp = await self._send("tools/call", {"name": name, "arguments": arguments})  # 等价 tools/call 🟢
        return resp["result"]
```

逐行重点：
- **`asyncio.create_subprocess_exec`**：stdio 传输核心——Client 把 Server 拉成子进程。类比 `Runtime.exec()` 起本地进程。🟡
- **换行分隔 + 禁止嵌套换行**：官方强约束🟢。stdin/stdout 是流式字节没有天然消息边界，只能靠换行切。`json.dumps` 出来的 JSON 不能有换行（注意 `indent=` 参数会害死你）。
- **`_next_id` 自增**：JSON-RPC 2.0 要求每个请求有 id，响应带回相同 id 匹配。类比 RPC 的 requestId/correlationId。🟡
- **万物云没实现的**：initialize 握手、分页 cursor、错误码处理、超时、并发锁——自建容易漏的坑 🔴。

### 自建容易漏的坑（🔴 万物云这些有没有做待核）

1. **没做 initialize 握手**：官方协议要求先握手建会话。自建跳过可能导致 Server 状态不一致。
2. **没做错误码处理**：JSON-RPC 有标准 error 对象（`{"error":{"code":-32601,"message":"Method not found"}}`）。自建如果只看 `result` 不看 `error`，Server 报错时 Client 会 KeyError 崩。
3. **没做超时**：`readline()` 阻塞读，Server 卡死 Client 就永远挂着。类比 RPC 不设超时必挂。🟡
4. **没做并发锁**：stdio 是单管道，多个 `call_tool` 并发写 stdin 会交错。自建要加 asyncio.Lock 串行化，或一个请求等一个响应。
5. **默认每次新建会话**：官方 `MultiServerMCPClient` 默认无状态（每次调用新建 session→执行→销毁）🟢，万物云自建如果复用子进程就是长连接，要注意子进程崩了要重启。

---

## 万物云权限/沙箱

### 业务 agent vs coding agent 的权限模型差异（重点）

这是万物云和 pi 最根本的差异，先立概念：

| | 业务 agent（万物云） | coding agent（pi） | 标注 |
|---|---|---|---|
| Agent 干啥 | 调业务工具（建工单、查知识库、退款） | 读写文件、跑 shell、装包、跑代码 | 🟡 |
| 危险面 | 调了不该调的接口（越权退款） | `rm -rf /`、读密钥、数据外泄 | 🟡 |
| 权限模型 | **角色/接口鉴权**（RBAC + 接口 token） | **文件/进程/网络沙箱**（容器隔离） | 🟡 |
| 隔离边界 | 接口层（API 网关 + 业务鉴权） | OS 层（容器/microVM） | 🟡 |

万物云是**业务 agent**，Agent 不跑代码、不碰文件系统，只调业务 API。所以**不需要文件沙箱**，权限靠**角色 + 接口鉴权**。🔴 推断（基于万物云没用 Deep Agents、场景是物业工单/智能问答推断；公开材料没明确说权限方案，不编）

### 万物云权限模型🔴推断

万物云权限分两层：

**1. Agent 调工具时的权限检查（ToolGuardMiddleware，wrap_tool_call）**🟢（源文档第7步确认有这个 middleware）：
```python
class ToolGuardMiddleware(AgentMiddleware):
    async def wrap_tool_call(self, request, handler):
        tool_name = request.name
        if tool_name in DANGEROUS_TOOLS:           # 退款、改价、删设备
            user_role = request.config.get("user_role", "guest")
            if user_role != "admin":
                raise PermissionError(f"非管理员不能调 {tool_name}")
        result = await handler(request)            # proceed 真正调工具
        return result
```
- 危险工具（退款/改价/改权限）只有 admin 角色能调
- 权限检查在 `proceed` 前（fail-fast）：不通过直接抛，工具不执行。**必须在执行前**——不然工具已跑、数据已查出，即使后面拒绝，没权限的信息可能已泄露（纵深防御，跟 Java 权限过滤器放最前面一个道理）🟡

**2. 工具内部调业务接口时的接口鉴权**🔴推断：工具函数调万物云内部 API（创建工单、退款）时，带服务 token / 用户 token，API 网关层再做一次鉴权。这是传统后端鉴权，不是 agent 特有的。🟡

后端类比：
- ToolGuardMiddleware = Spring `@PreAuthorize` / Shiro 权限注解 + `@Around` 切面，方法执行前查角色
- 接口鉴权 = API 网关 token 校验（Spring Cloud Gateway / Nginx + JWT）
- 业务 agent 不需要沙箱 = 你的 Spring 服务不跑用户代码，不需要 Docker 隔离；只有在线代码执行平台（像 LeetCode）才需要沙箱 🟡

### 万物云沙箱🔴待核

万物云没用 Deep Agents Sandbox backend / QuickJS Interpreter 🟢 推断（因为没用 Deep Agents）。万物云 Agent 是否需要跑代码 🔴 待核——从已知"物业工单/智能问答"场景看，更像调业务工具，**可能不需要沙箱**。但公开材料没明确说，不编。

面试话术（🔴 不编原则）：
> "万物云的 Agent 主要做物业工单和智能问答，从场景看是调业务工具（建工单、查知识库），没有代码执行需求，所以没上文件沙箱。权限靠角色 + 接口鉴权（ToolGuardMiddleware 拦危险工具 + API 网关 token 校验），这是业务 agent 的做法——和 coding agent 靠容器隔离不一样。如果未来要加代码执行能力，按官方推荐应该是 sandbox-as-tool + 云沙箱 + 密钥留宿主机 + 网络隔离 + TTL 兜底。"

---

## 万物云 Tool calling 可靠性

Agent 多轮循环里，模型每轮可能调工具。工具调用要可靠，靠**三道闸**：参数校验（防假参数）+ 失败处理（不崩循环）+ ToolMessage 闭合（结果对得上）。

### 1. args_schema 参数校验（= Spring @Valid + DTO）

模型传进来的参数对不对，靠 `args_schema`（Pydantic Model）在**工具执行前**校验。🟢

```python
from pydantic import BaseModel, Field, field_validator

class SearchOrderArgs(BaseModel):
    order_id: str = Field(..., description="订单编号，格式 ORD-YYYYMMDD-XXX")
    @field_validator("order_id")
    @classmethod
    def check_order_id_format(cls, v):
        if not v.startswith("ORD-"):
            raise ValueError("订单编号必须以 ORD- 开头")
        return v

@tool(args_schema=SearchOrderArgs)
def search_order(order_id: str) -> str:
    ...  # 进这里时参数已校验过
```

校验失败抛 `ValidationError`，**工具函数根本不执行**，错误信息回给模型，模型自己决定下一步（重新调 / 问用户）。🟢

万物云踩过的坑：没加 order_id 格式校验时，模型**编了一个不存在的订单号**，工具查库返回空，模型又对着空结果**编了订单状态**（幻觉）。加校验后假号在门口被拦，**幻觉从源头断了**。🟢

后端类比：`Pydantic Model` = DTO 类（带 `@NotBlank`/`@Pattern`），`args_schema` = Controller 参数上的 `@Valid`，校验失败抛 `ValidationError` = `MethodArgumentNotValidException`，Controller 不执行。🟡

### 2. 失败处理：不抛异常，返回错误信息 + retryable

工具执行可能失败（库查不到、超时、参数错、没权限）。**生产做法：工具内部 try/except 把异常转成错误信息返回，不让异常冒泡**。🟢

```python
@tool
def search_order(order_id: str) -> str:
    try:
        db = connect_db()
        ...
    except Exception as e:
        return json.dumps({           # 不抛，返回错误信息
            "error": f"查询失败: {e}",
            "hint": "可稍后重试，或让用户提供更准确的订单号",
            "retryable": True         # 是否值得重试
        })
```

- **抛异常**：冒泡中断整个 agent while 循环，用户收 500。🟢
- **返回错误信息**：作为 ToolMessage 回给模型，模型看到后自己决定下一步（重试 / 换工具 / 问用户），**循环不中断**。🟢

万物云所有工具都包了**统一 try/except 装饰器**，失败统一返回 `{"error","hint","retryable"}`：
- `error`：告诉模型出了什么错
- `hint`：建议模型下一步怎么办（重试 / 换工具 / 问用户）
- `retryable`：是否值得重试（数据库超时 `true` 可重试；参数错 `false` 不可重试，模型该换路或问用户）

**retryable 很关键**：没它模型会对不可重试的错误（参数本来就错）无限重试，只能靠 `recursion_limit`（万物云用框架自带 = 25🟢）兜底硬停。retryable 让模型"聪明地重试"而不是"无脑重试"。🟡

后端类比：抛异常 = DAO 抛异常不接 → 冒泡到用户 500；返回错误信息 = DAO 抛异常被 Service catch → Controller 返错误码 JSON。🟡

### 3. ToolMessage 闭合（tool_call_id 配对）

模型一轮可能并发发**多个**工具调用（同时查订单 + 查物流），每个 tool_call 带一个 `id`，执行完回的 ToolMessage **必须带对应的 `tool_call_id`** 配对。🟢

```
AIMessage(tool_calls=[
  {id:"call_a", name:"search_order", args:{order_id:"ORD-001"}},
  {id:"call_b", name:"query_logistics", args:{order_id:"ORD-001"}}
])
  → 执行后回两条 ToolMessage：
ToolMessage(content="订单已发货",    tool_call_id="call_a")   # 对应 search_order
ToolMessage(content="物流到转运中心", tool_call_id="call_b")   # 对应 query_logistics
```

不关联 id，模型拿到两条 ToolMessage 分不清哪条是订单、哪条是物流——可能把物流结果当订单状态给错答案。🟢 `tool_call_id` = RPC 的 correlationId。🟡

**循环结束的判断信号**：不是"有没有 ToolMessage"，而是"**最后一条 AIMessage 有没有 tool_calls**"。有 tool_calls → 执行工具 → 生成 ToolMessage → 继续；没有 tool_calls → 模型没要求调工具 → 循环结束。🟢

后端类比：tool_call_id = 消息队列的 correlationId / RPC 的 requestId，多请求多响应靠它一一配对。🟡

### 三道闸合起来

| 闸 | 防什么 | 机制 | 后端类比 |
|---|---|---|---|
| args_schema 参数校验 | 模型编假参数（幻觉） | Pydantic Model + `@valid`，执行前拦 | `@Valid` + DTO |
| 失败处理（不抛+retryable） | 工具失败崩循环、无脑重试 | try/except 返回错误 JSON + retryable 字段 | DAO 异常转错误码 |
| ToolMessage 闭合（tool_call_id） | 多工具调用结果对不上 | id 配对，框架自动管理 | correlationId 配对 |

加 `tool_choice="required"`（业务查询首轮强制调工具，防"不查就编"）🟢，= **防幻觉四道闸**：required 防不查就编、args_schema 防编假参数、失败处理防崩循环、tool_call_id 防结果错配。🟡

---

## 对标 pi（架构思想对标，不是代码移植）

pi 是 TypeScript coding agent 工具链（类 Claude Code，7.1 万星），万物云是 Python 业务 agent 平台。对标是**架构思想对标**，不是代码移植。🟡

### pi 无内置 HITL

pi coding-agent README Philosophy 节明确🟢：
> "**No permission popups.** Run in a container, or build your own confirmation flow with [extensions] inline with your environment and security requirements."

= pi **不内置 HITL**（coding agent 自主跑，不需要人工审批每一步）。要 HITL 得自己用 extension 建 confirmation flow，或靠容器化隔离（跑炸了也不烧宿主机）。

为什么？coding agent 的场景是写代码、跑测试、改文件——这些操作可重做、可 git 回滚，不需要每步人工审。业务 agent 不一样：退款、改价不可逆，必须 HITL。🟡

后端类比：pi 像一个有 root 权限的 CI/CD runner，自主跑构建脚本，跑错了重跑；万物云像一个支付系统，每笔交易要人工复核。🟡

### pi 无内置权限，靠容器 Gondolin/Docker/OpenShell

pi root README "Permissions & Containerization" 节明确🟢：
> "Pi does not include a built-in permission system for restricting filesystem, process, network, or credential access. By default, it runs with the permissions of the user and process that launched it."

三种容器化方案🟢：
- **Gondolin extension**：`pi` 和 provider auth 留宿主机，把内置工具和 `!` 命令路由进本地 Linux micro-VM
- **Plain Docker**：整个 `pi` 进程跑在本地容器里，简单隔离
- **OpenShell**：整个 `pi` 进程跑在策略控制的沙箱里

= pi **不内置权限系统**（文件/进程/网络/凭证都不管），默认用启动它的用户的权限。要强隔离就容器化。这跟 coding agent 的定位一致：coding agent 要自由读写文件跑命令，内置权限会碍事；要安全就整体扔进容器。🟢

万物云反过来：业务 agent 不碰文件系统，权限靠角色 + 接口鉴权（ToolGuardMiddleware），不需要容器沙箱。🔴 推断

### pi 明确 "No MCP"

pi coding-agent README Philosophy 节明确🟢：
> "**No MCP.** Build CLI tools with READMEs (see Skills), or build an extension that adds MCP support. Why?"

= pi **不内置 MCP 支持**。替代方案：用 CLI 工具 + README（Skills 标准），或写 extension 加 MCP。理由（链接文章）：coding agent 用文件系统就够了，工具就是 CLI 命令，不需要 MCP 那套协议。🟢

万物云自建 MCP（tools/list + tools/call 等价）：因为业务 agent 要调的内部工具（Dubbo/HTTP/JDBC）是独立服务，MCP 让工具变成独立进程动态发现，跨 agent/跨进程复用。🟢 两者场景不同：coding agent 的工具是本地 CLI（同进程就够），业务 agent 的工具是远程服务（需要协议层）。🟡

### pi tool calling（beforeToolCall + validateToolCall + throw error）

pi-agent-core README 揭示 pi 的 tool calling 可靠性机制🟢：

**1. beforeToolCall preflight hook（能 block）**🟢：
```typescript
beforeToolCall: async ({ toolCall, args, context }) => {
  if (toolCall.name === "bash") {
    return { block: true, reason: "bash is disabled" };  // 能阻止工具执行
  }
}
```
= 万物云的 ToolGuardMiddleware `wrap_tool_call` 的等价物。两者都在工具执行前拦、都能 block。🟡 区别：pi 是 agent 实例的配置项，万物云是 middleware 类（可多个叠加）。

**2. validateToolCall（TypeBox schema 校验）**🟢：
```typescript
const validatedArgs = validateToolCall(tools, toolCall);  // 校验失败抛
```
pi-ai README 用 TypeBox schema（可序列化的 JSON Schema）做参数校验。= 万物云的 `args_schema`（Pydantic Model）的等价物。🟡 区别：pi 用 TypeBox（TypeScript 生态），万物云用 Pydantic（Python 生态），都是 JSON Schema 校验。

**3. 工具失败 throw error → agent 捕获 → isError: true**🟢：
pi-agent-core README 明确：
> "**Throw an error** when a tool fails. Do not return error messages as content. Thrown errors are caught by the agent and reported to the LLM as tool errors with `isError: true`."

这是 pi 和万物云的**关键差异**：
- **pi**：工具 throw error（不 catch），**agent 框架捕获**，转成带 `isError: true` 的 ToolMessage 报告给 LLM。框架负责错误转换。
- **万物云**：工具**自己 catch**，返回错误 JSON 字符串作为 ToolMessage content。工具负责错误转换（带 retryable/hint）。

两者都不崩循环，但错误处理位置不同：pi 靠框架（标准化 `isError` 标志），万物云靠工具自己（自定义 error JSON 结构）。🟡 pi 的方式更标准（框架统一处理），万物云的方式更灵活（能塞 hint/retryable 等业务字段）。🟡

**4. tool execution mode（parallel/sequential）**🟢：pi 默认 parallel（并发执行多个 tool_call，按完成序发 event，但持久化 toolResult 按 assistant 源序）。万物云用 LangGraph 的 ToolNode，默认也是并发。🟡

---

## 对比表（万物云 vs pi，四维度）

| 维度 | 万物云（业务 agent） | pi（coding agent） | 标注 |
|---|---|---|---|
| **HITL** | 有。`interrupt_before`（静态断点）+ `Command(resume=)` 恢复，退款/改价等不可逆操作执行前暂停等人工 | 无内置。Philosophy "No permission popups"，要 HITL 自己用 extension 建 confirmation flow | 万物云🟢确认 / pi🟢官方 |
| **MCP** | 自建非官方 SDK，只 `tools/list`+`tools/call` 等价，轻量只取需要 | 明确 "No MCP"，用 CLI 工具 + Skills（README）代替，或 extension 加 | 万物云🟢确认 / pi🟢官方 |
| **权限/沙箱** | 角色 + 接口鉴权（ToolGuardMiddleware 拦危险工具 + API 网关 token），无文件沙箱（业务 agent 不跑代码） | 无内置权限系统，靠容器 Gondolin/Docker/OpenShell 隔离文件/进程/网络 | 万物云🔴推断 / pi🟢官方 |
| **Tool calling 可靠性** | args_schema(Pydantic) 校验 + 工具自己 try/except 返回 error JSON(retryable/hint) + tool_call_id 配对 + tool_choice=required 防幻觉 | beforeToolCall preflight(能 block) + validateToolCall(TypeBox) + 工具 throw error → 框架捕获转 isError:true | 万物云🟢确认 / pi🟢官方 |

一句话总结差异：**万物云是业务 agent（调 API、要审批、靠鉴权），pi 是 coding agent（跑命令、自主跑、靠容器）**。两者架构选择都被场景驱动——业务操作不可逆要 HITL，coding 操作可重做靠容器兜底。🟡

---

## 面试追问应答

**Q：你们人工审核怎么做的？**
> "高风险不可逆操作（退款、改价、改权限）用 LangGraph 的 interrupt_before 在执行节点前暂停。compile 时配 `interrupt_before=["refund_node"]`，agent 跑到退款节点前停，state 存 checkpointer（Postgres），第一次 HTTP 返回前端'需审核'。人工点批准后，第二次 HTTP 带 `Command(resume={"approved":True})` 和同一个 thread_id，从 checkpointer 拉回 state 接着跑。两次 HTTP 往返，不是一次连接挂着。官方现在主推 interrupt() 函数和 HumanInTheLoopMiddleware，我们用 interrupt_before 是因为审核点是固定的几个具名节点，静态断点语义清晰够用。"🟢

**Q：为什么用 interrupt_before 不用官方推荐的 interrupt()？**
> "审核点是固定的（退款、改价这几个具名节点），不需要运行时动态判断'要不要暂停'。静态断点 compile 时写死，简单清晰。如果是动态的（比如根据参数金额决定要不要审），会改用 interrupt() 在节点里条件调。另外 interrupt_before 是节点执行前停，节点还没跑——退款这种不可逆操作必须执行前拦。"🟡

**Q：MCP 为什么自建不用官方 SDK？**
> "万物云只用 MCP 的 Tools 原语（tools/list + tools/call），Resources 和 Prompts 没用。自建就是手写 JSON-RPC 收发，几十行代码，只实现需要的两个方法，不背 Resources/Prompts 的包袱，也不引入 langchain-mcp-adapters 那一整套（MultiServerMCPClient + 会话管理 + 拦截器）。工具权限和审计走我们自己的 ToolGuardMiddleware，不依赖 MCP 拦截器。传输方式用 stdio（本地工具子进程）。"🔴 传输方式待核，面试按实际讲

**Q：权限怎么管？有没有用沙箱？**
> "万物云是业务 agent，不跑代码不碰文件系统，所以没上文件沙箱。权限两层：一是 ToolGuardMiddleware 在工具执行前查角色（危险工具只有 admin 能调，fail-fast 在 proceed 前）；二是工具调内部 API 时带 token，API 网关再做接口鉴权。这是业务 agent 的做法——和 coding agent 靠容器隔离不一样。coding agent 要读写文件跑命令才需要沙箱，业务 agent 调 API 靠鉴权就够。"🔴 不编，沙箱方案待核

**Q：和 pi 比，你们的 tool calling 有什么不同？**
> "两处主要差异。一是错误处理位置：pi 是工具 throw error、agent 框架捕获转成 isError:true 的标准 ToolMessage；万物云是工具自己 try/except、返回带 error/hint/retryable 的错误 JSON。我们这样做是为了塞 hint（建议模型下一步）和 retryable（是否值得重试），让模型'聪明地重试'而不是无脑重试。二是校验库：pi 用 TypeBox（TS 生态），我们用 Pydantic（Python 生态），都是 JSON Schema 校验，本质一样。pi 还有 beforeToolCall preflight hook 能 block 工具，等价于我们的 ToolGuardMiddleware wrap_tool_call。"🟡

**Q：被追问 checkpointer 是 PostgresSaver 还是 Redis？**
> "checkpointer 用持久化后端，多实例共享 state。具体实现细节待确认（🔴），口径是'用 Postgres 做持久化后端'。InMemorySaver 只能开发用，多实例部署拉不回。"🔴 待用户确认

---

## 万物云口径（按真实，三色标注，没明确说的标🔴不编）

| 项目 | 口径 | 标注 |
|---|---|---|
| 万物云 HITL 机制 | 用 `interrupt_before`（静态断点，compile 时配）+ `Command(resume=)` 恢复 | 🟢 确认 |
| 为什么不用 interrupt()/HumanInTheLoopMiddleware | 审核点固定（退款/改价/改权限几个具名节点），静态断点够用；官方推荐知道但按场景选 | 🟡 选型理由 |
| checkpointer 后端 | 持久化后端（Postgres），多实例共享。**PostgresSaver vs Redis 待用户确认** | 🔴 待确认 |
| 万物云 MCP | 自建非官方 SDK，只 `tools/list` + `tools/call` 等价，没用 Resources/Prompts | 🟢 确认 |
| MCP 传输方式 | **🔴 待核**。源文档示例用 stdio，实际待确认 | 🔴 待核 |
| MCP initialize 握手 / 错误码 / 超时 / 并发锁 | 自建容易漏的坑，万物云是否做了 **🔴 待核** | 🔴 待核 |
| 万物云权限模型 | 角色 + 接口鉴权（ToolGuardMiddleware 拦危险工具 + API 网关 token），**无文件沙箱** | 🔴 推断（基于没用 Deep Agents + 业务场景推断） |
| 万物云沙箱 | 没用 Deep Agents Sandbox/Interpreter。业务 agent 可能不需要沙箱 **🔴 待核** | 🔴 待核 |
| Tool calling 参数校验 | args_schema（Pydantic Model），所有工具都用，不裸用 type hints | 🟢 确认 |
| Tool calling 失败处理 | 统一 try/except 装饰器，返回 `{error, hint, retryable}`，不抛异常 | 🟢 确认 |
| Tool calling 防幻觉 | `tool_choice="required"`（首轮）+ args_schema + 失败处理 + tool_call_id 配对，四道闸 | 🟢 确认 |
| recursion_limit | 用框架自带（万物云=25），"用框架自带兜底并调了阈值" | 🟢 确认 |
| 万物云 multi-agent | Custom workflow（StateGraph）🔴 推断（基于 StateGraph + interrupt_before + create_agent） | 🔴 推断 |

---

## 检查题（5 道，先答再对答案）

**题 1**：万物云 HITL 用 `interrupt_before` 而不是 `interrupt()` 函数，为什么？被追问"官方推荐 interrupt() 不推荐 interrupt_before 做 HITL"怎么答？

**题 2**：MCP 的 `tools/list` 和 `tools/call` 各干啥？万物云自建 MCP 为什么不用官方 SDK（`MultiServerMCPClient` + `FastMCP`）？自建容易漏哪些坑？

**题 3**：万物云工具失败时，为什么"返回错误信息"而不是"抛异常"？返回结构里 `retryable` 字段是干嘛的？没它会怎样？和 pi 的"throw error → 框架捕获转 isError:true"有什么区别？

**题 4**：万物云的权限模型和 pi 的容器沙箱，为什么不一样？各自适合什么场景？万物云如果要加代码执行能力，权限/沙箱该怎么改？

**题 5**：模型一轮并发发了两个 tool_call（search_order + query_logistics），执行完回两条 ToolMessage。如果两条 ToolMessage 都没带 `tool_call_id`，会出什么问题？循环什么时候结束——是"没有 ToolMessage"还是"AIMessage 没有 tool_calls"？

---

**答案要点**（做题时先别看）：

- 题1：审核点固定（退款/改价几个具名节点），静态断点 compile 时写死够用且简单；interrupt() 适合动态条件暂停。被追问答：知道官方推荐 interrupt()/HumanInTheLoopMiddleware，按场景选——固定点用 interrupt_before 语义清晰，动态判断会改用 interrupt()。before 是执行前停（不可逆操作必须执行前拦），after 是执行后审（已跑完）。

- 题2：tools/list（Client 问"你有哪些工具"，Server 回工具数组 + inputSchema）、tools/call（Client 调某工具，Server 回结果）。自建因为只用 Tools 原语（Resources/Prompts 没用），手写 JSON-RPC 几十行，不引入 langchain-mcp-adapters 全套。漏的坑：initialize 握手、错误码处理、超时、并发锁（stdio 单管道并发会交错）。

- 题3：抛异常中断 agent while 循环用户收 500；返回错误信息作为 ToolMessage 回给模型，循环不中断，模型自己决定下一步。retryable=是否值得重试（true 如超时可重试，false 如参数错不可重试）。没它模型对不可重试错误无限重试，只能靠 recursion_limit 硬停。和 pi 区别：pi 工具 throw error 框架捕获转 isError:true（标准化），万物云工具自己 catch 返回 error JSON（能塞 hint/retryable 业务字段，更灵活）。

- 题4：万物云业务 agent 调 API 不跑代码，权限靠角色+接口鉴权（ToolGuardMiddleware 拦危险工具 + 网关 token），不需要文件沙箱；pi coding agent 读写文件跑命令，无内置权限靠容器（Gondolin/Docker/OpenShell）隔离 OS 层。万物云要加代码执行应上 sandbox-as-tool + 云沙箱（LangSmith/E2B）+ 密钥留宿主机 + 网络隔离 + TTL 兜底；数据不出内网则自建 Docker backend + `--network none` + `--memory` + `--cap-drop ALL`。

- 题5：模型分不清哪条结果是订单、哪条是物流，可能把物流结果当订单状态给错答案。tool_call_id 是配对的 correlationId。循环结束信号是"**最后一条 AIMessage 没有 tool_calls**"——不是"没有 ToolMessage"。有 tool_calls→执行工具→生成 ToolMessage→继续；没有 tool_calls→循环结束。ToolMessage 永远是 tool_calls 触发的，没 tool_calls 就没 ToolMessage，且没有下一轮。

---

## 块6：生产实战与坑 + 部署

> 定位：Agent 从 demo 跑通到上生产，必须解决的工程化问题。前 5 块讲的是"Agent 怎么写"，这块讲"写完了怎么扛住生产"。
> 风格：后端类比（Spring Boot / Activiti / Redis / JUC / RabbitMQ）+ 生产伪代码（Python，万物云是 Python）+ 三色标注（🟢官方/已确认 🟡后端类比/通用spec 🔴推断待核）。
> 诚实边界：万物云自托管 LangGraph（StateGraph + create_agent），不是 LangSmith Agent Server。Agent Server 的内置能力（double-texting 四策略、自动 checkpointer）万物云没有，靠自建补。下面每条标清楚"框架给的"vs"万物云自己加的"。

---

### 1. 万物云生产坑表（现象 / 原因 / 解法 / 口径）

上生产你会撞上 7 个坑。每个坑按"现象→原因→解法→口径"四段讲，最后汇总成速查表。

#### 坑1：递归爆栈（recursion_limit 兜底）

**现象**：Agent 在 model→tool→model 循环里卡死。比如 tool 报错→model 看到错误重试→又报错→又重试，永远停不下来，烧 token 烧到天亮，账单几千块。

**原因**：Agent loop 是个 while(true) 循环（第1步讲过），如果模型不主动决定停，又没有外部终止条件，就会无限转。🟢 Pregel 官方文档原文："Repeat until no actors are selected for execution, or a maximum number of steps is reached."

**解法**：`recursion_limit` 是框架内置的 super-step 步数上限。🟢 默认 25（一次 model call + 一次 tool call = 2 个 super-step，25 步 ≈ 12 轮 tool 调用）。超过抛 `GraphRecursionError`。

```python
# 万物云口径：用框架自带兜底 + 调了阈值 🟢
config = {
    "configurable": {"thread_id": thread_id},
    "recursion_limit": 25,      # 🟢 框架内置兜底，万物云确认用 25
}
result = agent.invoke({"messages": [...]}, config=config)
```

触发兜底不能直接报错给用户，要降级：

```python
from langgraph.errors import GraphRecursionError

try:
    result = agent.invoke({"messages": [...]}, config=config)
except GraphRecursionError:
    # 友好降级，不把异常直接抛给前端 🔴 万物云具体降级文案待核
    return {"answer": "任务过于复杂，已转人工处理，请稍候"}
```

**口径**：🟢 recursion_limit=25，框架内置兜底，万物云确认用这个值并调过阈值。面试被问"为什么 25 不是 10 或 50"答：太低复杂任务做不完、太高烧钱且延迟高，25 是复杂度和成本的平衡点（经验值，业务调的）。

> **预判疑问**：recursion_limit 和第3步讲的"三层防护"什么关系？
> 第一层 recursion_limit 是**最后兜底**（触发时已烧 25 轮）；第二层证据增量检测、第三层多步检索最多 3 跳是**提前止损**（第 2-3 轮就截断）。三层各管一段，不冗余。

#### 坑2：上下文膨胀（trim_messages / 摘要）

**现象**：对话越长 messages 列表越长，撑爆 LLM 的 context window（128k 也会爆），超限直接报错；或者没超限但每轮发给模型的 token 越来越多，成本飙升、延迟变高。

**原因**：Agent 每轮调模型都看**全部历史**（第10步讲过 messages 是累积的）。一个 20 轮对话，第 20 轮要把前 19 轮全发给模型。工具返回的大结果（搜索 10KB、读文件 50KB）也全塞主上下文。

**解法**：三种手段组合用，不能单用一种。

```python
# 🟡 通用思路（万物云作为生产系统会用，具体策略 🔴 待核不编）
from langchain_core.messages import SystemMessage, trim_messages as lc_trim

# 手段1：裁剪（trim_messages）- 只留最近 N 轮
# ⚠️ 单独用会丢关键信息（订单号被裁掉，模型后面问"订单号是什么"）
messages = lc_trim(
    state["messages"],
    max_tokens=4000,           # 按 token 裁，不按轮数（一轮可能 50 也可能 5000 token）
    strategy="last",           # 保留最近的
    token_counter=model,       # 用模型的 tokenizer 计数
    start_on="human",          # 从 HumanMessage 开始（保证不切断 tool_call 配对）
)

# 手段2：摘要（SummarizationMiddleware）- 旧消息压成一段
# 🟢 LangChain 提供 SummarizationMiddleware，before_model 钩子里跑
from langchain.agents.middleware import SummarizationMiddleware

summarizer = SummarizationMiddleware(
    model=init_chat_model("gpt-4o-mini"),   # 用便宜小模型摘，主模型贵
    max_tokens_before_summary=8000,          # 超 8000 token 才摘，不是每轮都摘
    messages_to_keep=4,                      # 保留最近 4 条原样不摘
)
agent = create_agent(model=model, tools=tools, middleware=[summarizer])

# 手段3：外移（Store 长期记忆）- 关键事实不靠摘要，存到 pgvector
# 订单号这种关键事实塞进摘要会被多次压缩丢掉，必须外移
store.put(("user", "zhang_san"), "last_order", {"order_id": "ORD-001"})
```

**万物云每轮实际发给模型** = System prompt + 工具定义 + [摘要 + 最近几轮(含当前 query)]。检索结果用完即丢（外移），关键事实外移到 Store。

**口径**：🟢 长期记忆用 pgvector + similar merge + TTL（不是 Deep Agents 的 AGENTS.md）。🟡 上下文压缩（滑动窗口/摘要是通用生产做法，万物云作为生产系统会用，具体策略 🔴 不编）。面试口径："上下文管理我们用滑动窗口 + 摘要控制多轮消息，工具大输出靠 subagent 隔离。长期记忆用 pgvector 向量检索 + 相似合并 + TTL 清理。没用 Deep Agents 的 AGENTS.md，自己用 pgvector 实现。"

#### 坑3：并发写冲突（double-texting 自建 Redis 锁）

**现象**：同一个 thread_id，用户连发两条消息（双击"批准"），或前端网络超时自动重发了 resume 请求，两个 run 同时改同一份 state，checkpoint 互相覆盖，状态撕裂。如果工具是退款 100 元，**可能执行两次退 200**。

**原因**：Agent 有状态（state 在 checkpointer），两个 run 同时写同一个 thread_id 的 checkpoint = 经典 race condition。

**解法（两种，分场景）**：

🟢 **Agent Server（LangSmith 托管）内置 4 策略**（double-texting 页确认）：

| 策略 | 行为 | 后端类比 | 返回 |
|------|------|----------|------|
| enqueue（默认） | 第一个跑完，第二个排队接跑 | BlockingQueue.put() | 200 |
| reject | 直接拒第二个，第一个继续 | ReentrantLock.tryLock() 失败 | **409 Conflict** |
| interrupt | 暂停第一个（保留进度），插入第二个，跑完恢复 | Thread.interrupt() + 保存现场 | 200 |
| rollback | 回滚第一个全部进度，用第二个从头跑 | transaction.rollback() + 重来 | 200 |

🟢 **关键**：官方原文 "Double texting is a feature of LangSmith Deployment. It is not available in the LangGraph open source framework." —— **这四策略是 Agent Server 商业版的，OSS LangGraph 没有**。

🔴 **万物云自托管（StateGraph + create_agent），没有 Agent Server，所以没有这四策略**。万物云自己加 Redis 锁实现 reject 等价语义：

```python
# redis_concurrent_lock.py - 万物云自托管 concurrent-run 保护 🔴 推断
import redis, uuid

redis_client = redis.Redis(host='redis-host', port=6379, db=0)

def acquire_thread_lock(thread_id: str, timeout: int = 300):
    """
    同一 thread_id 同时只允许一个 run。
    类比：Redisson RLock.tryLock(thread_id, 300, SECONDS)
    """
    lock_key = f"agent:run:lock:{thread_id}"       # 锁 key 带 thread_id 维度
    lock_token = str(uuid.uuid4())                  # 唯一 token，防误解锁

    # SET NX EX：不存在才设置，原子操作 🟡 通用 Redis 模式
    acquired = redis_client.set(lock_key, lock_token, nx=True, ex=timeout)
    if acquired:
        return lock_token                           # 拿到锁
    return None                                     # 该 thread 有 run 在跑，拒绝

def release_thread_lock(thread_id: str, lock_token: str):
    # Lua 脚本保证"检查 token + 删除"原子 🟡 通用 Redis 模式
    lua = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    return redis_client.eval(lua, 1, f"agent:run:lock:{thread_id}", lock_token) == 1

# 生产调用
def handle_user_message(thread_id: str, user_input: str):
    lock_token = acquire_thread_lock(thread_id, timeout=300)
    if lock_token is None:
        return {"error": "该会话正在处理中，请稍后再试", "code": 409}  # 等价 reject
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"configurable": {"thread_id": thread_id}, "recursion_limit": 25},
        )
        return result
    finally:
        release_thread_lock(thread_id, lock_token)  # try-finally 保证不漏释放
```

**口径**：🔴 万物云 concurrent-run hard protection 是自己加的 Redis 锁（基于"自托管没用 Agent Server"推断）。面试讲到这要说"我们自托管，并发保护是自己加的 Redis 锁"，别说框架白送。退款这类副作用工具还要配幂等键（refund_id）双保险。

#### 坑4：LLM 429 限流（RateLimiter + retry + max_concurrency）

**现象**：高并发下你的 Agent 同时发 100 个请求给 LLM provider，API 返回 429（Rate Limit Exceeded），你的 Agent 全线崩溃，所有用户都收到错误。

**原因**：LLM 是外部依赖，有 API quota 限制（每分钟 N 个请求）。你不控制对它的并发，高并发时直接打爆。

**解法**：🟢 三层防护（handle-model-rate-limiting 页确认），从客户端到并发数：

```python
# rate_limit_setup.py - 三层限流容错 🟢
from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter

# 第一层：令牌桶限流 - 控制发往 LLM 的请求速率
# 类比：Guava RateLimiter.create(2.0) + Semaphore(10) / Sentinel
rate_limiter = InMemoryRateLimiter(
    requests_per_second=2.0,        # 每秒最多 2 个请求（按 API quota 设）
    check_every_n_seconds=0.1,      # 每 100ms 检查令牌桶
    max_bucket_size=10,             # 令牌桶上限 10，允许短时 burst
)

# 第二层：指数退避重试 - 429 时自动重试
# 类比：Spring @Retryable(maxAttempts=5, backoff=@Backoff(delay=1000, multiplier=2))
model = init_chat_model(
    "anthropic:claude-sonnet-4-6",
    rate_limiter=rate_limiter,       # 挂上限流器
).with_retry(
    stop_after_attempt=5,            # 最多重试 5 次，1s->2s->4s->8s->16s
)

# 第三层：max_concurrency - 并发上限，限制同时发出的请求数
# 类比：JUC Semaphore permits
# 在 evaluation / 批处理场景用
results = await aevaluate(..., max_concurrency=4)   # 最多 4 个并发
```

**三层各管什么**：RateLimiter 管**速率**（每秒几个）、retry 管**容错**（429 后重试）、max_concurrency 管**并发数**（同时几个）。一个防打爆、一个防偶发、一个防积压。

**口径**：🟢 万物云作为生产系统会用限流重试（面试技术准备手册确认："LLM 调用并发控制避免打爆 LLM API 限频 429"）。具体参数（requests_per_second 多少、retry 几次）🔴 按实际 quota 讲。

#### 坑5：thread_id 1-run-per-thread（并发隔离规则）

**现象**：跟坑3相关但更基础。核心规则：🟢 官方原文 "The queue enforces that at most 1 run can be executed for a given thread at one time." —— 同一个 thread_id，同时只能有一个 run 在跑。

**原因**：thread_id = 会话身份（= JSESSIONID）。同一个会话两个 run 同时跑会互相覆盖 state。但**不同 thread_id 无竞争**：各跑各的，state 各存在 Postgres 不同行，不需要锁。

**解法**：理解清楚锁的粒度——锁的是 thread_id 维度，不是全局。

```python
# ❌ 错误：全局锁，所有请求串行，并发上不去
global_lock = acquire_lock("agent:global")  # 所有 thread 共用一把锁

# ✅ 正确：thread 维度锁，不同 thread 并行，同 thread 串行
thread_lock = acquire_lock(f"agent:run:lock:{thread_id}")  # 每个 thread 一把锁
```

**后端类比**：跟你 Activiti 里同一个 processInstanceId 同时只能有一条 execution 在推进是一个道理。不同流程实例可以并行，同一流程实例串行。

**口径**：🟢 1-run-per-thread 是核心规则（agent-server 页确认）。🔴 万物云自托管没有 Agent Server 的 queue 自动 enforce，是自己用 Redis 锁实现的（同坑3）。

#### 坑6：TTL 只对新 thread（checkpoint 膨胀清理）

**现象**：你配了 `checkpointer.ttl.default_ttl=43200`（30天），部署后 Postgres 磁盘还在涨，查发现老 thread 的 checkpoint 没被清。

**原因**：🟢 官方原文 "TTLs are applied to threads and checkpoints when they are created. They do not apply to existing threads and checkpoints." —— **TTL 只对配置部署后新创建的 thread 生效，老 thread 不受影响**。

**解法**：

```json
// langgraph.json - checkpointer TTL 配置 🟢
{
  "checkpointer": {
    "ttl": {
      "strategy": "delete",            // delete=删整个thread | keep_latest=只留最新checkpoint
      "sweep_interval_minutes": 60,    // 后台 sweeper 每 60 分钟扫一次
      "default_ttl": 43200             // 新 thread 存活 43200 分钟 = 30 天
    }
  }
}
```

老数据要手动删：
```python
# 手动清老 checkpoint（TTL 管不到的存量数据）
# 🟡 通用 SQL，万物云用 PostgresSaver
await db.execute(
    "DELETE FROM checkpoints WHERE created_at < NOW() - INTERVAL '30 days'"
)
```

**预判疑问：能不能每个 thread 设不同 TTL？** 🟢 能，per-thread TTL：`client.threads.create(ttl={"strategy": "delete", "ttl": 43200})`。VIP 用户对话保留久一点，普通用户短一点。

**口径**：🟢 万物云配了 TTL（万物云确认）。🔴 万物云是否用 langgraph.json 配置（Agent Server 方式）还是自己跑 cron 清理待核——因为自托管可能不走 langgraph.json，而是自己写定时任务。面试讲"checkpoint 膨胀用 TTL 控制 + 定时清理"即可。

#### 坑7：Checkpointer TTL + durability modes（存储膨胀三层防线）

**现象**：每个 super-step 存一个 checkpoint 全量快照。一个 20 轮对话 = 20+ 个 checkpoint，每个存全量 state（含所有 messages）。1000 用户 × 每天 10 thread × 20 步 = 每天 20 万条 checkpoint，Postgres 磁盘一周爆。🟢 官方原文："Over long conversations, checkpoints accumulate. This can increase latency and storage costs."

**解法**：三层防线。

**第一层：durability 降级**。🟢 三种持久化模式（checkpointers 页确认）：

| 模式 | 行为 | 后端类比 | 适用 |
|------|------|----------|------|
| `exit` | 只在 graph 结束时存一次，中间不存 | 方法结束时才写一次 DB | 短任务/批处理，减少 90% 写入 |
| `async`（默认） | 每个 super-step 异步存，下一步开始时上一步在后台写 | Spring @Async + write-behind | 折中，性能好 |
| `sync` | 每个 super-step 同步存，写完才下一步 | Spring 同步事务 commit | 最安全最慢 |

```python
# 🟢 官方原文
graph.stream({"input": "test"}, durability="sync")   # 同步存，最安全
graph.stream({"input": "test"}, durability="async")  # 默认，异步存
graph.stream({"input": "test"}, durability="exit")   # 只存最终结果
```

**第二层：TTL 自动清理**（见坑6）。

**第三层：DeltaChannel（beta）**。🟢 传统 checkpoint 存全量 state（100 条消息存 20 份 = 存 20 份 100 条），DeltaChannel 只存增量 delta（新增的那条），从 O(N) 降到 O(1)。🔴 beta 阶段，万物云是否用待核，没上线先用 TTL。

**口径**：🟢 万物云配了 TTL 控制膨胀。🔴 durability 模式（sync/async/exit 哪个）不编，没明确说。🔴 DeltaChannel 不编，beta 阶段。

#### 7 坑速查表

| 坑 | 现象 | 原因 | 解法 | 万物云口径 |
|----|------|------|------|-----------|
| 1 递归爆栈 | Agent 卡循环烧 token | while(true) 无外部终止 | recursion_limit=25 兜底 + 降级 | 🟢=25 框架自带 |
| 2 上下文膨胀 | messages 撑爆 context | 每轮看全部历史 | 裁剪+摘要+外移三组合 | 🟡通用做法 🔴具体策略待核 |
| 3 并发写冲突 | 双发消息 state 撕裂 | 同 thread 两 run 竞争 | Agent Server 4策略 / 自建 Redis 锁 | 🔴自建 Redis 锁 |
| 4 LLM 429 | 高并发 API 全线 429 | 不控制对 LLM 并发 | RateLimiter+retry+max_concurrency | 🟢会用 🔴参数待核 |
| 5 1-run-per-thread | 同 thread 并行乱套 | 同 thread state 共享 | thread 维度串行（不同 thread 并行） | 🔴Redis 锁实现 |
| 6 TTL 不清旧数据 | 配了 TTL 磁盘还涨 | TTL 只对新 thread | 老数据手动删 | 🟢配了 TTL 🔴cron vs langgraph.json待核 |
| 7 checkpoint 膨胀 | Postgres 磁盘爆 | 每 step 存全量快照 | TTL+durability+DeltaChannel | 🟢TTL 🔴durability/Delta待核 |

---

### 2. 万物云部署架构（API Server + Queue Worker + Postgres + Redis）

#### 为什么 demo 能跑但生产不能

demo 里一个 `graph.invoke()` 全搞定——接请求、跑 graph、存 state、返回结果全在一个进程一个调用里。生产不行：

- **LLM 调用慢**（几秒到几十秒），HTTP 网关通常 30-60s 超时，不可能一次 invoke 挂着连接等完
- **C 端必然多实例**，state 不能在进程内存（InMemorySaver 多实例拉不回）
- **接请求的和跑 graph 的职责不同**，扩容维度不同，要分开

#### 四组件架构（Agent Server 参考架构 🟢）

🟢 官方文档确认（agent-server 页 Runtime architecture），Split API and queue 模式：

```
User
 ↓ HTTP
API Server（接请求，不跑 graph 代码，创建 run / 读 state / 转发 SSE）
 ↓ create run
Postgres（存所有持久数据：thread / run / checkpoint / store）
 ↓ notify
Redis（pubsub + ephemeral run 信号 + 分布式锁）
 ↓ wake
Queue Worker（跑 graph 代码，写 checkpoint）
 ↓ publish events
Redis → API Server → SSE → User
```

**关键点**（🟢 官方原文）：
- API server 和 Queue worker 是**同一 Docker image，不同启动命令**（`langgraph-api` vs `langgraph-queue-worker`）
- 容器是 **stateless** 的——数据全在 Postgres + Redis，扩容缩容不丢数据
- 至少 1 个 queue worker 必须活着，否则 run 被 orphan（永远 pending）
- `N_JOBS_PER_WORKER` 默认 10：一个 worker 容器同时跑 10 个 run
- `available_jobs = number_of_queue_workers × N_JOBS_PER_WORKER` 🟢
- `throughput_per_second = available_jobs / average_run_execution_time_seconds` 🟢

**Redis 存什么**：🟢 官方原文 "Redis handles the storage of ephemeral data about on-going runs" + "stores only ephemeral data—no user or run data persists in Redis" —— Redis 只存 ephemeral 信号（run 状态、pubsub 消息、锁），**不存用户数据**。用户数据全在 Postgres。

#### 为什么这么拆（三个理由）

| 理由 | 解释 | 后端类比 |
|------|------|----------|
| **异步削峰** | LLM 慢，API 接请求后不等 graph 跑完，丢给 Worker 异步执行，API 立刻返回 job_id（=thread_id），前端轮询/SSE 取结果 | RabbitMQ 削峰：消费端按能力拉取，峰值不直接打到 DB |
| **状态持久化** | state 在 Postgres 不在进程内存，实例挂了/重启了，用 thread_id 从 Postgres 拉回继续 | Spring Session + Redis：session 统一存 Redis，所有实例共享 |
| **独立扩容** | API 按读 QPS 扩（接请求快），Worker 按 run 积压数扩（跑 graph 慢），各自扩容更高效 | Tomcat（接请求）vs 消息消费者（跑任务）分开扩容 |

#### docker-compose 伪代码（Split 模式）

```yaml
# docker-compose.yml - Split API and queue 模式 🟢
services:
  # API Server：接 HTTP 请求，不跑 graph 代码
  api-server:
    image: my-agent-app:latest           # 跟 worker 同一个 image
    command: ["langgraph-api"]           # 启动命令：API 模式
    environment:
      - REDIS_URL=redis://redis:6379
      - POSTGRES_URI=postgresql://user:pass@postgres:5432/langgraph
      - N_JOBS_PER_WORKER=10
    deploy:
      replicas: 3                        # 3 个 API 容器（按读 QPS 扩）
    depends_on: [postgres, redis]

  # Queue Worker：跑 graph 代码，写 checkpoint
  queue-worker:
    image: my-agent-app:latest           # 同一个 image
    command: ["langgraph-queue-worker"]  # 启动命令：Worker 模式
    environment:
      - REDIS_URL=redis://redis:6379
      - POSTGRES_URI=postgresql://user:pass@postgres:5432/langgraph
      - N_JOBS_PER_WORKER=20             # IO bound（等 LLM），调高到 20
    deploy:
      replicas: 5                        # 5 个 worker，available_jobs = 5×20 = 100
    depends_on: [postgres, redis]

  # Postgres：存所有持久数据（thread/run/checkpoint/store）
  postgres:
    image: postgres:16
    environment:
      - POSTGRES_DB=langgraph
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - pgdata:/var/lib/postgresql/data  # 数据持久化
    # 🟢 官方建议高读写场景：4 CPU / 16Gi+

  # Redis：只存 ephemeral 信号 + pubsub + 分布式锁
  redis:
    image: redis:7-alpine
    # 🟢 官方："stores only ephemeral data"
    # 不需要持久化，重启丢信号无所谓（run 状态在 Postgres 有备份）
```

#### 后端类比总表（Agent概念 | Spring/Activiti/Redis/JUC）

| Agent 概念 | 后端类比 | 说明 |
|------------|----------|------|
| API Server | Spring Boot @RestController | 只接 HTTP 请求，不做业务逻辑，转发给后端 |
| Queue Worker | Activiti Job Executor / Spring @Async 线程池 | 真正跑任务（graph）的执行引擎 |
| Postgres（checkpoint） | Activiti ACT_RU_EXECUTION / ACT_HI_ACTINST | 持久化流程实例状态，重启可恢复 |
| Redis（ephemeral+pubsub） | Redis pub/sub + SseEmitter | 传递实时信号，不存业务数据 |
| thread_id 串行 | Activiti processInstanceId 唯一执行链 | 同一流程实例同时只有一条执行路径 |
| N_JOBS_PER_WORKER | ThreadPoolExecutor corePoolSize | 单 worker 并发处理数 |
| available_jobs = workers × N_JOBS | 线程池总容量 = corePoolSize × 实例数 | 集群总并发 |
| durability="sync" | Spring 同步事务 commit 后才返回 | 最安全最慢 |
| durability="async" | Spring @Async + write-behind cache | 异步写，性能好，有小窗口丢数据风险 |
| durability="exit" | 只在方法结束时写一次 DB | 短任务用，中间步骤不存 |
| checkpointer TTL | Redis EXPIRE / Activiti History Cleanup Job | 定时清理过期数据 |
| InMemoryRateLimiter | Guava RateLimiter / Sentinel / Bucket4j | 令牌桶限流，客户端控制 |
| .with_retry() | Spring @Retryable + ExponentialBackoffPolicy | 指数退避重试 |
| max_concurrency | JUC Semaphore permits | 限制并发数 |
| Redis 分布式锁（自托管） | Redisson RLock.tryLock() | SET NX EX + Lua CAS 释放 |
| double-texting reject (409) | ReentrantLock.tryLock() 返回 false | 拿不到锁就拒绝 |
| double-texting enqueue | LinkedBlockingQueue.put() | 排队等前面跑完 |

#### 万物云实际部署口径

🟢 万物云自托管 LangGraph（StateGraph + create_agent），**不是 LangSmith Agent Server**。所以上面的 Split API+queue 架构是**官方参考架构**，万物云是否完全照搬 🔴 待核。

🟢 但万物云的部署原则是确认的（面试技术准备手册）：
- **FastAPI 异步非阻塞**接请求（= API Server 角色）
- **任务队列削峰**（= Queue Worker 角色，万物云 IoT 项目用 RabbitMQ，Agent 平台具体队列 🔴 待核）
- **Postgres 存 checkpoint + pgvector 存长期记忆**（= Postgres 角色）
- **Redis 做分布式锁 + 缓存**（= Redis 角色）
- **K8s 容器化部署**，多实例 + 滚动更新

🔴 **待核不编**：万物云 Agent 平台具体是 single host 还是 split API+queue 模式、checkpointer 后端是 PostgresSaver 还是 Redis 封装（面试技术准备手册说 PostgresSaver，但若实际是别的按真实的改口述）。

**面试口径**："部署上是 FastAPI 接请求 + 异步任务跑 graph + Postgres 存状态 + Redis 做锁和缓存，四组件分开各自扩容。API 按读 QPS 扩，Worker 按 run 积压扩。状态全在 Postgres 不在进程内存，容器 stateless 扩缩容不丢数据。"

---

### 3. 对标 pi：CLI 工具 vs 服务端部署

#### pi 是什么（一句话定位）

pi 是 **TypeScript coding agent 工具链**（类 Claude Code，7.1万星），万物云是 **Python 业务 agent 平台**。对标是**架构思想对标不是代码移植**——pi 用 TypeScript，万物云用 Python；pi 给开发者本地跑，万物云给园区运营人员线上服务。

#### pi 的部署形态：CLI 工具，无服务端

🟢 pi 根 README + AGENTS.md 确认：

- **npm 发布的 CLI 包**：`@earendil-works/pi-coding-agent`，用户 `npm install` 或 `npx` 装本地用
- **Node/Bun 双打包**：同一个包同时支持 Node 和 Bun 运行时（release smoke test 分别测 `node/pi` 和 `bun/pi`）
- **无服务端部署**：pi 跑在开发者本机，没有 API Server / Queue Worker / Postgres / Redis 这套。状态在本地文件系统（AGENTS.md + session-resources）
- **无内置权限系统**：🟢 README 原文 "Pi does not include a built-in permission system for restricting filesystem, process, network, or credential access." 靠容器化隔离（Gondolin / Docker / OpenShell 三种模式）
- **无内置 HITL**：coding agent 用文件系统交互，不需要 interrupt_before
- **无 RAG**：coding agent 直接读文件系统，不需要向量检索
- **记忆靠 AGENTS.md 文件**：🟢 文件式记忆，启动时整份加载进 system prompt（跟万物云 pgvector 完全不同）

#### pi 的发布流程（AGENTS.md Releasing 节 🟢）

🟢 **Lockstep versioning**：所有包共享一个版本号，每次 release 全部一起更新。`patch` = 修复+新增，`minor` = breaking changes，**无 major release**。

发布步骤：
1. 更新 CHANGELOG（每个包 `packages/*/CHANGELOG.md` 的 `[Unreleased]` 节）
2. 本地 smoke test：`npm run release:local -- --out /tmp/pi-local-release`，在 repo 外测 Node 和 Bun 两种安装
3. 跑 release 脚本：`npm run release:patch` 或 `release:minor`（带 `PI_ALLOW_LOCKFILE_CHANGE=1` 允许改 lockfile）
4. release 脚本自动：bump 版本 → 更新 changelog → 重新生成 release artifacts → 跑 `npm run check` → commit `Release vX.Y.Z` → 打 tag `vX.Y.Z` → push
5. **CI 发布 npm**：push tag 触发 GitHub Actions，用 **npm trusted publishing（OIDC）**，不需要本地 `npm publish` / OTP / WebAuthn

#### pi 的 supply-chain hardening（供应链加固 🟢）

🟢 pi 根 README "Supply-chain hardening" 节 + AGENTS.md "Dependency and Install Security" 节确认。pi 把 npm 依赖变更当成 code review 级别对待：

| 加固措施 | pi 做法 | 说明 |
|----------|---------|------|
| **依赖锁定** | 直接外部依赖 pin 到精确版本（`save-exact=true`） | 内部 workspace 包保持 version-range |
| **min-release-age** | `.npmrc` 设 `min-release-age=2`（天） | 避免用当天刚发布的依赖（可能被投毒/有未发现 bug） |
| **lockfile 保护** | `package-lock.json` 是 ground truth，pre-commit 阻止意外提交 lockfile 改动 | 除非设 `PI_ALLOW_LOCKFILE_CHANGE=1` |
| **shrinkwrap** | 发布的 CLI 包含 `npm-shrinkwrap.json`（从 root lockfile 生成） | pin 住 transitive deps，npm 用户装的是固定版本 |
| **lifecycle script 白名单** | shrinkwrap 生成有显式 allowlist | 新依赖带 lifecycle script 会 fail check 直到 review |
| **ignore-scripts** | 本地 `npm install --ignore-scripts` / CI `npm ci --ignore-scripts` | 不跑依赖的 lifecycle script（防 install 时执行恶意代码） |
| **npm audit** | 定时 GitHub workflow 跑 `npm audit --omit=dev` + `npm audit signatures` | 查漏洞 + 验签名 |
| **release smoke test** | `npm run release:local` 在 repo 外建独立 npm/bun 安装测 | 确保发布版不依赖 workspace 内部文件 |

#### 万物云后端依赖管理（对比）

万物云是 Python 后端，依赖管理跟 pi 的 npm 完全不同，但**思想可对标**：

| 维度 | pi（npm/TypeScript） | 万物云（Python） | 对标点 |
|------|---------------------|-----------------|--------|
| 依赖锁定 | package-lock.json + shrinkwrap | requirements.txt / poetry.lock / pip-tools | 都要锁版本 |
| 精确版本 | save-exact=true pin | `==` 精确 pin（非 `>=`） | 防漂移 |
| 安装安全 | --ignore-scripts 不跑 lifecycle | pip 无 lifecycle script，但要看 setup.py | pi 更严（npm 有 postinstall 攻击面） |
| 漏洞扫描 | npm audit + signatures | pip-audit / safety / dependabot | 都要定期扫 |
| 发布 | npm trusted publishing (OIDC) | 私有镜像仓库 / K8s 部署 | pi 走公共 npm，万物云走内部 |
| 版本管理 | lockstep（所有包同版本） | 服务独立版本（微服务） | pi 是 monorepo 统一版本，万物云是多服务 |
| min-release-age | 2 天缓冲 | 🔴 万物云是否用待核 | 防当天发布依赖 |

**关键差异**：pi 是 CLI 工具发给开发者用，供应链加固重点是"别让恶意依赖进了开发者的机器"；万物云是服务端部署，重点是"别让漏洞依赖进了生产服务器"+"容器镜像扫描+base image 固定"。

#### pi 无服务端部署 vs 万物云服务端部署（核心对比）

| 维度 | pi（CLI 工具） | 万物云（服务端平台） |
|------|---------------|---------------------|
| 部署形态 | npm 包，开发者本机跑 | K8s 多实例服务端部署 |
| 运行时 | Node / Bun | Python (uvicorn/FastAPI) |
| 状态存储 | 本地文件系统（AGENTS.md） | Postgres（checkpoint）+ pgvector（记忆）+ Redis（锁/信号） |
| 多实例 | 无（单机单进程） | 必然多实例（C 端） |
| 并发隔离 | 无（一个用户一个进程） | thread_id 维度 Redis 锁 |
| 权限隔离 | 容器化（Gondolin/Docker/OpenShell） | 服务端鉴权 + 工具权限审计 middleware |
| HITL | 无内置 | interrupt_before（静态） |
| RAG | 无（读文件系统） | pgvector 向量检索 |
| 限流重试 | 无（本地调，自己控制频率） | RateLimiter+retry+max_concurrency 三层 |
| 供应链加固 | npm pin+min-release-age+shrinkwrap | pip 锁版本+镜像扫描+base image 固定 |
| checkpointer | 无（coding agent 无状态恢复需求） | PostgresSaver + TTL |

**一句话总结**：pi 是"单机开发工具"，工程化重点是**供应链安全 + 发布流程**；万物云是"多实例服务平台"，工程化重点是**状态共享 + 并发隔离 + 限流容错 + 部署架构**。两者在"依赖锁定、漏洞扫描、版本管理"上有思想对标，但部署形态完全不同。

---

### 4. 对比表（万物云服务端 vs pi 工程化）

#### 生产坑对比

| 坑类型 | 万物云（服务端） | pi（CLI 工具） | 为什么不同 |
|--------|-----------------|---------------|-----------|
| 递归爆栈 | recursion_limit=25 兜底 🟢 | 无（coding agent 用户自己 Ctrl+C） | pi 本地跑，用户盯着，不需要自动止损 |
| 上下文膨胀 | 滑动窗口+摘要+外移 🟡 | AGENTS.md 文件式记忆 + session-resources 🟢 | pi 用文件系统卸载，万物云用向量库外移 |
| 并发写冲突 | Redis 锁 thread 串行 🔴 | 无（单进程单用户） | pi 不存在多实例多用户并发 |
| LLM 限流 | RateLimiter+retry+max_concurrency 🟢 | 无（本地单用户调，自己控制） | pi 不存在高并发打爆 API |
| 状态膨胀 | TTL+durability+DeltaChannel 🟢🔴 | 无（文件系统，用户自己清） | pi 状态在本地文件，万物云在共享 DB |
| 部署架构 | API Server+Worker+Postgres+Redis 🟢 | npm 包发布，无服务端 🟢 | 形态根本不同 |

#### 工程化对比

| 维度 | 万物云 | pi | 对标价值 |
|------|--------|-----|---------|
| 框架 | LangGraph StateGraph（Python）🟢 | 自研 agent harness（TypeScript）🟢 | 都自建编排，不直接用 SDK 黑盒 |
| 模型抽象 | init_chat_model 多 provider 🟢 | pi-ai 统一多 provider API 🟢 | 都抽象掉 provider 差异 |
| 工具协议 | MCP 自建（tools/list+tools/call）🟢 | 内置工具 + !commands | 万物云对标 MCP 标准，pi 自定义 |
| 记忆 | pgvector+similar merge+TTL 🟢 | AGENTS.md 文件式 🟢 | 服务端用向量库，CLI 用文件 |
| 可观测 | trace_id 跨实例+ELK 🟡🔴 | session 发布到 HuggingFace 🟢 | 万物云重线上排查，pi 重数据共享 |
| 发布 | K8s 滚动更新+灰度 🔴 | npm trusted publishing+lockstep 🟢 | 万物云重部署架构，pi 重供应链 |
| 权限 | 服务端鉴权+工具审计 middleware 🟢 | 容器隔离（无内置权限）🟢 | 万物云在应用层，pi 在容器层 |

---

### 5. 面试追问应答

#### Q1：生产遇到过什么坑？怎么解决的？

**应答框架**（讲 3 个，覆盖不同维度）：

"主要有三类坑。

**第一类是递归爆栈。** Agent 在 model→tool 循环里卡死，tool 报错→model 重试→又报错，烧 token。解法是 recursion_limit=25 框架兜底，触发 GraphRecursionError 时降级返回'任务太复杂转人工'，不直接抛 500 给用户。但 25 是最后兜底，真正止损靠第二层证据增量检测——第 2-3 轮没新证据就截断，不用等到 25 轮。

**第二类是并发写冲突。** 同一个用户双击'批准'或前端网络超时重发 resume，两个 run 同时改同一份 state，退款工具可能执行两次。解法是 Redis 分布式锁——锁 key 带 thread_id 维度，SET NX EX + Lua CAS 释放，拿不到锁返回 409。退款工具还配了 refund_id 幂等键双保险。注意我们是自托管 LangGraph 不是 LangSmith Agent Server，所以 double-texting 四策略我们没有，是自己加的 Redis 锁。

**第三类是 checkpoint 膨胀。** 每个 super-step 存全量快照，长对话+多用户 Postgres 磁盘一周爆。解法是 TTL 自动清理——配 default_ttl=30天，sweeper 定时扫过期 thread 删。踩过一个坑：TTL 只对新创建的 thread 生效，老数据不被清，得手动 DELETE。"

#### Q2：怎么部署的？并发怎么处理？

"部署是四组件：FastAPI 接请求（API 角色）+ 异步任务跑 graph（Worker 角色）+ Postgres 存 checkpoint 和长期记忆（pgvector）+ Redis 做分布式锁和 pubsub 信号。API 和 Worker 分开部署各自扩容——API 按读 QPS 扩，Worker 按 run 积压数扩。容器 stateless，数据全在 Postgres + Redis，扩缩容不丢数据。

并发处理分两层：
- **不同 thread_id 无竞争**，各跑各的，state 各存在 Postgres 不同行，不需要锁。用 async（ainvoke/astream）不阻塞事件循环，一个 worker 扛多并发 I/O（瓶颈是等 LLM 不是 CPU）。
- **同一 thread_id 才有竞争**，用 Redis 锁串行化，第二个请求 reject 返回 409。

LLM 是外部依赖有 API quota，高并发会 429。三层防护：InMemoryRateLimiter 令牌桶控速率、.with_retry 指数退避重试、max_concurrency 限并发数。园区级内部工具峰值 2-3 QPS，量级不大但必须控制对 LLM 的并发。"

#### Q3：recursion_limit 调多少？为什么？

"25，框架默认值。一次 model call + 一次 tool call = 2 个 super-step，25 步 ≈ 12 轮 tool 调用，对物业客服场景够用。太低（如 10）复杂任务做不完，太高（如 50）烧钱且延迟高。25 是业务调的平衡点。用框架自带的兜底并调了阈值。触发时降级不直接报错。"

#### Q4：和 pi 比有什么不同？

"pi 是 TypeScript coding agent CLI 工具，万物云是 Python 业务 agent 平台，形态完全不同。

**部署上**：pi 是 npm 包发给开发者本机跑，无服务端；万物云是 K8s 多实例服务端部署，有 API Server + Worker + Postgres + Redis 四组件。pi 不存在多实例并发问题，万物云必须处理 thread 级并发隔离。

**工程化重点不同**：pi 重供应链加固（npm pin 版本、min-release-age 防当天发布依赖、shrinkwrap 锁 transitive deps、npm audit 扫漏洞），因为它的产物发给开发者，恶意依赖会进开发者机器；万物云重状态共享+并发隔离+限流容错，因为是线上服务。

**架构思想有对标**：都用自建编排不直接用 SDK 黑盒（pi 自研 agent harness，万物云用 StateGraph+create_agent 自建）；都抽象掉 provider 差异（pi-ai 统一多 provider API，万物云 init_chat_model）；都做依赖锁定和漏洞扫描。但记忆机制完全不同——pi 用 AGENTS.md 文件式（coding agent 读文件系统），万物云用 pgvector 向量库（业务 agent 跨会话记忆）。"

#### Q5：TTL 配了为什么磁盘还涨？

"TTL 只对配置部署后新创建的 thread 生效，老 thread 的 checkpoint 不受影响。这是官方文档明确的。解法：①存量老数据手动 DELETE（按 created_at 过期）；②新 thread 会按 default_ttl 到期被 sweeper 清；③同时降 durability 到 exit/async 减少新增 checkpoint 量；④长对话考虑 DeltaChannel 只存增量（但 beta 阶段我们没上）。"

#### Q6：checkpointer 用什么？多实例怎么拉回？

"用 PostgresSaver（按真实讲，若实际是 Redis 封装说真实的）。所有实例连同一个 Postgres，state 在 DB 不在进程内存。请求打哪个实例都能用 thread_id 从 Postgres 拉回 checkpoint 恢复。InMemorySaver 只在本地测试用，生产多实例会拉不回。thread_id 要前端生成或网关分配并回传，不能后端每次随机，否则第二次 resume 找不回——等于 JSESSIONID 要 cookie 带回来。"

---

### 6. 万物云口径（按真实，三色标注）

| 维度 | 万物云口径 | 来源 |
|------|-----------|------|
| 框架 | StateGraph + create_agent 自建，没用 Deep Agents 🟢 | 🟢 万物云确认 |
| recursion_limit | =25，框架内置兜底，调了阈值 🟢 | 🟢 万物云确认 |
| concurrent-run 保护 | 自托管加自己 Redis 锁（不用 Agent Server 内置 double-texting）🔴 | 🔴 推断（未明确说用 Agent Server） |
| double-texting 四策略 | 🔴 不编（自托管若没用 Agent Server 则没有这四策略；用 Redis 锁实现 reject 等价语义） | 🔴 待核 |
| checkpointer 后端 | PostgresSaver 🟢（若实际是 Redis 按真实的改口述） | 🟢 面试技术准备手册 / 🔴 待用户确认 |
| checkpointer TTL | 配了 TTL 🟢 | 🟢 万物云确认 |
| 长期记忆 | pgvector + similar merge + TTL 🟢（不是 RedisStore / 不是 Deep Agents AGENTS.md） | 🟢 万物云确认 |
| 上下文压缩 | 滑动窗口/摘要是通用生产做法，万物云会用，具体策略 🔴 不编 | 🟡 通用 / 🔴 具体策略待核 |
| 限流重试 | 会用 RateLimiter+retry+max_concurrency 🟢，具体参数 🔴 待核 | 🟢 面试技术准备手册 |
| 部署模式 | FastAPI+任务队列+Postgres+Redis 四组件 🟢；具体 split API+queue 还是 single host 🔴 待核 | 🟢 面试手册 / 🔴 具体模式待核 |
| durability 模式 | 🔴 不编（没明确说用 sync/async/exit 哪个） | 🔴 待核 |
| DeltaChannel | 🔴 不编（beta 阶段，没明确说用没用） | 🔴 待核 |
| 人工审核 | interrupt_before（静态）🟢 | 🟢 万物云确认 |
| MCP | 自建（非官方 SDK，只 tools/list+tools/call 等价）🟢 | 🟢 万物云确认 |
| 可观测性 | RAGAS / Langfuse / LangSmith 只"了解"没用 🟢；自研 trace_id 跨实例 | 🟢 万物云确认 |

**核心口径一句话**：万物云自托管 LangGraph（StateGraph + create_agent），不是 LangSmith Agent Server。recursion_limit 用框架默认 25 🟢。concurrent-run 保护是自己加 Redis 锁 🔴（因为没用 Agent Server，框架本身没有 double-texting 四策略 🟢）。checkpointer 膨胀用 TTL 控制 🟢。长期记忆用 pgvector + similar merge + TTL 🟢，不是 Deep Agents 的 AGENTS.md。部署是 FastAPI + 任务队列 + Postgres + Redis 四组件 🟢。可观测靠 trace_id 跨实例 + ELK，LangSmith/Langfuse 只了解没用 🟢。

---

### 检查题（5 道）

**第1题**：万物云自托管 LangGraph，没有 LangSmith Agent Server。那么 Agent Server 的 double-texting 四策略（enqueue/reject/interrupt/rollback）万物云有吗？万物云怎么实现并发隔离？

> **答案要点**：🟢 double-texting 四策略是 Agent Server 商业版功能，OSS LangGraph 没有。🔴 万物云自托管没用 Agent Server，所以没有这四策略，自己加 Redis 锁实现 reject 等价语义（SET NX EX + Lua CAS 释放，拿不到锁返回 409）。锁 key 带 thread_id 维度——不同 thread 并行，同 thread 串行。退款这类副作用工具还要配 refund_id 幂等键双保险。面试要主动说"并发保护是自己加的，不是框架白送的"。

**第2题**：你配了 `checkpointer.ttl.default_ttl=43200`（30天）部署上线，一周后发现 Postgres 磁盘还在涨，查发现老 thread 没被清。为什么？怎么解决？

> **答案要点**：🟢 TTL 只对配置部署后**新创建**的 thread 生效，老 thread 的 checkpoint 不受影响（官方原文）。解决：①手动删老数据（DELETE FROM checkpoints WHERE created_at < ...）；②新 thread 会按 default_ttl 到期被 sweeper 清；③降 durability 到 exit/async 减少新增 checkpoint 量；④长对话考虑 DeltaChannel 只存增量（beta，没上线先用 TTL）。万物云口径：配了 TTL 🟢，具体是 langgraph.json 配还是自己跑 cron 🔴 待核。

**第3题**：高并发时 LLM API 返回大量 429，你的 Agent 全线崩溃。官方给了哪三种限流手段？各管什么？万物云用吗？

> **答案要点**：🟢 三种：①InMemoryRateLimiter（客户端令牌桶，控制发往 LLM 的请求速率，requests_per_second + max_bucket_size）；②.with_retry(stop_after_attempt=N)（指数退避重试，429 时自动重试）；③max_concurrency（并发上限，限制同时发出的请求数）。三层各管：RateLimiter 管速率、retry 管容错、max_concurrency 管并发数。类比 Sentinel 限流 + Spring @Retryable 重试 + JUC Semaphore 并发控制。🟢 万物云作为生产系统会用（面试手册确认"LLM 调用并发控制避免打爆 429"），🔴 具体参数按实际 quota 讲。

**第4题**：万物云部署架构有哪几个组件？API Server 和 Queue Worker 为什么分开？容器为什么说是 stateless 的？

> **答案要点**：🟢 四组件：API Server（接 HTTP 请求，不跑 graph）+ Queue Worker（跑 graph 代码，写 checkpoint）+ Postgres（存所有持久数据 thread/run/checkpoint/store）+ Redis（存 ephemeral 信号 + pubsub + 锁，不存用户数据）。分开的原因：①异步削峰（LLM 慢，API 接请求不等跑完，丢给 Worker 异步执行）；②职责不同扩容维度不同（API 按读 QPS 扩，Worker 按 run 积压扩）；③状态持久化（state 在 Postgres 不在进程内存）。容器 stateless = 数据全在 Postgres + Redis，容器本身不存状态，扩缩容不丢数据。🟢 万物云 FastAPI+任务队列+Postgres+Redis 四组件确认；🔴 具体是否 split API+queue 模式待核。

**第5题**：pi 和万物云在工程化上有什么相同和不同？为什么？

> **答案要点**：相同点（思想对标）：都自建编排不直接用 SDK 黑盒（pi 自研 harness，万物云 StateGraph 自建）；都抽象掉 provider 差异（pi-ai 统一 API，init_chat_model）；都做依赖锁定+漏洞扫描。不同点（形态不同）：pi 是 CLI 工具发给开发者本机跑，无服务端部署，工程化重供应链加固（npm pin/min-release-age/shrinkwrap/npm audit）；万物云是 K8s 多实例服务端部署，工程化重状态共享（PostgresSaver）+并发隔离（Redis 锁）+限流容错（三层）+部署架构（四组件）。原因：pi 单机单用户无并发问题，万物云 C 端多实例有状态必须处理分布式问题。记忆机制也完全不同——pi 用 AGENTS.md 文件式（coding agent 读文件系统），万物云用 pgvector 向量库（业务 agent 跨会话记忆）。这是架构思想对标不是代码移植。

---

## 块7：综合对比总表 + 面试追问清单 + 数字口径 + 陈述模板

> 定位：前 6 块讲"万物云怎么写 + 怎么对标 pi"，这块是面试冲刺速查--一张大对比表 + 20 条追问应答 + 数字口径 + 可背陈述模板。
> 诚实边界贯穿全文：🟢 官方/已确认　🟡 后端类比/通用 spec/重述　🔴 推断待核。🔴 项被追问时口述"推断依据 / 待确认"，绝不编。
> 后端类比对象：Spring / Activiti / Redis / SseEmitter / JUC / RabbitMQ（你是 Java 后端转 AI）。

---

### 一、万物云 vs pi 大对比表（12 维度）

| 维度 | 万物云 | pi | 口径标注 |
|---|---|---|---|
| **定位** | 园区智能客服 / 座席辅助 Agent 平台（业务 agent） | TypeScript coding agent 工具链（类 Claude Code，7.1 万星） | 双方🟢已确认 |
| **语言** | Python | TypeScript | 双方🟢 |
| **编排方式** | LangGraph StateGraph 图级编排（节点=函数/LLM/agent/子图，条件边硬路由） | 进程级编排（无内置 sub-agents，靠 tmux spawn / RPC / extension 自建调度） | 万物云🟢框架 / 🔴归类 Custom workflow 推断；pi🟢官方 Philosophy |
| **状态管理** | 共享 State（TypedDict，所有节点读写同一对象）+ Checkpointer 持久化（thread_id + 版本化 checkpoint） | 进程内 AgentState 对象（直接赋值改）+ JSONL session 文件（tree 结构 id/parentId） | 双方🟢；万物云 checkpointer 后端🔴待确认 |
| **记忆** | pgvector + similar merge + TTL（LangGraph Store API，按需语义召回 top-K） | AGENTS.md 文件（启动整份加载进 system prompt）+ session JSONL（会话级） | 万物云🟢主体 / 🔴cron 实现；pi🟢 |
| **RAG** | 三类节点管线（Rewrite/Retrieve/Agent），pgvector 向量召回 + BM25 + RRF + Rerank | 无（coding agent 用 read/grep/find 直接读文件系统） | 万物云🟢编排思想 / 🔴深度待核；pi🟢 |
| **HITL** | interrupt_before（静态断点）+ Command(resume=) 恢复（两次 HTTP 往返） | 无内置（Philosophy "No permission popups"，靠 extension 自建 confirmation flow） | 万物云🟢；pi🟢 |
| **MCP** | 自建非官方 SDK，只 tools/list + tools/call 等价（不用 Resources/Prompts） | 明确 "No MCP"（用 CLI 工具 + Skills README 代替，或 extension 加） | 双方🟢 |
| **权限/沙箱** | 角色 + 接口鉴权（ToolGuardMiddleware 拦危险工具 + API 网关 token），无文件沙箱（业务 agent 不跑代码） | 无内置权限系统，靠容器（Gondolin / Docker / OpenShell）隔离文件/进程/网络 | 万物云🔴推断；pi🟢官方 |
| **部署** | K8s 多实例服务端（FastAPI + 任务队列 + Postgres + Redis 四组件，容器 stateless） | npm CLI 包，开发者本机跑，Node/Bun 双打包，无服务端 | 万物云🟢四组件 / 🔴具体 split 模式待核；pi🟢 |
| **适用场景** | 业务 agent：客服/工单/退款，操作不可逆要审核，知识非结构化要 embed 检索 | coding agent：读写文件/跑命令，操作可重做可 git 回滚，知识就是文件系统 | 双方🟡场景重述 |
| **规模** | 日均~3000 次 / 峰值 2-3 QPS / 月~2.7 亿 token / 月成本数百至近千元 | 单机单用户，无规模数字（npm 包发给开发者） | 万物云🟢；pi🟢 |

> 一句话总结差异：**万物云是业务 agent 平台（调 API、要审批、靠鉴权、线上多实例），pi 是 coding agent 工具链（跑命令、自主跑、靠容器、本地单机）**。两者架构选择都被场景驱动--业务操作不可逆要 HITL，coding 操作可重做靠容器兜底；业务知识在库里要 RAG，coding 知识在文件里直接读。对标是**架构思想对标不是代码移植**🟡。

---

### 二、面试追问清单（20 条）

格式：问 -> 一句话应答 -> 深度备弹要点 3-5 条。

#### A. 架构类（5 条）

**Q1：你的多 Agent 怎么协作？状态怎么共享？**
> 应答：万物云用 LangGraph StateGraph 做图级编排，多个 agent 各自是一个节点，协作靠共享 State--一个类型化 TypedDict，所有节点读写同一个 State 对象，不是消息传递。

备弹要点：
1. State 字段分 4 类：messages（短期记忆，add_messages 累加）/ 当前阶段 intent（驱动条件路由）/ 记忆引用 user_id（拉长期记忆）/ 审核状态 review_status 🟢
2. 状态共享不需要 agent 之间发消息，是图引擎提供的共享内存--类比 Activiti 流程变量，节点 setVariable 下游直接读 🟡
3. classify 节点把意图写进 state["intent"]，条件边读 intent 路由到 query_agent 或 refund_node，下游直接看到不用重新问 🟢
4. 这和 pi 的进程级编排是两个范式：pi 各进程独立 AgentState 靠 RPC 消息传，无共享 state 🟢

**Q2：Supervisor 模式怎么实现？为什么不用官方 Subagents？**
> 应答：我们不是标准 Subagents/Supervisor（主 agent 把子 agent 包 @tool、LLM 动态调度），是 Custom workflow StateGraph--分类节点扮演路由职责，但路由决策写在 add_conditional_edges 条件边里是硬的确定性的，不让 LLM 临场决定调谁。

备弹要点：
1. 万物云 multi-agent = Custom workflow（StateGraph）是🔴推断，基于 StateGraph + interrupt_before + create_agent 三条已确认事实，源文档没明确归类，被追问口述"基于这三点推断"🔴
2. 不用 Subagents 原因：主 agent LLM 调度本身耗调用且不可控，业务流程是确定性编排（先查单->分析->报告），要硬路由不要 LLM 临场决策 🟡
3. 不用 Handoffs middleware：那是"一个 agent 切配置"不是真多 agent，万物云要不同节点装不同 agent 职责彻底隔离 🟡
4. 一句话：Subagents/Handoffs 是"让 LLM 当调度员"，万物云要"让图当调度员"--路由写在条件边里是硬的、可测的、不烧 token 的 🟡
5. 官方提醒：not every complex task requires multi-agent，单 agent 配对工具和 prompt 往往够用，别为 multi-agent 而 multi-agent 🟢

**Q3：路由用什么实现？add_conditional_edges 还是 Command(goto)？**
> 应答：主要用 add_conditional_edges 条件边硬路由，这是万物云 multi-agent 路由的主要机制。

备弹要点：
1. add_conditional_edges = Activiti 排他网关 XOR，按 route 函数返回值走对应边，不耗 LLM 调用 🟢🟡
2. 是否同时用 Command(goto=...) 做路由🔴待核--已确认主要用条件边，Command(goto) 没确认不编 🟢条件边 / 🔴Command(goto)
3. Command 有三种用法要分清：Command(goto=) 和 Command(update=) 是节点函数 return 用的；Command(resume=) 是唯一能作 invoke() 输入的 🟢
4. 被追问"有没有用 Command(goto)"口述："主要用条件边，Command(goto) 是否用过我确认下"，别瞎称 🔴

**Q4：状态怎么持久化？跨 turn 怎么恢复？**
> 应答：state 存 Checkpointer--LangGraph 内置持久化机制，每个 thread 一个 thread_id，图每跑完一个节点存一个版本化 checkpoint，跨 turn 用同一个 thread_id 拉回。

备弹要点：
1. checkpointer 后端🔴待确认（PostgresSaver 还是 Redis）--口径"用持久化后端多实例共享 state，具体我确认下"，别瞎称 PostgresSaver 被表结构追问翻车 🔴
2. 跨 turn 恢复机制：interrupt_before 暂停 -> state 落 checkpointer -> HTTP 早返回 -> 人工确认后第二次 invoke 传 Command(resume=) + 同 thread_id 拉回 🟢
3. 两次 HTTP 往返不是一次连接挂着：state 不在连接里不在进程内存，在 checkpointer 后端，人工想 5 分钟第二天都行（只要 checkpoint 那行没被 TTL 清）🟢
4. InMemorySaver 多实例拉不回（请求打到不同实例），C 端生产必须外部存储 🟢
5. thread_id = JSESSIONID / processInstanceId，要前端生成或网关分配并回传，不能后端每次随机 🟡

**Q5：一个 LangGraph node 可以是哪几种？万物云图里各属哪种？**
> 应答：node 可以是 4 种：确定性函数 / LLM 调用 / agent（create_agent）/ 子图。万物云客服图里 classify 是确定性函数节点、query_agent 是 agent 节点、refund_node 是执行写入的函数节点。

备弹要点：
1. 官方原话：可以在任何 LangGraph node 里直接调 LangChain agent 🟢
2. 关键认知：不是所有节点都要 LLM。Retrieve 是确定性的（同 query 同结果可复现可测试），Rewrite 和 Agent 才调 LLM 🟢
3. 把确定性的留确定性、该智能的才智能，是图编排核心思想 🟢
4. 后端类比：node = Activiti serviceTask/scriptTask，节点函数读 state/return 更新 state = execution.setVariable 🟡

#### B. 技术深度类（5 条）

**Q6：agent loop 怎么防死循环？三层防护各管什么？**
> 应答：三层防护。第一层 recursion_limit=25 框架兜底防停不下来；第二层证据增量检测防原地打转；第三层多步检索最多 3 跳防无限深挖。

备弹要点：
1. 第一层 recursion_limit=25：LangGraph 自带 super-step 上限，口径"用框架自带兜底并调了阈值"，25 是复杂度 vs 成本平衡点 🟢
2. 第二层证据增量检测：每次工具返回后检查 scratchpad 有没有新信息，连续两次无实质区别=原地打转，注入换思路提示，重复 2 次强制结束 🟢
3. 第三层多步检索 3 跳：防 RAG 无限深挖（结果一直在变但跟问题无关），到 3 跳强制停用已有信息综合回答 🟢
4. 为什么不只靠第一层：25 轮触发时已烧 25 次模型调用 + 25 次工具执行，第二三层能在第 2-3 轮提前止损 🟡
5. 撞到 recursion_limit 不能直接报错，要 except GraphRecursionError 返回降级文案转人工 🟡

**Q7：长期记忆怎么做的？为什么不用 Redis/AGENTS.md？**
> 应答：长期记忆用 pgvector + similar merge + TTL，跑在 LangGraph Store API 上。pgvector 复用已有 Postgres 运维栈且支持语义检索；Redis 适合短期缓存不做长期记忆；AGENTS.md 是文件壳启动整份加载会爆 token。

备弹要点：
1. similar merge：写记忆前先语义搜同 namespace 下有没有高度相似的（cosine ≥ 阈值），有就合并（put 同 key 覆盖），无就新建，防重复记忆占满召回 🟢主体 / 🔴具体算法待核
2. TTL：官方 Store 没有内置过期机制（created_at/updated_at 只是时间戳不自动删数据），万物云自建 cron 按 updated_at + ttl_days 判断过期并 delete 🔴
3. Store vs Checkpointer 区别：checkpointer 是 thread-scoped（换 thread 隔离）；store 是 cross-thread（namespace 带 user_id 跨 thread）🟢
4. 用户跨会话偏好（如"花生过敏"）必须存 store，下次会话用当前消息做 query 语义召回塞进 system prompt 🟢
5. 不用 RedisStore🟢确认；不用 Deep Agents AGENTS.md🟢确认；记忆按 user_id namespace 隔离🔴推断（路径 A 标准模式）

**Q8：上下文工程怎么做？工具定义占 token 吗？**
> 应答：上下文工程管模型每轮看到的 5 部分（System prompt + 历史 messages + 工具定义 + 检索结果 + 长期记忆）。工具定义每轮都发，是最常被漏算的大头。

备弹要点：
1. 一个工具约 100-150 token，12 个 Skill ≈ 1500-2000 token/轮，20 轮就 4 万 token 光花在工具定义上 🟢
2. 三种解法组合用不能单用：裁剪（删旧消息留最近 N）/ 摘要（小模型压旧消息成摘要）/ 外移（存外部只留指针）🟡
3. 裁剪不能单独用：用户最早说的订单号被裁掉，后面模型问"订单号是什么"用户体验崩，必须配合摘要或外移 🟢
4. 万物云配方：滑动窗口 + SummarizationMiddleware（按 token 触发累积摘要用小模型）+ 关键事实外移 Store + checkpointer 配 TTL 🟡通用做法 / 🔴具体策略待核
5. SummarizationMiddleware 放 before_model 钩子，按 token 不按轮数触发（一轮可能 50 也可能 5000 token），累积摘要每次【上次摘要+新消息】一起摘产出 1 条替换旧的 🟢

**Q9：similar merge 具体怎么合并？阈值怎么定？**
> 应答：写记忆前先 store.search(ns, query=text, filter={category}) 语义搜相似，取 score 最高的；若 score ≥ SIM_THRESHOLD 就合并--用原 key 调 put 覆盖（put 是 store or overwrite 语义），把新 text 并进原 value。

备弹要点：
1. 不 merge 的后果：用户三次说"喜欢简洁回答"记忆库就三条几乎一样的，召回时 top-K 全被占满把别的有用记忆挤掉，退化成垃圾场 🟢
2. 合并算法：简化版是拼接（best.text + "\n---\n" + text），生产版可让 LLM 做语义合并去重🔴（万物云具体用哪个待核）🟢机制 / 🔴算法
3. 阈值 SIM_THRESHOLD🔴业务调参官方无默认值：设高了漏合并（重复记忆），设低了误合并（丢信息），要在 golden set 上调 🟡
4. search 的 query 走向量语义召回，filter 走等值过滤，两者可叠加先 filter 收窄类别再语义搜提高精度 🟢
5. search 返回的 item 带 score（cosine 相似度），取 max(hits, key=score) 🟢

**Q10：工具调用可靠性怎么保证？三道闸是什么？**
> 应答：三道闸：args_schema 参数校验（防假参数）+ 失败处理不抛异常返回错误 JSON 带 retryable（防崩循环）+ ToolMessage 闭合 tool_call_id 配对（防结果错配）。加 tool_choice=required 首轮强制调工具，是防幻觉四道闸。

备弹要点：
1. args_schema = Pydantic Model + @valid，执行前拦，校验失败抛 ValidationError 工具根本不执行，错误信息回给模型 🟢
2. 万物云踩过的坑：没加 order_id 格式校验时模型编了不存在的订单号，工具查库返回空，模型又对着空结果编了订单状态（幻觉），加校验后假号在门口被拦幻觉从源头断了 🟢
3. 失败处理：工具内部 try/except 把异常转成 {"error","hint","retryable"} 返回，不抛异常冒泡中断循环 🟢
4. retryable=是否值得重试（超时 true 可重试 / 参数错 false 不可重试），没它模型对不可重试错误无限重试只能靠 recursion_limit 硬停 🟡
5. 和 pi 区别：pi 工具 throw error 框架捕获转 isError:true（标准化）；万物云工具自己 catch 返回 error JSON（能塞 hint/retryable 业务字段更灵活）🟡

#### C. 生产实战类（5 条）

**Q11：生产遇到过什么坑？讲三个不同维度的。**
> 应答：三类坑。第一类递归爆栈（recursion_limit 兜底）；第二类并发写冲突（Redis 锁串行化）；第三类 checkpoint 膨胀（TTL 清理）。

备弹要点：
1. 递归爆栈：tool 报错->model 重试->又报错无限转烧 token，解法 recursion_limit=25 + 降级返回"转人工"不抛 500 🟢
2. 并发写冲突：同一 thread_id 双击"批准"两个 run 同时改 state 可能退款两次，解法 Redis 锁（SET NX EX + Lua CAS 释放）拿不到锁返回 409，退款还配 refund_id 幂等键双保险 🔴自建锁推断
3. checkpoint 膨胀：每 super-step 存全量快照长对话+多用户 Postgres 磁盘一周爆，解法 TTL 自动清理 + 踩坑 TTL 只对新 thread 生效老数据要手动删 🟢TTL / 🔴具体清理方式
4. 关键口径：万物云自托管 LangGraph 不是 LangSmith Agent Server，double-texting 四策略（enqueue/reject/interrupt/rollback）是 Agent Server 商业版功能 OSS 没有，万物云自己加 Redis 锁实现 reject 等价 🟢边界 / 🔴自建锁
5. LLM 429 也是常见坑：高并发打爆 API quota，三层防护 RateLimiter + retry + max_concurrency 🟢

**Q12：怎么部署的？四组件为什么分开？**
> 应答：四组件：FastAPI 接请求（API 角色）+ 异步任务跑 graph（Worker 角色）+ Postgres 存 checkpoint 和长期记忆（pgvector）+ Redis 做分布式锁和 pubsub 信号。分开是因为 LLM 慢要异步削峰、职责不同扩容维度不同、状态要持久化不在进程内存。

备弹要点：
1. API 按读 QPS 扩（接请求快），Worker 按 run 积压数扩（跑 graph 慢），各自扩容更高效 🟢
2. 容器 stateless：数据全在 Postgres + Redis，扩缩容不丢数据 🟢
3. Redis 只存 ephemeral 信号（run 状态/pubsub/锁）不存用户数据，用户数据全在 Postgres 🟢
4. 官方 Split 模式：API Server 和 Queue Worker 是同一 Docker image 不同启动命令（langgraph-api vs langgraph-queue-worker）🟢
5. 万物云具体是 split API+queue 还是 single host🔴待核；FastAPI+任务队列+Postgres+Redis 四组件🟢确认 🟢/🔴

**Q13：并发写冲突怎么解决？为什么用 Redis 锁不用框架的？**
> 应答：用 Redis 分布式锁做 thread 维度串行化--锁 key 带 thread_id，SET NX EX + Lua CAS 释放，拿不到锁返回 409。因为万物云自托管 LangGraph 不是 Agent Server，框架本身没有 double-texting 四策略，得自己加。

备弹要点：
1. 核心规则 1-run-per-thread：同一 thread_id 同时只能一个 run，不同 thread_id 无竞争各跑各的 🟢
2. 锁粒度是 thread_id 维度不是全局锁--全局锁所有请求串行并发上不去 🟢
3. Agent Server 内置 4 策略（enqueue 默认/reject 409/interrupt 暂停/rollback 回滚）是 LangSmith Deployment 功能 OSS 没有 🟢
4. 万物云自托管没用 Agent Server🔴推断，所以没有这四策略自己加 Redis 锁实现 reject 等价 🟢边界 / 🔴自建锁
5. 退款这类副作用工具还要配 refund_id 幂等键双保险--锁防并发，幂等键防重放 🟡

**Q14：LLM 429 限流怎么处理？三层防护各管什么？**
> 应答：三层防护。InMemoryRateLimiter 令牌桶控速率（每秒几个）、.with_retry 指数退避重试（429 后重试）、max_concurrency 限并发数（同时几个）。一个防打爆、一个防偶发、一个防积压。

备弹要点：
1. RateLimiter 类比 Guava RateLimiter.create(2.0) + Semaphore(10) / Sentinel 🟡
2. .with_retry(stop_after_attempt=5) 类比 Spring @Retryable(maxAttempts=5, backoff=@Backoff(delay=1000, multiplier=2)) 🟡
3. max_concurrency 类比 JUC Semaphore permits，在 evaluation/批处理场景用 🟡
4. 万物云作为生产系统会用🟢（面试手册确认"LLM 调用并发控制避免打爆 429"），具体参数🔴按实际 quota 讲 🟢/🔴
5. 园区级内部工具峰值 2-3 QPS 量级不大但必须控制对 LLM 的并发 🟢

**Q15：checkpointer 膨胀怎么清理？TTL 配了为什么磁盘还涨？**
> 应答：用 TTL 自动清理--配 default_ttl=30 天，sweeper 定时扫过期 thread 删。踩过的坑：TTL 只对配置部署后新创建的 thread 生效，老 thread 不受影响得手动删。

备弹要点：
1. 官方原文：TTLs are applied to threads and checkpoints when they are created. They do not apply to existing threads 🟢
2. 老数据手动删：DELETE FROM checkpoints WHERE created_at < NOW() - INTERVAL '30 days' 🟡
3. 三层防线：durability 降级（exit 只存最终/async 默认异步/sync 同步最安全）+ TTL 自动清理 + DeltaChannel 只存增量（beta 没上线）🟢TTL / 🔴durability+DeltaChannel
4. 万物云配了 TTL🟢确认；具体是 langgraph.json 配还是自己跑 cron🔴待核（自托管可能不走 langgraph.json）🟢/🔴
5. per-thread TTL 能给 VIP 用户对话保留久一点：client.threads.create(ttl={...}) 🟢

#### D. 对比类（5 条）

**Q16：和 pi 比有什么根本不同？**
> 应答：pi 是 TypeScript coding agent CLI 工具发给开发者本机跑，万物云是 Python 业务 agent 平台 K8s 多实例服务端部署。形态完全不同，对标是架构思想对标不是代码移植。

备弹要点：
1. 部署：pi 是 npm 包无服务端，万物云是 API Server+Worker+Postgres+Redis 四组件 🟢
2. 工程化重点：pi 重供应链加固（npm pin/min-release-age/shrinkwrap/audit），万物云重状态共享+并发隔离+限流容错 🟢
3. 架构思想有对标：都自建编排不直接用 SDK 黑盒；都抽象掉 provider 差异（pi-ai 统一 API / init_chat_model）；都做依赖锁定漏洞扫描 🟡
4. 记忆机制完全不同：pi 用 AGENTS.md 文件式（coding agent 读文件系统），万物云用 pgvector 向量库（业务 agent 跨会话记忆）🟢
5. pi 无内置 HITL/权限/RAG/MCP🟢官方 Philosophy；万物云这四层都自建因为业务场景需要 🟢/🔴

**Q17：万物云的记忆和 pi 的 AGENTS.md 有什么本质区别？**
> 应答：pi 用 AGENTS.md 文件启动整份加载进 system prompt（always loaded），文件大了爆 token；万物云用 pgvector Store 按需语义召回 top-K 省 token，还有 similar merge 去重和 TTL 清理。

备弹要点：
1. pi 记忆三层都是会话级或文件级：AGENTS.md（启动加载指令文件）+ session JSONL（会话历史）+ session-resources（会话级资源），没有跨会话语义检索长期记忆 🟢
2. 万物云按需语义召回：每轮用当前消息做 query 召回 top-K 相关记忆塞进 system prompt，不是全量塞 🟢
3. similar merge 语义去重🟢/🔴算法待核；TTL cron 清理🔴（官方 store 无内置 TTL）；pi 都没有 🟢
4. 本质区别根因：pi 是 coding agent 知识就是文件 read 直接读；万物云是业务 agent 客服知识/规范非结构化必须 embed 才能语义召回 🟢
5. pi 的 Compaction（/compact 摘要压缩）和万物云 SummarizationMiddleware 是同一思想（摘要旧消息保留近期），都按 token 触发有损，差异是 pi 完整历史在 JSONL 文件万物云在 checkpointer 🟢

**Q18：万物云和 pi 的 tool calling 有什么不同？**
> 应答：两处主要差异。一是错误处理位置：pi 工具 throw error 框架捕获转 isError:true（标准化）；万物云工具自己 try/except 返回带 error/hint/retryable 的错误 JSON（能塞业务字段更灵活）。二是校验库：pi 用 TypeBox（TS 生态），万物云用 Pydantic（Python 生态），都是 JSON Schema 校验。

备弹要点：
1. pi 有 beforeToolCall preflight hook 能 block 工具执行，等价万物云 ToolGuardMiddleware wrap_tool_call 🟢
2. pi 的 validateToolCall 用 TypeBox schema 校验，等价万物云 args_schema（Pydantic Model）🟢
3. 两者工具并发默认都是 parallel（并发执行同一批 tool_calls），pi 还可选 sequential 🟢
4. pi 有 terminate:true（工具暗示停不用再调 LLM）/ shouldStopAfterTurn（优雅停），万物云靠条件边路由到 END + recursion_limit 实现等价 🟢
5. 万物云多一道 tool_choice=required 首轮强制调工具防"不查就编"，pi 无此机制（coding agent 自主决定）🟢

**Q19：为什么万物云不用 pi 那种进程级方案？**
> 应答：场景不同。pi 是 coding agent 任务探索性流程不固定，进程隔离+文件系统足够；万物云是业务 agent 流程确定性（分类->查询->审核->执行），要硬路由+人工审核+共享流程变量+跨 turn 恢复，这些 StateGraph 开箱即用，进程级方案要自己造图引擎。

备弹要点：
1. pi 明确"No sub-agents"（Philosophy 节），把"多 agent 怎么协作"甩给用户：开多个 pi 进程（tmux）+ RPC（stdin/stdout JSONL）+ extension 自建调度 🟢
2. pi 各进程独立 AgentState 无共享 state，靠 RPC 消息传字符串 🟢
3. 万物云要的：条件边硬路由（可测不烧 token）+ interrupt_before 人工审核 + 共享 State 流程变量 + checkpointer 跨 turn 恢复，StateGraph 开箱即用 🟢
4. 进程级方案要自己写调度逻辑、自己管状态共享、自己做条件路由，等于重新造个图引擎 🟡
5. pi-orchestrator 包本身是实验性 stub（README 只有 3 行有效内容），没暴露 supervisor.ts/RPC/storage 的 API 细节🟢已读，不编 🟢

**Q20：pi 无内置 HITL/权限/RAG/MCP，万物云为什么都需要？**
> 应答：场景决定的。业务操作不可逆（退款错了追不回）要 HITL；业务 agent 调 API 要角色鉴权不是文件沙箱；客服知识非结构化要 RAG 语义检索；业务工具是远程服务要 MCP 协议层动态发现。coding agent 操作可重做可 git 回滚靠容器兜底就行。

备弹要点：
1. HITL：万物云 interrupt_before 在退款/改价执行前暂停等人工🟢；pi "No permission popups"靠容器隔离跑炸了不烧宿主机🟢 🟢双方
2. 权限：万物云角色+接口鉴权（ToolGuardMiddleware 拦危险工具+网关 token）无文件沙箱🔴推断；pi 无内置权限靠容器（Gondolin/Docker/OpenShell）🟢 🟢pi/🔴万物云
3. RAG：万物云 pgvector 向量检索客服知识🟢；pi 无 RAG 用 read/grep 直接读文件系统🟢 🟢双方
4. MCP：万物云自建 tools/list+tools/call 等价🟢；pi "No MCP"用 CLI 工具+Skills README🟢 🟢双方
5. 根因：coding agent 的工具是本地 CLI（同进程就够），业务 agent 的工具是远程服务（需要协议层）；coding 知识在文件里直接读，业务知识在库里要 embed 🟡

---

### 三、数字口径备忘表（按边界 12）

| 指标 | 值 | 口径 / 怎么算 / 标注 |
|---|---|---|
| **Agent 日均调用** | 约 3000 次 | 🟢 园区级内部工具，服务座席/管理员，按 trace_id 统计；不是上限是真实使用量 |
| **峰值 QPS** | 约 2-3 QPS | 🟡 工作时段集中；Agent 瓶颈是 LLM 推理不是吞吐，QPS 本不高 |
| **月 token 量** | 约 2.7 亿 | 🟡 加权均约 3k token/次 × 3000 次/天 × 30 天 |
| **月成本** | 数百元至近千元 | 🟡 DeepSeek 定价估算 |
| **单次 token** | 简单 1-2k / 复杂 5-15k | 🟡 简单=意图分类+一次生成；复杂=多次 LLM 调用 |
| **端到端延迟** | 简单 2-4s / 复杂 5-10s | 🟡 瓶颈是 LLM 推理 |
| **复杂任务成功率** | 约 70% | 🟡 150 条评测样本正确完成占比，人工+LLM-judge |
| **意图分类准确率** | 约 88% | 🟡 离线样本测的小模型分类准确率 |
| **Skill 数** | 约 12 个 | 🟢 咨询/报修/工单/访客/车辆/告警等 |
| **recursion_limit** | 约 25 | 🟢 框架自带兜底，万物云调了阈值 |
| **IoT 设备消息吞吐** | 约 2000 条/秒 | 🟢 万物云 IoT PaaS 项目，设备消息上报吞吐（**非用户请求并发**） |

> ⚠️ **关键区分（别穿帮）**：万物云 Agent 平台的"约 3000 次/天、2-3 QPS"是**用户请求量级**；万物云 IoT PaaS 项目的"约 2000 条/秒"是**设备消息上报吞吐**（万余台设备心跳/遥测聚合）。**两个项目的数字别混**。被追问"2-3 QPS 和 2000 条/秒怎么差这么多"答："那是两个项目，Agent 平台是用户请求 QPS，IoT 是设备消息上报吞吐，不是一个量纲。"🟢（边界 12）

> 数字记忆法：3000 次/天 → 3k token/次 → 2.7 亿/月 → 数百至近千元/月。四个数一条链，背一个串一串。

---

### 四、项目陈述模板

#### 30 秒电梯版（直接背）

> "我做的是万物云的园区运营助手 Agent 平台，用 LangGraph 的 StateGraph 做多 Agent 编排。把物业咨询、报修、工单查询这些业务能力封装成大约 12 个 Skill 给 Agent 调。用户提问进来，先经意图分类加规则风险标记做条件路由，简单查询走单 Agent，跨域或写入类走多 Agent 协作链路--Supervisor 拆任务、Executor 用 ReAct 调 Skill、需要知识走 RAG 检索、写入动作前用 interrupt_before 暂停等人工确认，确认后用 Command resume 恢复。短期记忆靠 Checkpointer 按 session 续接，长期记忆用 pgvector 做相似合并加 TTL 治理。日均约 3000 次调用，复杂任务成功率约 70%。我在团队是核心开发，负责多 Agent 编排链路和工具接入层这两块的设计和实现。"

#### 3 分钟深入版（四段，按时间背）

> **（0-30s）定位与规模**：万物云园区运营助手 Agent 平台，服务园区座席和管理员，日均约 3000 次调用，峰值 2-3 QPS--Agent 类应用瓶颈是 LLM 推理不是吞吐，量级本来就不大。月 token 约 2.7 亿，成本几百到近千元。
>
> **（30-90s）编排核心**：编排用 LangGraph StateGraph，本质是个图执行引擎，类比 Activiti。我定义了一个共享 State--messages 用 add_messages 累加，加意图、槽位、plan、scratchpad、risk_flags、allowed_skills 这些结构化字段。每个 Agent 是图上一个 node。意图分类后用条件边路由：简单查询走单 Agent，跨域或写入类走多 Agent 链路。多 Agent 用 Supervisor 模式--Supervisor 节点用 LLM 决定下一步调哪个 worker，循环到 FINISH；Executor 内部是 ReAct 循环调 Skill。
>
> **（90-150s）生产化关键件**：写入类动作前用 interrupt_before 静态暂停，state 落 Checkpointer，HTTP 请求结束返回前端，用户确认后发新请求带 Command(resume=) 读档续跑--这是跨请求的中断恢复，不是线程 await。短期记忆靠 Checkpointer 按 thread_id 续接多轮，长期记忆用 pgvector 存用户常用园区、关注设备、历史工单摘要，做相似合并去噪加 TTL 淘汰。工具层是自建的 MCP 等价实现--只做了 tools/list 和 tools/call，加了鉴权审计和懒加载，没接官方 SDK。
>
> **（150-180s）可观测与角色**：可观测是自研 trace_id 串全链路--用户原始问题、意图分类、槽位、Skill 调用链、推理摘要、异常原因，因为园区数据不能出公网所以没用 Langfuse。搭了约 150 条评测样本，复杂任务成功率约 70%，主要失败在槽位歧义和跨域拆解。我在团队是核心开发不是 owner，整体架构 lead 拍板，我主导设计了多 Agent 协作链路和工具接入层这两个子模块。

---

### 五、诚实边界速查（🔴 项汇总，面试照这个讲）

> 这一节是"哪些是确认的、哪些是推断待核"的清单。被追问到细节时照标注讲，别把🔴推断说成已确认。

| # | 项 | 口径 | 标注 |
|---|---|---|---|
| 1 | 生产框架 | 用 LangGraph StateGraph（Python）；遇"自研 vs 调包"口述"框架选型经原型验证" | 🟢 |
| 2 | 长期记忆 | pgvector + similar merge + TTL（**不是** RedisStore / **不是** AGENTS.md 文件式）；Store 无内置 TTL，自建 cron🔴 | 🟢主体 / 🔴cron |
| 3 | MCP | 自建非官方 SDK，只 tools/list + tools/call 等价 | 🟢 |
| 4 | recursion_limit | 用框架自带（=25），口径"用框架自带兜底并调了阈值" | 🟢 |
| 5 | HITL | 用 interrupt_before（静态），官方推荐 interrupt()/HumanInTheLoopMiddleware 但万物云用 interrupt_before；恢复用 Command(resume=) | 🟢 |
| 6 | multi-agent 归类 | Custom workflow（StateGraph） | 🔴推断（基于 StateGraph+interrupt_before+create_agent） |
| 7 | Deep Agents | 没用（用 StateGraph + create_agent 自建） | 🟢 |
| 8 | Checkpointer 后端 | PostgresSaver 还是 Redis | 🔴待确认（别瞎称 PostgresSaver 被表结构追问翻车） |
| 9 | 路由实现 | 主要用条件边 add_conditional_edges；是否用 Command(goto) | 🟢条件边为主 / 🔴Command(goto)待核 |
| 10 | double-texting | 4 策略是 Agent Server only（非 OSS），万物云自建 Redis 锁 | 🔴推断 |
| 11 | 公司/角色 | 深圳市万睿智能科技；2023.05-2025.11；核心开发（非 owner）；后端开发工程师（2025.01 起转 AI 应用方向） | 🟢 |
| 12 | 数字 | Agent 日均~3000/峰值2-3QPS/月~2.7亿token/月数百至近千元；IoT 2000条/秒是设备消息上报吞吐（非用户请求并发） | 🟢 |
| 13 | pi 对标 | pi 是 TS coding agent 工具链，万物云是 Python 业务 agent 平台；架构思想对标不是代码移植；pi 无内置权限/HITL/RAG/MCP | 🟢 |

**🔴 项被追问时的标准话术**：
- **Checkpointer 后端**："checkpointer 用持久化后端多实例共享 state，具体是 PostgresSaver 还是 Redis 我确认下再回你。"🔴
- **multi-agent 归类**："基于我们用 StateGraph + interrupt_before + create_agent 这三点，对应官方 Custom workflow 模式，源文档没明确归类所以是推断。"🔴
- **Command(goto) 是否用**："路由主要用 add_conditional_edges 条件边，Command(goto) 是否同时用过我没确认不展开。"🔴
- **double-texting**："我们自托管 LangGraph 不是 LangSmith Agent Server，框架本身没有 double-texting 四策略，并发保护是自己加的 Redis 锁。"🔴
- **TTL cron**："官方 Store 没有内置 TTL，我们按 updated_at + ttl_days 自己跑 cron 清理，具体清理周期我确认下。"🔴

**三色含义**：🟢 官方/已确认　🟡 后端类比/通用 spec/重述　🔴 推断待核（讲时标明"我推断的"，别当确认事实）

---

### 六、检查题

1. **大对比表**：万物云和 pi 在编排方式、记忆、HITL 三个维度的根本差异各是什么？各自的标注是什么？（注意🔴项别讲混）
2. **数字口径**：Agent 日均 3000 次和 IoT 2000 条/秒是什么关系？被追问"2-3 QPS 和 2000 条/秒差这么多"怎么答不穿帮？
3. **陈述模板**：30 秒版里必须提到哪几个关键件？（意图分类、条件路由、interrupt_before、Command resume、Checkpointer、pgvector、角色边界）
4. **诚实边界**：Checkpointer 后端、multi-agent 归类、Command(goto) 是否用、double-texting--这四个🔴项被追问时各自的标准话术是什么？
5. **角色边界**：你是 owner 还是核心开发？架构谁拍板？你主导设计的子模块是哪两个？被问"团队多少人/谁拍板"怎么答不穿帮？

#### 检查题答案要点

**Q1**：编排方式--万物云图级 StateGraph（共享 State+条件边硬路由）🟢框架/🔴归类推断 vs pi 进程级（无内置 sub-agents 靠 tmux/RPC/extension）🟢；记忆--万物云 pgvector+similar merge+TTL（按需语义召回）🟢主体/🔴cron vs pi AGENTS.md 文件（启动整份加载）🟢；HITL--万物云 interrupt_before+Command(resume)🟢 vs pi 无内置靠 extension🟢。

**Q2**：是两个项目的数字。Agent 平台"3000 次/天、2-3 QPS"是用户请求量级🟢；IoT PaaS 项目"2000 条/秒"是设备消息上报吞吐（万余台设备心跳/遥测聚合）🟢。被追问答"那是两个项目，Agent 是用户请求 QPS，IoT 是设备消息上报吞吐，不是一个量纲"。

**Q3**：意图分类+规则风险标记、条件路由（单/多 Agent）、interrupt_before 暂停、Command(resume=) 恢复、Checkpointer 短期记忆、pgvector+similar merge+TTL 长期记忆、日均~3000 次、复杂任务成功率~70%、核心开发非 owner 负责多 Agent 编排+工具接入层两个子模块。

**Q4**：Checkpointer 后端--"用持久化后端多实例共享，具体 PostgresSaver 还是 Redis 我确认下"🔴；multi-agent 归类--"基于 StateGraph+interrupt_before+create_agent 推断为 Custom workflow，源文档没明确归类"🔴；Command(goto)--"主要用条件边，Command(goto) 是否用过没确认不展开"🔴；double-texting--"自托管没用 Agent Server，四策略没有，自己加 Redis 锁"🔴。

**Q5**：核心开发非 owner🟢；整体架构 lead 拍板我参与方案讨论🟡；主导设计多 Agent 协作链路 + 工具接入层两个子模块🟢。别说"主导整个平台"，问团队规模/owner 就穿。口径"主导子模块"可以。

---

