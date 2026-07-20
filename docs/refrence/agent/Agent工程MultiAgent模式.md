# Agent 工程 Multi-Agent 模式（小步教学）

> 第 24 步详细。地基通了之后，5 种模式一个一个上。
> **先看地基** [`Agent工程LangGraph心智模型.md`](./Agent工程LangGraph心智模型.md)：node 是函数、multi-agent = 多个 agent-node 串图、Command 管"走" interrupt 管"停"。
> 官方来源（🟢 Agent 核对，已验证正文）：`docs.langchain.com/oss/python/langchain/multi-agent`
> 标注：🟢 官方 / 🟡 后端类比（非官方）/ 按真实 = 万物云实际做法

---

## 0. 5 模式地图（先有个全貌，🟢）

| 模式 | 一句话 | 后端类比（🟡） | 状态 |
|---|---|---|---|
| ①Subagents | 主 agent 把子 agent 包成 @tool，自己调度 | 门面 service 调子 service | ✅ 本步讲 |
| ②Handoffs | tool 返回 Command 改 state，触发切 agent | 工作流节点跳转+改流程变量 | ✅ 已补 |
| ③Skills | 单 agent 按需加载专门 prompt/知识 | 按需 import 模块 | ✅ 已补 |
| ④Router | 路由步骤分类，导向专门 agent | API 网关路由 | ✅ 已补 |
| ⑤Custom workflow | StateGraph 自定义执行流 | 自定义工作流引擎（Activiti） | ✅ 已补（万物云用这个） |

**关键**：5 种模式不是 5 个新引擎，是"怎么组织 agent-node 和它们之间跳转"的 5 种套路。底层都是地基文档那套（State/Node/Edge/Command）。

---

## ① Subagents（=老 Supervisor）

### 定位（一句话，🟢）
主 agent（supervisor）把每个子 agent 包成 `@tool`，自己决定调谁、传什么、怎么合并。子 agent **无状态**，记忆由主 agent 维护。

### 后端类比（🟡）
- 主 agent = **门面 service（Facade）**，接收请求，调多个子 service
- 子 agent = **子 service**，无状态，每次新上下文
- `@tool` 包装 = 把子 service 封成接口给门面调

### 机制（🟢 ma_subagents.txt 核对）
- 主 agent 是个**完整 agent**（有对话记忆、能 ReAct、能调工具）
- 每个子 agent 包成 `@tool`，主 agent 像调工具一样调它
- 子 agent **无状态**：每次调用从干净上下文开始（主 agent 把问题传进去，子 agent 跑完返回结果，**不保留自己的对话历史**）
- 上下文/记忆在**主 agent** 维护

### 伪代码（🟢 官方示例）
```python
from langchain.tools import tool
from langchain.agents import create_agent

# 子 agent（专门做研究，带自己的 search 工具）
research_agent = create_agent(model="...", tools=[search_tool])

# 包成工具给主 agent 调
@tool("research", description="Research a topic and return findings")
def call_research(query: str):
    result = research_agent.invoke({"messages": [{"role":"user","content":query}]})
    return result["messages"][-1].content

# 主 agent（supervisor）调度
main_agent = create_agent(model="...", tools=[call_research])
```

### 逐行解释
1. `research_agent = create_agent(...)` -- 建子 agent（研究专长，带自己的 search_tool）
2. `@tool("research")` -- 把子 agent 包成工具，主 agent 能像调工具一样调它
3. `call_research(query)` -- 内部 `invoke` 子 agent，返回结果给主 agent
4. `main_agent = create_agent(tools=[call_research])` -- 主 agent，自己决定何时调研究工具

### 父子通信机制（详解，回答常见疑问）

**Q1：`tools=[call_research]` 生产上真这么用，还是比喻？**
真的，不是比喻。生产上就是把子 agent 包成 `@tool` 放进主 agent 的 tools 列表。主 agent 的 tools 里**既有普通工具（search/db），也可以有"子 agent 工具"（call_research），混在一起**。主 agent 的 LLM 看到 tools 里有个叫 research 的工具，需要时发 tool_call 调它，和调普通工具一模一样--主 agent 不知道（也不关心）这个工具内部其实跑了一个完整 agent。

**Q2：父子 agent 怎么传参/通信？**
**唯一通道：tool 的参数 + 返回值。没有共享内存/共享 state。**
- 父 -> 子：父 agent 发 tool_call，参数就是传给子的输入（如 `query="查RAG原理"`）
- 子 -> 父：子 agent 跑完 `return` 一个字符串，作为 ToolMessage 回到父的对话历史
- 子 agent **看不到**父的对话历史，父也**看不到**子内部怎么想的，只看子返回的最终字符串

类比（🟡）：子 agent = **无状态 REST API**（每次请求独立，服务器不存会话状态）。主 agent = 持有会话的客户端。

**Q3：记忆在哪维护？**
- 主 agent 维护**整个对话的 messages 历史**（用户问的、主 agent 答的、调了哪些 tool、tool 返回啥）
- 子 agent **每次调用全新**：invoke 时传干净 messages（只有 query），跑完返回，内部 messages 丢弃。下次再调又是全新
- "子 agent 无状态" = 不保留跨调用的记忆，每次 invoke 独立

**主 agent messages（主 agent 维护，跨整个对话）：**
```
[user: 研究RAG并算成本]
[assistant: tool_call research("RAG原理")]      # 主决定调子
[tool: "RAG是检索增强生成..."]                   # 子返回的结果（子内部过程主看不到）
[assistant: tool_call calculate(...)]           # 主再调别的工具
[tool: "成本约..."]
[assistant: "RAG是...成本约..."]                # 主最终答用户
```

**子 agent messages（每次调用独立，用完丢）：**
```
第一次 invoke:
[user: RAG原理]                                 # 干净，不带主的对话历史
[assistant: tool_call search("RAG")]            # 子内部 ReAct
[tool: "RAG是检索增强..."]
[assistant: "RAG是检索增强生成..."]             # 这个 return 给主，然后丢弃

第二次 invoke（如果主再调）:
[user: 另一个query]                             # 全新，不带第一次的记忆
...
```

**Q4：门面 service 异步调子 service，类似 JUC 异步包？**
理解对一半，关键纠正（🟢 LangGraph 机制 + 🟡 类比）：
- 门面 service 调子 service：✅ 对，主调子就像 service 调 service
- 但**默认不是异步**。主 agent 调 call_research 是**同步阻塞**等子跑完返回，主才继续。像**同步 RPC**，不是 CompletableFuture 异步回调
- JUC 异步类比在哪成立？**并行调多个子 agent** 时。主 agent 一次发多个 tool_call（research + calculate），LangGraph **并行**跑这些 tool，像 `CompletableFuture.allOf`。但单个 tool_call 内部是同步的

类比表（🟡）：

| 场景 | 后端类比 |
|---|---|
| 主调单个子 agent | 同步 RPC（门面同步调子 service，阻塞等返回） |
| 主并行调多个子 agent | CompletableFuture.allOf（并行 RPC，全完成再合并） |
| 子 agent 本身 | 无状态 REST API（每次请求独立，不存会话） |

注意：子 agent 内部可能多步 ReAct（多次 LLM + 多次工具），但对外（对主 agent）就是一个**同步 tool 调用**，主 agent 阻塞等它整个跑完。

### 完整伪代码（展示传参 + 返回 + messages 流转，🟢）

```python
from langchain.tools import tool
from langchain.agents import create_agent

# 子 agent（研究专长，带自己的 search 工具）
research_agent = create_agent(model="...", tools=[search_tool])

# 包成工具：参数 = 父传子的输入，返回值 = 子回父的结果
@tool("research", description="Research a topic and return findings")
def call_research(query: str) -> str:
    # 父 -> 子：query 作为子的任务，传干净上下文（不带父的对话历史）
    result = research_agent.invoke({
        "messages": [{"role": "user", "content": query}]
    })
    # 子 -> 父：返回最终结果字符串（子内部过程不回传）
    return result["messages"][-1].content

# 主 agent：tools 里混放子 agent 工具 + 普通工具
main_agent = create_agent(
    model="...",
    tools=[call_research, calculate_tool]
)

# 运行：主 agent 自己决定调谁、何时调
main_agent.invoke({
    "messages": [{"role": "user", "content": "研究下 RAG 原理并算下成本"}]
})
```

**运行时发生了啥（逐步）：**
1. 用户问"研究 RAG 并算成本" -> 进主 agent messages
2. 主 LLM 看 tools 列表 [research, calculate]，决定先调 research
3. 主发 tool_call `research(query="RAG原理")` -- **父传子**（参数通道）
4. call_research 收到 query，invoke research_agent（干净上下文），子内部 ReAct 跑完，return "RAG是..."
5. 结果作为 ToolMessage 加到主 messages -- **子回父**（返回值通道，子内部过程主看不到）
6. 主 LLM 看到 research 结果，决定再调 calculate
7. ... 直到主 agent 觉得能答用户了

关键：第 4 步子 agent 内部怎么 search、怎么思考，**主 agent 看不到**，主只看到第 5 步返回的字符串。

---

### 两种 tool 组织方式（🟢）

> ⚠️ subagent 共 **5 种形式**（不止这 2 种，还有 subagent 作 graph 节点、CompiledSubAgent 等），完整见 [`Agent工程MultiAgent体系全景.md`](./Agent工程MultiAgent体系全景.md) 第 4 节。
- **Tool per agent**：每个子 agent 一个 tool（细粒度，如 call_research / call_writer / call_reviewer）
- **Single dispatch tool**：一个参数化 `task(agent_name, description)` tool 按约定分发（大规模，几十个子 agent 时用）

### 适用（🟢）
多领域（日历/邮件/CRM/DB）、子 agent 不直接面对用户、要集中控制、要并行。

### 为啥叫"=老 supervisor"（🟢 原文）
官方原文："a central main agent often referred to as a **supervisor**"。Supervisor 不是独立模式，是 Subagents 的别称。面试别说"Supervisor 是单独一种模式"。

### Subagents 检查题
1. Subagents 里子 agent 有没有状态/记忆？记忆在哪维护？
2. `@tool` 包装子 agent 后，主 agent 怎么调它？和直接调子 agent 区别？
3. 父子 agent 怎么传参通信？有共享 state 吗？子 agent 看得到父的对话历史吗？
4. 主调单个子 agent 是同步还是异步？并行调多个子 agent 呢？后端类比（同步 RPC / CompletableFuture.allOf）？
5. 为啥说 Subagents = 老 supervisor？面试能说"Supervisor 是独立模式"吗？

### 参考答案（🟢 核实自 ma_subagents.txt + 心智模型）

**1. 子 agent 有没有状态/记忆？记忆在哪维护？**
子 agent **无状态**（🟢）。每次调用从干净上下文开始，跑完返回结果，内部 messages 丢弃，不保留跨调用记忆。记忆在**主 agent** 维护（整个对话的 messages 历史：用户问的、主答的、调了哪些 tool、tool 返回啥）。类比（🟡）：子 agent = 无状态 REST API（每次请求独立不存会话），主 agent = 持会话的客户端。

**2. @tool 包装后主 agent 怎么调？和直接调子 agent 区别？**
主 agent 把 call_research 当普通工具调（🟢）--主 LLM 看 tools 列表，需要时发 tool_call `research(query=...)`，和调 search/db 工具一模一样，主 agent 不知道这个工具内部跑了完整 agent。区别：直接调子 agent 是代码里显式 invoke（你写死调用时机）；@tool 包装后是**主 agent 的 LLM 自己决定何时调、传什么参数**（LLM 调度）。生产上 tools 里可混放子 agent 工具 + 普通工具（🟢）。

**3. 父子怎么传参？有共享 state 吗？子看得到父对话历史吗？**
**唯一通道：tool 参数 + 返回值，无共享 state**（🟢）。父->子：tool_call 参数（query）；子->父：return 字符串作为 ToolMessage 回父 messages。子**看不到**父对话历史（invoke 时传干净 messages 只有 query），父也看不到子内部 ReAct 过程，只看最终字符串。

**4. 主调单个子 agent 同步还是异步？并行调多个呢？**
单个**同步阻塞**（🟢+🟡）--主调 call_research 阻塞等子跑完返回才继续，像同步 RPC，不是 CompletableFuture。并行调多个子 agent（主一次发多个 tool_call）时 LangGraph **并行**跑，像 `CompletableFuture.allOf`（🟡）。子 agent 内部可能多步 ReAct，但对外就是一个同步 tool 调用。

**5. 为啥 Subagents = 老 supervisor？能说 Supervisor 是独立模式吗？**
官方原文 "a central main agent often referred to as a supervisor"（🟢）--Supervisor 是 Subagents 的别称（主 agent 集中调度），**不是独立模式**。面试**不能**说"Supervisor 是单独一种模式"，要说"Supervisor 是 Subagents 的别称"。新官方 5 模式是 Subagents/Handoffs/Skills/Router/Custom workflow，没有 Supervisor 这一项（见附录 D 纠偏）。

---

## ② Handoffs（🟢 核实自 ma_handoffs.txt）

> ⚠️ 看这节前，先看《Agent工程Command全量总结》第 1-4 节，搞懂 `Command(goto/update/graph)` 是啥。Handoffs 里用到 `Command(update)` 和 `Command(goto+update+PARENT)`，没看全量总结会懵。这篇只讲 Handoffs，Command 不在这深讲。

### Handoffs 是干嘛（白话先立住，别急着看代码）

**一句话：对话里把"话筒"从一个 agent 递给另一个 agent，让被递的 agent 接着跟用户聊。**

生活直觉：你打客服电话，先到分诊客服（收你保修号），分诊客服把情况记下来，然后说"我帮你转专家"，专家客服接过话筒，基于刚才记的信息继续跟你聊怎么修。**你不用重新报一遍保修号**，因为信息被"传"过去了。

Handoffs 就是这个"转话筒"在 multi-agent 里的实现：
- **不是** A 跑完把结果"还"给主 agent（那是 Subagents）
- **是** A 把**控制权直接交给** B，B 接着和用户对话

### 为什么需要 Handoffs（什么场景才用，对比 Subagents）

典型场景：**多阶段对话，每阶段不同 agent 处理，但要保持对话连续。**

例子（🟢 官方客服流程）：
- 第1阶段（triage 分诊）：收集保修信息（warranty ID）
- 第2阶段（specialist 专家）：基于保修信息给方案

要求：
- 用户感觉是"同一个客服"在服务（信息不用重报）
- 但底层是两个不同配置的 agent（triage 只会收信息，specialist 只会给方案）
- 必须顺序：先收完 warranty ID，才能转专家（**强制顺序约束**）

**如果用 Subagents**：主 agent 调 triage 子 agent 收信息 -> 结果回主 agent -> 主 agent 再调 specialist 子 agent。主 agent 全程控制，子 agent 不直接对用户。问题是：用户跟"主 agent"对话，但主 agent 可能啥也不懂只是转发，体验割裂。

**用 Handoffs**：triage agent 直接对用户，收完信息后把话筒转给 specialist agent，specialist 直接对用户。**用户全程感觉一个人在服务，底层换人了。**

### 核心机制（先不写代码，把原理搞懂）

Handoffs 的核心：**一个 state 变量（如 `current_step`）决定"现在哪个 agent 配置生效"，tool 改这个变量就完成"转话筒"。**

3 步循环：
1. **state 里有 `current_step`**（初始 "triage"），跨 turn 持久化（checkpointer 存着）
2. **agent 按 current_step 选配置**：triage 时用"收信息"的 prompt + tools；specialist 时用"给方案"的 prompt + tools
3. **triage agent 收完信息，调一个 tool 改 `current_step=specialist`** -> 下一轮 agent 自动切到 specialist 配置 -> 转话筒完成

**关键洞察**：Handoffs（实现1）没有"真的换一个进程/换一个对象"，而是**同一个 agent，靠 state 变量切换配置**，看起来像换人了。这就是官方说的 "State-driven behavior"（行为随 state 变量变）。

> 这就是为什么 Handoffs 会用到 `Command(update={...})`——tool 改 current_step 就是 `Command(update={"current_step":"specialist"})`。**Command 是干"改 state"这事的工具，不是 Handoffs 自带的。** Command 全貌看《Agent工程Command全量总结》。

### 两种实现（原理懂了，现在看代码就好懂了）

官方 Handoffs 有两种实现方式，区别在"怎么组织 agent"：

| | 实现 1：单 agent + middleware | 实现 2：多个 agent subgraph |
|---|---|---|
| agent 数 | 1 个（靠 state 切配置） | 多个（每个 agent 是图里一个节点） |
| 怎么切 | middleware 拦截每次 LLM 调用，按 state 换 prompt/tools | handoff tool 用 `Command(goto, graph=PARENT)` 跳到另一个 agent 节点 |
| 用到 Command | `Command(update=...)` 改 state | `Command(goto, update, graph=PARENT)` 三参数齐上 |
| 复杂度 | 简单 | 复杂（要管 subgraph + PARENT） |
| 官方推荐 | ✅ 多数场景用这个 | 只有某 agent 本身是复杂图（带反思/检索）才用 |

#### 实现 1：单 agent + middleware（官方推荐，先看这个）

**思路**：就一个 agent，但每次 LLM 调用前，middleware 读 current_step，给 agent 套对应的 prompt 和 tools。tool 改 current_step 就触发"转话筒"。

```python
from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse
from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from langgraph.types import Command

# 1. state 加 current_step 字段（这是"话筒在谁手里"的标记）
class SupportState(AgentState):
    current_step: str = "triage"        # 初始分诊
    warranty_status: str | None = None

# 2. tool：收完保修信息，改 current_step（这就是"转话筒"）
@tool
def record_warranty_status(status: str, runtime: ToolRuntime[None, SupportState]) -> Command:
    return Command(update={
        "messages": [ToolMessage(content=f"Warranty: {status}", tool_call_id=runtime.tool_call_id)],
        "warranty_status": status,           # 记下保修信息
        "current_step": "specialist"         # 关键：改这一句 = 转话筒给专家
    })
    # 这里 Command(update=) 就是"改 state"，没 goto（下一步走哪由 middleware+图决定）
    # Command 详见《Agent工程Command全量总结》用法 1（纯 update）

# 3. middleware：每次 LLM 调用前，按 current_step 换配置
@wrap_model_call
def apply_step_config(request, handler):
    step = request.state.get("current_step", "triage")
    configs = {
        "triage":      {"prompt": "收集保修信息...", "tools": [record_warranty_status]},
        "specialist":  {"prompt": "基于保修 {warranty_status} 给方案", "tools": [provide_solution, escalate]},
    }
    config = configs[step]
    request = request.override(system_prompt=config["prompt"].format(**request.state), tools=config["tools"])
    return handler(request)

# 4. 创建 agent，挂 middleware + checkpointer
agent = create_agent(model, tools=[record_warranty_status, provide_solution, escalate],
                     state_schema=SupportState, middleware=[apply_step_config], checkpointer=InMemorySaver())
```

逐行（重点看转话筒怎么发生的）：
- `SupportState.current_step`：state 里记"现在话筒在哪步"。初始 triage。
- `record_warranty_status` return `Command(update={..., "current_step":"specialist"})`：tool 不只返回结果，还**把 current_step 改成 specialist**。这就是 handoff 的"转移"——下一步 agent 会按 specialist 配置跑。
- `apply_step_config` middleware：每次 LLM 调用前拦截，读 current_step，套对应 prompt 和 tools。triage 步只给收信息 tool，specialist 步给方案/升级 tool。**同一个 agent，配置随 state 变。**
- `checkpointer=InMemorySaver()`：state 跨 turn 持久化，下一轮用户消息进来 current_step 还是 specialist。

后端类比（🟡）：同一个 Spring Service 根据 state 字段走不同分支 = **策略模式**。current_step 是策略选择键，middleware 是策略装配点。也像 SseEmitter 一个连接，按会话状态切不同 handler。

#### 实现 2：多个 agent subgraph（每个 agent 是独立图节点）

> ⚠️ 这里"subgraph"是新概念，先看《Agent工程Subgraph全量总结》第 1-3 节搞懂"subgraph = 编译后的图当节点 + 和包 tool 的可见性区别"，再看本节。
> 一句话：实现2 里每个 agent 是父图的一个**子图节点**（不是包 tool），handoff tool 用 `Command.PARENT` 从子图跳到父图另一个 agent 节点。subgraph 是和 Command 同级的基础原语，之前没系统讲是遗留缺口，已补。

**思路**：不是一个 agent 切配置，而是**真的有多个 agent**，每个是 StateGraph 里的一个节点。转话筒 = 从一个节点跳到另一个节点，用 `Command(goto, graph=PARENT)`。

```python
@tool
def transfer_to_sales(runtime: ToolRuntime) -> Command:
    last_ai_message = next(msg for msg in reversed(runtime.state["messages"]) if isinstance(msg, AIMessage))
    transfer_message = ToolMessage(content="Transferred to sales agent", tool_call_id=runtime.tool_call_id)
    return Command(
        goto="sales_agent",                                    # 跳到 sales_agent 节点（父图里）
        update={"active_agent": "sales_agent",
                "messages": [last_ai_message, transfer_message]},
        graph=Command.PARENT                                    # 命令冒泡到父图
    )
    # 这里 3 个参数齐上：goto(跳) + update(改) + graph=PARENT(作用于父图)
    # 每个参数干啥看《Agent工程Command全量总结》用法 4
```

**为什么这里要 `graph=Command.PARENT`（实现 2 才需要，实现 1 不需要）**：
- 实现 2 里每个 agent 是**子图**节点，handoff tool 在子图里跑。
- `goto="sales_agent"` 默认跳子图内部的 sales_agent，但 sales_agent 是**父图**的节点。
- 所以加 `graph=Command.PARENT` 告诉引擎"这个 goto/update 作用于父图，不是子图"。
- **实现 1 没 subgraph，不用 PARENT。** 这就是为什么实现 1 简单。

官方建议 🟢：多数场景用实现 1（更简单）。只有当某 agent 本身是带反思/检索的复杂图时，才用实现 2。

### 为什么 handoff tool 必须配 ToolMessage（🟢 官方原话，两个实现都要）

LLM 调 tool 期待响应。`ToolMessage`（配对 `tool_call_id`）完成请求-响应循环——**没有它对话历史就坏了**。任何时候 handoff tool 更新 messages 都必须配。

后端类比（🟡）：HTTP 请求必须有响应，否则连接悬挂。tool call 是请求，ToolMessage 是响应，配对才闭合。

### subgraph handoffs 的 context engineering（🟢 官方，仅实现 2）

用 `Command.PARENT` 交接时必须**同时传**：
1. `AIMessage`（触发 handoff 的那条 tool call）
2. `ToolMessage`（对该 tool call 的人工响应）

不配对，接收 agent 看到不完整对话会出错。官方建议 🟢：**只传 handoff pair，不传全部 subagent 历史**（避免上下文膨胀、避免内部推理干扰）。如需更多上下文，把 subagent 工作摘要写进 ToolMessage content。

### 和 Subagents 区别（核心，一句话记住）

**Subagents 是"调用"，Handoffs 是"转交"。**
- Subagents：主 agent **调**子 agent 当 tool，子 agent 跑完结果回流主 agent，子 agent 不直接对用户。像方法调用。
- Handoffs：A agent **把话筒转给** B agent，B 接管对话直接对用户，A 不再管。像接力赛交接棒。

| | Subagents | Handoffs |
|---|---|---|
| 控制权 | 主 agent 始终控制，子跑完回流 | **转移**给另一个 agent/state |
| 谁对用户 | 主 agent | 被交接的 agent 直接对用户 |
| 适合 | 中心化工作流控制 | 多阶段顺序对话、控制权交接 |

### 万物云口径（按真实）

万物云 multi-agent = **Custom workflow（StateGraph）**🔴 推断，**不是** handoffs。但 handoffs 的"state 驱动行为变化"思想（current_step 改变流程走向）在万物云 StateGraph 条件边里也体现。万物云人工审核用 interrupt_before（第23步），不是 handoffs 的 state 转移。

面试口径："handoffs 模式适合客服这种顺序收集信息的多阶段对话，靠 state 变量驱动行为切换。我们万物云是 StateGraph 自定义工作流，状态驱动用条件边实现，没用 handoffs 的 middleware 形式。"

### ② Handoffs 检查题
1. Handoffs 是干嘛？用"转话筒"和客服例子说清楚。和 Subagents 的"调用"有什么根本区别？
2. Handoffs 的核心机制是什么？为什么说"（实现1）没有真的换一个进程，是靠 state 变量切配置"？
3. 两种实现（单 agent+middleware / 多 subgraph）区别？为什么官方推荐单 agent？哪个才用 `graph=Command.PARENT`？
4. handoff tool 为什么必须配 ToolMessage？不配会怎样？
5. （联动 Command 全量总结）Handoffs 里出现的 `Command(update={...})` 和 `Command(goto, update, graph=PARENT)` 分别是 Command 的哪两种用法？为什么实现 1 不用 PARENT？

### 参考答案（🟢 核实自 ma_handoffs.txt + Command 全量总结）

**1. Handoffs 是干嘛？和 Subagents 根本区别？**
Handoffs = 对话里把"话筒"从一个 agent 转给另一个 agent，被转的 agent 接着跟用户聊（🟢）。客服例子：分诊客服收保修号 -> 转专家客服给方案，用户不用重报信息。根本区别：Subagents 是**"调用"**（主 agent 调子 agent 当 tool，子跑完回流主，子不直接对用户，像方法调用）；Handoffs 是**"转交"**（A 把控制权直接交给 B，B 接管对话直接对用户，A 不再管，像接力赛交接棒）（🟢）。

**2. 核心机制？为啥说"没真换进程，靠 state 切配置"？**
核心是**一个 state 变量（如 current_step）决定哪个 agent 配置生效，tool 改这个变量就完成转话筒**（🟢）。3 步循环：state 有 current_step（初始 triage）-> agent 按 current_step 选 prompt/tools -> triage 收完信息调 tool 改 current_step=specialist -> 下轮自动切配置。"没真换进程"指**实现1**是同一个 agent 靠 state 变量切配置（middleware 拦截按 current_step 换 prompt/tools），不是真的换一个 agent 对象/进程，看起来像换人（🟢 State-driven behavior）。注意：实现2才是真的多 agent 节点。

**3. 两种实现区别？为啥推荐单 agent？哪个用 graph=PARENT？**
实现1（单 agent+middleware）：1 个 agent 靠 state 切配置，middleware 拦截每次 LLM 调用换 prompt/tools，用 `Command(update=...)` 改 state。实现2（多 subgraph）：多个 agent 各是图节点，用 `Command(goto, update, graph=PARENT)` 跳节点。官方推荐实现1因为**更简单**（🟢）；只有某 agent 本身是带反思/检索的复杂图才用实现2。**实现2才用 `graph=Command.PARENT`**（子图节点跳父图节点要冒泡），实现1没 subgraph 不用 PARENT。

**4. handoff tool 为啥必须配 ToolMessage？不配怎样？**
LLM 调 tool 期待响应（🟢官方原话）。ToolMessage（配对 tool_call_id）完成请求-响应循环，没有它对话历史就坏了。不配：对话历史里有个 tool_call 没有对应 ToolMessage，LLM 下一轮看到不完整的 tool 序列会出错或异常。类比（🟡）：HTTP 请求必须有响应否则连接悬挂。**两个实现都要配**。

**5. Command(update) 和 Command(goto,update,PARENT) 是哪两种用法？为啥实现1不用 PARENT？**
`Command(update={...})` 是 Command 全量总结的**用法1（纯 update，只改 state 不跳转）**--实现1用它改 current_step，下一步走哪由 middleware+图决定。`Command(goto, update, graph=PARENT)` 是**用法4（goto+update+graph=PARENT，subgraph 跳父图节点）**--实现2用它跳父图 sales_agent 节点 + 改 active_agent + 冒泡到父图。实现1不用 PARENT 因为**没有 subgraph**--单图里 return Command 默认作用于当前图不用冒泡；PARENT 只在子图节点里要跳/改父图东西时才用（🟢）。

## ③ Skills（🟢 核实自 ma_skills.txt）

> 上一版只列概念没讲生产怎么落地。这版从"是什么 -> progressive disclosure 机制 -> 生产实现 -> 生产坑 -> 万物云怎么做"补全。

### Skills 是什么（白话先立住）

**一句话：把专门能力（prompt + 知识 + 可选工具）打包成"skill"，agent 按需 load 进上下文，不一开始全塞。**

生活直觉：你问"帮我写 SQL"，助手不会一开始就把 SQL 专家 prompt、数据库 schema、SQL 规范全背在身上（太占脑容量/token），而是你说要写 SQL 时，它"翻出"SQL skill 这本手册读一下再帮你写。写完手册可丢开（下轮不用就不占上下文）。

官方叫 **progressive disclosure（渐进式披露）**--用到才加载，不用到不占 token（🟢）。

### 为什么需要 Skills（解决什么问题）

不用 Skills 的痛点（🟡 生产场景）：
1. **token 爆**：12 个领域专家 prompt 全塞 system_prompt，每个 1-2k token，光 prompt 就 1.5-2 万 token/轮，20 轮烧 40 万 token
2. **互相干扰**：SQL skill 的 prompt 和法律文档 skill 的 prompt 同时在，agent 容易把 SQL 语法混进法律意见
3. **团队难协作**：所有领域 prompt 写在一个 system_prompt 字符串里，多团队改同一份冲突

Skills 解法：system_prompt 只列"有哪些 skill"（一句话目录），agent 用到哪个 load 哪个，只占当前需要的（🟢）。

### progressive disclosure 机制（核心，讲透省 token 怎么实现）

3 步（🟢 ma_skills）：
1. **system_prompt 只放目录**：告诉 agent "你有 write_sql / review_legal_doc 两个 skill，用 load_skill 加载"，不写具体内容
2. **agent 决定用某 skill**：LLM 看 system_prompt 知道有这技能，任务需要时发 tool_call `load_skill("write_sql")`
3. **load_skill 返回 skill 内容塞进上下文**：skill 的 prompt + schema 作为 ToolMessage 进 messages，LLM 下一轮看到完整 skill 内容按它干活

**省 token 的关键**：skill 没被 load 时，它的 prompt/schema **不在上下文里**（只在 system_prompt 占一行目录）。只有 load 那一刻才进上下文。20 个 skill 只用 2 个，省 18 个 skill 的 token。

后端类比（🟡）：Skills = **按需 import 模块**（lazy loading）。system_prompt = 模块索引；load_skill = `import module`（用到才加载进内存）；不 import 的不占内存。progressive disclosure = Spring `@ConditionalOnProperty` 按需装配 bean，不是启动全加载。

### 生产实现 load_skill（完整伪代码，不是 ...）

官方 basic 实现就是 load_skill tool，但官方伪代码省略了"怎么存怎么加载"。生产实现：

```python
from langchain.tools import tool
from langchain.agents import create_agent
from pathlib import Path
import json

# 1. skill 存储：每个 skill 一个目录，prompt.md + schema.json + 可选 tools
#    skills/write_sql/prompt.md, schema.json
#    skills/review_legal_doc/prompt.md, schema.json
SKILLS_DIR = Path("skills")

SKILL_REGISTRY = {           # 🟢 目录注册表（system_prompt 用它告诉 agent 有哪些 skill）
    "write_sql": "SQL query writing expert, given a schema write safe efficient SQL",
    "review_legal_doc": "Legal document reviewer, flag risky clauses and compliance issues",
}

@tool
def load_skill(skill_name: str) -> str:
    """Load a specialized skill prompt + schema on-demand.
    Available skills:
    - write_sql: SQL query writing expert
    - review_legal_doc: Legal document reviewer
    """
    if skill_name not in SKILL_REGISTRY:                     # 生产坑：未知 skill 兜底
        return f"Error: unknown skill '{skill_name}'. Available: {list(SKILL_REGISTRY)}"
    skill_dir = SKILLS_DIR / skill_name
    prompt = (skill_dir / "prompt.md").read_text(encoding="utf-8")   # 生产：从文件/DB/远程加载
    schema_path = skill_dir / "schema.json"
    schema = schema_path.read_text(encoding="utf-8") if schema_path.exists() else ""
    return f"# Skill: {skill_name}\n\n## Prompt\n{prompt}\n\n## Schema\n{schema}"
    # 返回内容作为 ToolMessage 进上下文，下一轮 LLM 看到完整 skill

# 2. system_prompt 只放目录，不写 skill 内容（progressive disclosure 关键）
agent = create_agent(
    model="gpt-5.5",
    tools=[load_skill],
    system_prompt=(
        "You are a helpful assistant. "
        f"You have access to these skills (use load_skill to load on-demand): "
        f"{json.dumps(SKILL_REGISTRY, ensure_ascii=False)}. "
        "Load a skill ONLY when the task needs it. Do not load all skills upfront."
    ),
)
```

逐行（重点看 progressive disclosure 怎么落地）：
- `SKILL_REGISTRY`：skill 目录注册表，system_prompt 用它告诉 agent 有哪些 skill（只放一句话描述，不放假 prompt）
- `load_skill` 内部：从文件/DB 读 prompt.md + schema.json 拼字符串返回。生产上文件可换 DB/远程配置中心
- 未知 skill 兜底：`skill_name not in SKILL_REGISTRY` 返回错误+可用列表（生产坑：LLM 编了不存在的 skill 名，要兜底不能崩）
- system_prompt 用 `json.dumps(SKILL_REGISTRY)` 放目录，**不放 skill 内容**--progressive disclosure 关键，skill 内容只在 load 后进上下文
- system_prompt 明确"不要 upfront 加载全部"--防 LLM 一上来 load 所有 skill 把 token 爆掉

**生产存储选择**（🟡）：文件系统（简单，skill 少改动少）/ DB 表（skill_name/prompt/schema/version，多团队+版本管理）/ 远程配置中心（Apollo/Nacos，热更新不改代码）。

### 三种扩展模式的生产实现（不是只列概念）

#### ① Dynamic tool registration（动态工具注册，🟢）
加载 skill 同时注册新工具，让 agent 能力随 skill 变。

```python
@tool
def load_skill(skill_name: str, runtime: ToolRuntime[None, SkillState]) -> Command:
    """Load a skill and register its tools."""
    skill = load_skill_from_store(skill_name)
    return Command(update={
        "messages": [ToolMessage(content=skill.prompt, tool_call_id=runtime.tool_call_id)],
        "loaded_skills": [skill_name],        # state 记已加载 skill
        "available_tools": skill.tools,        # 动态注册 skill 自带的工具
    })
```
机制：skill 定义自己的 tools（如 database_admin skill 带 backup/restore/migrate 工具），load 时把 tools 写进 state，middleware 按 state 给 agent 换 tools（和 Handoffs 实现1 的 middleware 切配置同机制）🟢。

#### ② Hierarchical skills（分层 skill，🟢）
skill 定义子 skill 形成树，按需逐层 load。
```
data_science (load 后才知道有子 skill)
├── pandas_expert
├── visualization
└── statistical_analysis
```
实现：data_science skill 的 prompt.md 里写"你还有子 skill: pandas_expert/visualization/statistical_analysis，需要时 load_skill 加载"。agent load 父 skill 后看到子 skill 目录，需要时再 load 子 skill。**逐层 progressive disclosure**，不是一次全暴露🟢。

#### ③ Reference awareness（引用感知，🟢）
skill prompt 不塞全部知识，只放"知识在哪"，agent 需要时读。
```markdown
# Skill: review_legal_doc
你是法律文档审查专家。
风险条款库在：docs/legal/risk_clauses.md（需要时用 read_file 读）
合规清单在：docs/legal/compliance.md
```
agent load 这个 skill 后，知道有风险条款库但内容没进上下文；审查时需要查具体条款才 read_file 读进内存。**知识按需加载，不一开始全塞**🟢。

### 生产坑（🟡 实战会踩）

| 坑 | 现象 | 解法 |
|---|---|---|
| skill prompt 太长 | 一个 skill prompt 5k token，load 后上下文爆 | skill prompt 精简到 1-2k，大知识用 reference awareness 引用文件 |
| LLM 编不存在的 skill | load_skill("write_sql2") 编错名 | load_skill 内部校验 SKILL_REGISTRY + 返回可用列表兜底 |
| load 后不释放 | load 5 个 skill 都留上下文，越聊越爆 | 轮次结束清理 loaded_skills / 用 subagent 隔离（load 在子 agent，跑完上下文丢）|
| agent 不知道有哪些 skill | system_prompt 没写目录，LLM 不会主动 load | system_prompt 必须列 skill 目录 + 何时用各 skill 的指引 |
| skill 版本冲突 | 多团队改同一 skill，线上版本乱 | skill 存 DB 带版本号，灰度发布 |
| 一开始全 load | LLM 怕漏，第一轮 load 所有 skill | system_prompt 明确"不要 upfront 全 load，按需"|

### 和 Subagents 区别（核心）
| | Subagents | Skills |
|---|---|---|
| 控制权 | 派子 agent（换执行者） | **单 agent 保持控制**（不换人） |
| 机制 | 子 agent 当 tool 调 | load_skill 加载专门 prompt/工具 |
| 隔离 | 子 agent 独立上下文 | 同一 agent 上下文，只加载技能包 |
| 适合 | 多领域需独立上下文 | 单 agent 多专门化、轻量 |
| 上下文 | 子 agent 跑完上下文丢 | skill load 后留在主上下文（要手动清理）|

### Deep Agents 的 SKILL.md 和这里的关系
- multi-agent 页 Skills 模式 = **手写 load_skill tool** 的通用思路
- Deep Agents = **框架内置** SKILL.md 文件实现 skill（封装好的框架版，见第30步）
- 关系：同一个概念，Deep Agents 是 Skills 模式的官方封装实现

### 万物云口径（按真实）

万物云**没用** Skills 的 load_skill 形式，也没用 Deep Agents 的 SKILL.md（🔴）。
- 万物云"专门能力"怎么实现？--万物云用 StateGraph 把不同业务领域（咨询/报修/工单/访客/车辆/告警）拆成不同 **agent 节点**，每个 agent 自带 system_prompt + tools（🔴推断，主辅导口径表）。这是 **Subagents 思路**（换执行者）不是 Skills（同 agent 加载技能包）。
- 为什么不用 Skills？万物云业务领域边界清晰（咨询 vs 报修是不同流程），用不同 agent 节点隔离更彻底；Skills 适合"同一 agent 干很多种活"，万物云是"不同活交不同 agent"🟡。
- 万物云"约 12 个 Skill"（面试手册）指封装的业务能力（工具/agent），不是 Skills 模式的 load_skill🟢。

面试口径："Skills 模式适合单 agent 多领域专门化，按需加载 prompt 省 token。我们万物云是 StateGraph 多 agent，不同业务领域拆成不同 agent 节点各自带 system_prompt，是 Subagents 思路不是 Skills 的 load_skill。没用 Deep Agents 的 SKILL.md。"

### ③ Skills 检查题
1. Skills 的核心机制 progressive disclosure 是什么？怎么省 token（system_prompt 只放目录 + load 才进上下文）？
2. load_skill 生产怎么实现？skill 存哪、怎么加载、未知 skill 怎么兜底？
3. 三种扩展模式（Dynamic tool registration / Hierarchical skills / Reference awareness）生产怎么落地？
4. Skills 和 Subagents 根本区别？万物云"专门能力"为什么用 Subagents 思路不用 Skills？
5. Skills 有哪些生产坑？（skill prompt 太长 / load 不释放 / LLM 编 skill 名 / 一开始全 load）

### ③ Skills 参考答案（🟢 核实自 ma_skills.txt）

**1. progressive disclosure 是什么？怎么省 token？**
技能/prompt/知识用到才加载进上下文，不一开始全塞（🟢）。省 token 机制：system_prompt 只放 skill 目录（一句话描述），skill 完整 prompt/schema 不在上下文；agent 用到时 load_skill 把内容作为 ToolMessage 进上下文。20 个 skill 只用 2 个，省 18 个的 token。类比（🟡）：按需 import 模块，不 import 不占内存。

**2. load_skill 生产怎么实现？**
skill 存文件/DB（每个 skill 一个 prompt.md + schema.json + 可选 tools）；load_skill(skill_name) 从存储读内容拼字符串返回；未知 skill 校验 SKILL_REGISTRY 不存在返回错误+可用列表兜底；system_prompt 用 SKILL_REGISTRY 目录告诉 agent 有哪些 skill（不放假 prompt）。生产存储：文件（简单）/ DB（版本管理）/ 远程配置中心（热更新）🟡。

**3. 三种扩展模式怎么落地？**
① Dynamic tool registration：load skill 时把 skill 自带 tools 写进 state，middleware 按 state 给 agent 换 tools（和 Handoffs 实现1 middleware 同机制）🟢；② Hierarchical skills：父 skill prompt 里写子 skill 目录，agent load 父后看到子，需要再 load 子，逐层披露🟢；③ Reference awareness：skill prompt 只放"知识在哪"（文件路径），agent 需要时 read_file 读进内存，知识按需加载🟢。

**4. Skills vs Subagents？万物云为什么用 Subagents？**
控制权：Subagents 换执行者（子 agent 独立上下文），Skills 单 agent 不换人（同上下文加载技能包）🟢。万物云用 Subagents 思路（不同业务领域拆不同 agent 节点各自 system_prompt）🔴推断，因为业务领域边界清晰（咨询 vs 报修是不同流程）隔离更彻底；Skills 适合"同一 agent 干多种活"，万物云是"不同活交不同 agent"🟡。万物云"12 个 Skill"指封装的业务能力不是 Skills 模式🟢。

**5. Skills 生产坑？**
skill prompt 太长（解法精简+reference awareness）；load 后不释放越聊越爆（解法轮次清理/subagent 隔离）；LLM 编不存在的 skill 名（解法 load_skill 校验+兜底）；agent 不知道有哪些 skill（解法 system_prompt 列目录）；一开始全 load（解法 system_prompt 明确按需）；skill 版本冲突（解法 DB 带版本号灰度）🟡。

## ④ Router（🟢 核实自 ma_router.txt）

> 上一版只列了 Command/Send 玩具伪代码（`...` 省略），没讲生产怎么分类、怎么并行聚合、错误怎么兜。这版补全。Send 是新原语先讲透再用。

### Router 是什么（白话先立住）

**一句话：一个分类步骤，把 input 派发到一个或多个专门 agent，结果合成一个回复。**

生活直觉：你打 114 问"附近哪有修手机的 + 营业到几点"，114 不会一个客服全答，而是把"修手机"分给生活服务客服、"营业时间"分给商家信息客服，**两个客服并行查**，114 把两边结果合一起回你。114 就是 Router--分类 + 并行派发 + 合成。

Router 适合"多源并行查询再合成"（🟢官方：GitHub/Notion/Slack 并行查再合成）。

### 前置：Send 是什么（并行原语，先讲透再用）

Router 用 Send 做并行 fan-out。Send 是 LangGraph 的**并行派发原语**，和 Command 同级但职责不同（🟢 ma_router）：

| | Command | Send |
|---|---|---|
| 干啥 | 跳到**一个**节点（可带 update）| 并行派发**多个**节点实例（各自带输入）|
| 语法 | `Command(goto="X", update={...})` | `Send("node", {"input": ...})` 返回 list |
| 场景 | 单发路由（去一个 agent）| 并行 fan-out（同时去多个 agent）|
| 后端类比 | 网关转发单后端 | 网关 scatter-gather（广播多后端并行再聚合）|

**Send 机制**：节点函数 return 一个 `[Send(...), Send(...), ...]` 列表，LangGraph 给每个 Send 创建一个目标节点实例并行跑，各自带自己的输入 state，跑完结果聚合到下游节点（🟢）。

关键：Send 的目标节点是**同一个节点名但多个实例**（每个 Send 一个实例并行跑），不是跳不同节点。比如 `[Send("worker", {"task": t1}), Send("worker", {"task": t2})]` = 并行跑 2 个 worker 实例。

### Router vs Subagents（先搞清边界，🟢官方明确）

| | Router | Subagents |
|---|---|---|
| 是什么 | 专门的路由**步骤**（单次 LLM call 或规则）| 主 supervisor **agent** |
| 状态 | 通常不维护对话历史，**预处理步骤** | 维护上下文，跨轮编排 |
| 决策 | 分类输入派发，一次性的 | 对话中动态决定调哪些子 agent |
| 适合 | 输入类别清晰、要确定性/轻量分类 | 灵活的、对话感知的编排 |

一句话：**分类明确用 Router，对话动态编排用 Subagents**（🟢官方）。

### 生产实现：Command 单发（完整伪代码）

官方 `classify_query` 是 `...` 省略。生产怎么分类：

```python
from langgraph.types import Command
from langchain.agents import create_agent
from pydantic import BaseModel

# 1. 分类用 structured output（LLM 返回结构化结果，不是裸字符串）
class Route(BaseModel):
    agent: str   # "billing" / "support" / "sales"
    reason: str

classifier = create_agent(
    model="gpt-5.5-mini",    # 分类用小模型省钱省延迟
    response_format=Route,   # structured output 强制返回 Route 结构
    prompt="根据用户问题分类到 billing/support/sales 之一",
)

ROUTE_TABLE = {"billing": billing_agent, "support": support_agent, "sales": sales_agent}  # 路由表

def classify_query(query: str) -> str:
    result = classifier.invoke({"messages": [{"role": "user", "content": query}]})
    route = result["structured_response"]            # 拿到 Route 对象
    if route.agent not in ROUTE_TABLE:               # 生产坑：分类失败/编造兜底
        return "support"                             # 兜底到默认 agent
    return route.agent

def route_query(state: State) -> Command:
    active_agent = classify_query(state["messages"][-1].content)
    return Command(goto=active_agent)                # 路由到选中 agent（Command 用法2 纯跳转）
```

逐行（生产要点）：
- 分类用 **structured output**（`response_format=Route`）：LLM 返回结构化 Route 对象不是裸字符串，避免解析"我觉得走 billing"这种自然语言🟢
- 分类用**小模型**（gpt-5.5-mini）：分类是简单任务，省钱省延迟🟡
- `ROUTE_TABLE`：路由表，agent 名 -> agent 实例。生产上配置化（DB/配置中心），加 agent 不改代码🟡
- 兜底：`route.agent not in ROUTE_TABLE` 返回默认 agent（生产坑：LLM 编了不存在的 agent 名或分类置信度低，要兜底不能崩）🟡
- `Command(goto=active_agent)`：纯跳转不改 state（Command 用法2，见《Command全量总结》）

### 生产实现：Send 并行 fan-out（完整伪代码）

官方并行伪代码也是 `...`。生产怎么并行 + 聚合：

```python
from typing import TypedDict
from langgraph.types import Send
from langgraph.graph import StateGraph, START, END

class State(TypedDict):
    query: str
    results: list[str]    # 各 agent 结果聚合
    final_answer: str

# 1. 分类：LLM 决定要查哪几个源（可能多个）
def classify_query(query: str) -> list[str]:
    result = multi_classifier.invoke({"messages": [{"role": "user", "content": query}]})
    sources = result["structured_response"].sources   # ["github", "notion"] 等
    if not sources:                                    # 生产坑：分类出空，兜底默认源
        sources = ["support"]
    return sources

# 2. 路由节点：return Send 列表并行 fan-out
def route_query(state: State):
    sources = classify_query(state["query"])
    return [Send(s, {"query": state["query"]}) for s in sources]
    # 每个 Send 创建一个目标 agent 实例并行跑，各自带 query

# 3. 各专门 agent 节点
def github_agent(state): ...    # 查 GitHub 返回结果进 state["results"]
def notion_agent(state): ...
def slack_agent(state): ...

# 4. 聚合节点：把各 agent 结果合成一个回复（scatter-gather 的 gather）
def synthesize(state: State) -> dict:
    answer = synthesizer.invoke({                       # 用 LLM 合成，不是字符串拼接
        "messages": [{"role": "user",
                       "content": f"问题:{state['query']}\n各源结果:{state['results']}"}]
    })
    return {"final_answer": answer["messages"][-1].content}

# 5. 图：classify -> 并行 agent（Send fan-out）-> synthesize
workflow = (
    StateGraph(State)
    .add_node("github", github_agent)
    .add_node("notion", notion_agent)
    .add_node("slack", slack_agent)
    .add_node("synthesize", synthesize)
    .add_conditional_edges(START, route_query, ["github", "notion", "slack"])  # Send fan-out
    .add_edge("github", "synthesize")       # 各 agent 跑完都到 synthesize 聚合
    .add_edge("notion", "synthesize")
    .add_edge("slack", "synthesize")
    .add_edge("synthesize", END)
    .compile()
)
```

逐行（生产要点）：
- 分类返回**列表**（多源）：一个问题可能要查多个源（"项目进度"要查 GitHub issue + Notion 文档），classify 返回多个源🟢
- 兜底：分类出空列表返回默认源（生产坑：LLM 觉得不需要查任何源，但用户问了问题，要兜底）🟡
- `Send(s, {"query": ...})`：每个 Send 一个 agent 实例并行跑，各自带 query 输入🟢
- `synthesize` 聚合节点：**用 LLM 合成**不是字符串拼接（拼接出来不通顺，LLM 合成连贯回复）🟡
- 图用 `add_conditional_edges(START, route_query, [...])` 接 Send fan-out，各 agent 跑完 edge 到 synthesize 聚合🟢

### Stateful router 的 Tool wrapper（生产实现，官方推荐）

纯 Router 是无状态预处理。要多轮对话，官方推荐把 router 包成 tool 给对话 agent 调（🟢）：

```python
@tool
def search_docs(query: str) -> str:
    """Search across GitHub/Notion/Slack in parallel."""
    result = workflow.invoke({"query": query})     # 内部跑 router workflow（stateless）
    return result["final_answer"]                  # 返回合成结果给对话 agent

# 对话 agent 持记忆，router 保持 stateless
conversational_agent = create_agent(
    model="gpt-5.5",
    tools=[search_docs],
    prompt="You are a helpful assistant. Use search_docs to answer questions about docs.",
)
```
机制：对话 agent 持有 messages 历史（多轮记忆），需要查文档时调 search_docs tool；search_docs 内部跑 stateless router workflow（并行查多源合成），返回结果给对话 agent。**记忆放对话 agent，路由保持无状态**🟢。

后端类比（🟡）：对话 agent = 持 session 的 Controller，search_docs = 调一个无状态查询服务，路由逻辑在服务内部不持有 session。

### 生产坑（🟡 实战会踩）

| 坑 | 现象 | 解法 |
|---|---|---|
| 分类不准 | LLM 分错类，派错 agent | structured output 强制结构 + 小模型分类 + 置信度低兜底默认 + 评测集调分类 prompt |
| 分类失败/编造 | LLM 返回不存在的 agent 名 | ROUTE_TABLE 校验 + 兜底默认 agent |
| 并行结果冲突 | 两个源给矛盾信息，合成混乱 | synthesize 节点让 LLM 标注矛盾 + 优先级（如官方文档 > 社区）|
| 并行超时 | 一个源慢拖垮整体 | 各 agent 超时 + 降级（超时源跳过，用已有结果合成）|
| 聚合质量差 | 字符串拼接不通顺 | synthesize 用 LLM 合成不是拼接 |
| 路由表硬编码 | 加新 agent 要改代码 | ROUTE_TABLE 配置化（DB/配置中心）|

### 万物云口径（按真实）

万物云 multi-agent = **Custom workflow（StateGraph）**🔴 推断。Router 的"分类+派发"思想在万物云有体现，但不是纯 Router 模式：
- 万物云有**意图分类节点**（小模型分类 + 规则风险标记）+ **条件边路由**（add_conditional_edges）🟡（面试手册口径）。这是 Router 的"分类+单发"思想。
- 但万物云不是纯 Router（纯 Router 是无状态预处理），万物云是有状态自定义工作流（跨轮记忆 + HITL + 多阶段）🔴推断。
- 万物云没用 Send 并行 fan-out（业务场景是顺序编排不是多源并行查询）🔴推断。

面试口径："Router 模式适合多源并行查询合成，是 custom workflow 的特例。我们万物云 StateGraph 里也用意图分类节点 + 条件边做路由分类（Router 的单发思想），但不是纯 Router 模式，是带状态的自定义工作流，没用 Send 并行 fan-out（业务是顺序编排）。"

### ④ Router 检查题
1. Router 是什么？和 Subagents 根本区别（预处理步骤 vs 对话编排）？
2. Send 是什么？和 Command 区别？Send 的目标节点是同一个还是不同？
3. Command 单发路由生产怎么实现？classify_query 怎么做（structured output + 小模型 + 路由表 + 兜底）？
4. Send 并行 fan-out 生产怎么实现？结果怎么聚合（synthesize 节点 LLM 合成）？
5. Stateful router 的 Tool wrapper 怎么让无状态 router 支持多轮？
6. Router 有哪些生产坑？（分类不准/编造/并行超时/聚合质量/路由表硬编码）
7. 万物云用 Router 吗？意图分类节点 + 条件边 和纯 Router 区别？

### ④ Router 参考答案（🟢 核实自 ma_router.txt）

**1. Router 是什么？vs Subagents？**
Router 是一个分类步骤把 input 派发到专门 agent（🟢）。Subagents 是主 supervisor agent 维护上下文跨轮编排；Router 是专门的路由步骤通常不维护对话历史是预处理步骤，分类输入一次性派发。分类明确用 Router，对话动态编排用 Subagents（🟢官方）。

**2. Send 是什么？vs Command？**
Send 是 LangGraph 并行派发原语（🟢）。Command 跳一个节点（单发），Send 并行派发多个节点实例（fan-out）。Send 的目标节点是**同一个节点名多个实例**（每个 Send 一个实例并行跑），不是跳不同节点。类比（🟡）：Command=网关转发单后端，Send=scatter-gather 广播多后端。

**3. Command 单发生产实现？**
classify_query 用 structured output（response_format=Route）强制 LLM 返回结构化 Route 不是裸字符串；分类用小模型省钱；ROUTE_TABLE 路由表配置化；兜底 route.agent 不在表里返回默认 agent。route_query return Command(goto=active_agent) 纯跳转🟡生产+🟢官方。

**4. Send 并行 fan-out 生产实现？**
classify_query 返回多源列表（一个问题可能查多源）；route_query return [Send(s, {"query":...}) for s in sources] 每个 Send 一个 agent 实例并行；synthesize 聚合节点用 LLM 合成不是字符串拼接；图用 add_conditional_edges 接 Send fan-out，各 agent edge 到 synthesize🟢+🟡。

**5. Tool wrapper 怎么支持多轮？**
把 stateless router 包成 tool（search_docs）给对话 agent 调（🟢官方推荐）。对话 agent 持有 messages 历史多轮记忆，需要查文档时调 search_docs；search_docs 内部跑 stateless router workflow 返回合成结果。记忆放对话 agent，路由保持无状态。

**6. Router 生产坑？**
分类不准（structured output+小模型+兜底+评测调 prompt）；分类编造（ROUTE_TABLE 校验+默认 agent）；并行结果冲突（synthesize 标注矛盾+优先级）；并行超时（各 agent 超时+降级跳过）；聚合质量差（LLM 合成非拼接）；路由表硬编码（配置化）🟡。

**7. 万物云用 Router 吗？**
万物云有意图分类节点 + 条件边路由（Router 单发思想）🟡，但不是纯 Router 模式（纯 Router 无状态预处理），万物云是带状态自定义工作流（跨轮记忆+HITL+多阶段）🔴推断。没用 Send 并行 fan-out（业务顺序编排不是多源并行）🔴推断。

## ⑤ Custom workflow（🟢 核实自 ma_custom.txt，万物云用这个）

### 定位
用 LangGraph **自定义专属执行流**。对图结构完全控制--顺序步骤、条件分支、循环、并行执行。

### 关键特性（🟢）
- 对图结构**完全控制**
- 混合**确定性逻辑和 agentic 行为**
- 支持顺序步骤、条件分支、循环、并行
- 可把**其他模式作为节点**嵌入工作流

### 何时用
标准模式（subagents/skills 等）不满足需求 / 需混合确定性逻辑和 agentic 行为 / 用例需复杂路由或多阶段处理。

### 核心洞察（🟢 官方）
可以在**任何 LangGraph node 里直接调 LangChain agent**，结合 custom workflow 的灵活性和 prebuilt agent 的便利。

### 一个 node 可以是（🟢 官方，4 种）
1. 简单函数（确定性逻辑）
2. LLM call
3. 带 tools 的完整 agent
4. 整个 multi-agent 系统（作为单个节点嵌入）

### 基础实现（🟢 官方示例）
```python
from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END

agent = create_agent(model="openai:gpt-5.5", tools=[...])

def agent_node(state: State) -> dict:
    """LangGraph node 里调 LangChain agent"""
    result = agent.invoke({
        "messages": [{"role": "user", "content": state["query"]}]
    })
    return {"answer": result["messages"][-1].content}

workflow = (
    StateGraph(State)
    .add_node("agent", agent_node)
    .add_edge(START, "agent")
    .add_edge("agent", END)
    .compile()
)
```

逐行：
- `agent_node` 是个普通函数（node），内部调 `agent.invoke`--node 里装 agent
- `StateGraph(State).add_node(...)` 把 node 加进图
- `.add_edge(START, "agent").add_edge("agent", END)` 连边：START->agent->END
- `.compile()` 编译成可执行图

### RAG 管线示例（🟢 官方，展示三类节点混合）
- **Model node（Rewrite）**：用 structured output 重写 query 改善检索（LLM）
- **Deterministic node（Retrieve）**：向量相似度搜索，**无 LLM**（确定性）
- **Agent node（Agent）**：对检索上下文推理，可经 tools 取额外信息（agentic）

```python
class State(TypedDict):
    question: str
    rewritten_query: str
    documents: list[str]
    answer: str

def rewrite_query(state): ...    # Model node：LLM 重写 query
def retrieve(state): ...         # Deterministic node：向量检索，无 LLM
def call_agent(state): ...       # Agent node：create_agent 推理 + tools

workflow = (
    StateGraph(State)
    .add_node("rewrite", rewrite_query)
    .add_node("retrieve", retrieve)
    .add_node("agent", call_agent)
    .add_edge(START, "rewrite")
    .add_edge("rewrite", "retrieve")
    .add_edge("retrieve", "agent")
    .add_edge("agent", END)
    .compile()
)
```

官方提示 🟢：生产用**持久化向量库**（Valkey / Databricks Vector Search / MongoDB Atlas），别用 InMemoryVectorStore。

后端类比（🟡）：这条管线 = Activiti 流程：脚本任务（rewrite，调 LLM）-> 服务任务（retrieve，向量检索）-> 智能任务（agent，调 agent）-> 结束。混合确定性和智能节点。

### 万物云用 Custom workflow（🔴 推断，基于已确认事实）
依据：
- 万物云用 StateGraph（🟢 之前确认）
- 万物云用 interrupt_before 做人工审核（🟢 第23步）
- 万物云用 create_agent（🟢）
- 源文档没明确归类万物云用 multi-agent 哪个模式

归为 Custom workflow 最贴切：万物云的图混合了确定性节点（检索/规则）和 agentic 节点（create_agent）+ 人工审核节点（interrupt_before），这正是 Custom workflow"混合确定性逻辑和 agentic 行为"的特征，且不是 Subagents/Handoffs/Skills/Router 任一标准模式。

万物云的 node 大致：
- 检索节点（确定性，向量检索 pgvector）
- LLM 节点（重写 query / 合成答案）
- agent 节点（create_agent 推理 + tools）
- 人工审核节点（interrupt_before 打断等审核）
- 条件边路由（根据 state 走不同分支）

面试口径："我们万物云 multi-agent 是 **Custom workflow**，用 StateGraph 自定义执行流，混合确定性逻辑（检索/规则）和 agentic 行为（create_agent），节点间用条件边路由，人工审核用 interrupt_before 打断。没用 subagents/handoffs 这些标准模式，是自己定义的工作流。"

### 和其他 4 模式关系（Custom workflow 最通用）
Custom workflow 是**最底层图编排**，其他模式都可看作它的特例：
- **Router** 官方明说是 custom workflow 的例子（分类节点 + Send/Command 边）
- **Subagents** = custom workflow 里 node 调 agent（tool 形式）
- **Handoffs（multiple subgraphs）** = custom workflow（StateGraph 多 agent 节点 + Command.PARENT）
- **Handoffs（single agent+middleware）** = custom workflow 里单 agent + middleware
- **Skills** = custom workflow 里单 agent + load_skill tool

所以万物云用 Custom workflow 不矛盾--它是最底层的图编排，能容纳其他模式。

后端类比（🟡）：Custom workflow = **Activiti 自定义工作流引擎**（完全自己画流程图，节点/边/分支/循环/并行全自己定）。其他模式 = Activiti 里某些**预置流程模板**（拿来即用但不够灵活时退回自定义）。

### ⑤ Custom workflow 检查题
1. Custom workflow 的核心是什么？为什么说它最通用？
2. 一个 node 可以是什么？（4 种）
3. RAG 管线示例里三类节点各是什么？哪个是确定性、哪个是 agentic？
4. 万物云用 Custom workflow 的依据是什么？（🔴 推断，基于 StateGraph + interrupt_before + create_agent）
5. 为什么说其他 4 模式都是 Custom workflow 的特例？

### 参考答案（🟢 核实自 ma_custom.txt）

**1. Custom workflow 核心？为啥最通用？**
核心是用 LangGraph StateGraph **自定义专属执行流**，对图结构完全控制（🟢）--顺序步骤、条件分支、循环、并行，混合确定性逻辑和 agentic 行为。最通用因为它是**最底层图编排**，其他 4 模式都可看作它的特例（Router 是分类节点+Send/Command 边；Subagents 是 node 调 agent；Handoffs 是多 agent 节点+Command.PARENT 或单 agent+middleware；Skills 是单 agent+load_skill）。能容纳其他模式所以最通用。类比（🟡）：Activiti 自定义工作流引擎，其他模式是预置流程模板。

**2. 一个 node 可以是什么？（4 种）**
（🟢官方）① 简单函数（确定性逻辑）；② LLM call；③ 带 tools 的完整 agent；④ 整个 multi-agent 系统（作为单个节点嵌入）。核心洞察：可以在任何 LangGraph node 里直接调 LangChain agent。

**3. RAG 管线三类节点各是什么？哪个确定性、哪个 agentic？**
（🟢）① **Model node（Rewrite）**--用 structured output 重写 query 改善检索，**LLM（agentic）**；② **Deterministic node（Retrieve）**--向量相似度搜索，**无 LLM（确定性）**；③ **Agent node（Agent）**--对检索上下文推理可经 tools 取额外信息，**agentic**。关键：不是所有节点都要 LLM，确定性的留确定性（同 query 同结果可复现可测试），该智能的才智能。

**4. 万物云用 Custom workflow 的依据？（🔴 推断）**
🔴推断，基于三条已确认事实：万物云用 StateGraph（🟢）+ 用 interrupt_before 做人工审核（🟢第23步）+ 用 create_agent（🟢）。源文档没明确归类万物云用哪个模式。归 Custom workflow 最贴切因为万物云的图混合确定性节点（检索/规则）和 agentic 节点（create_agent）+ 人工审核节点（interrupt_before），正是 Custom workflow"混合确定性逻辑和 agentic 行为"特征，且不是 Subagents/Handoffs/Skills/Router 任一标准模式。面试口述"基于这三点推断"（🔴），别说成已确认归类。

**5. 为什么其他 4 模式都是 Custom workflow 特例？**
（🟢）Custom workflow 是最底层图编排（StateGraph 自定义），其他模式都是它的特定图结构：**Router** = 分类节点 + Send/Command 边（官方明说是 custom workflow 例子）；**Subagents** = custom workflow 里 node 调 agent（tool 形式）；**Handoffs（多 subgraph）** = StateGraph 多 agent 节点 + Command.PARENT；**Handoffs（单 agent+middleware）** = 单 agent + middleware；**Skills** = 单 agent + load_skill tool。它们都用 StateGraph 底层，只是图结构是预置套路，Custom workflow 是完全自定义能容纳所有。

---

## 附录 A：性能对比（🟢 官方实测，面试硬货）

| Pattern | 单次 | 重复请求 | 多领域 |
|---|---|---|---|
| Subagents | 4 calls | 8 calls (4+4) | 5 calls, 9K tokens |
| Handoffs | 3 calls | 5 calls (3+2) | 7+ calls, 14K+ tokens |
| Skills | 3 calls | 5 calls (3+2) | 3 calls, 15K tokens |
| Router | 3 calls | 6 calls (3+3) | 5 calls, 9K tokens |

关键 insight：
- 单次：Handoffs/Skills/Router 最优（3 calls）；Subagents 多 1 call（结果要回流主 agent）
- 重复请求：有状态的 Handoffs/Skills 省 40-50%（subagent 无状态每次重跑全流程）
- 多领域并行：Subagents/Router 最优（并行）；Handoffs 必须串行最差

## 附录 B：特性矩阵（🟢 官方，选模式用）

| 模式 | 分布式开发 | 并行 | 多跳串行 | 子agent直接面对用户 |
|---|---|---|---|---|
| Subagents | ✓✓✓ | ✓✓✓ | ✓✓✓ | ✗ |
| Handoffs | - | - | ✓✓✓ | ✓✓✓ |
| Skills | ✓✓✓ | ✓✓ | ✓✓✓ | ✓✓✓ |
| Router | ✓✓ | ✓✓✓ | - | ✓✓ |

**模式可混搭**（🟢 原文）："You can mix patterns!"

## 附录 C：选择决策（🟢 官方）

| 场景 | 推荐模式 |
|---|---|
| 优化单次请求 | Subagents / Handoffs / Skills |
| 优化重复请求 | Handoffs / Skills |
| 并行执行 | Subagents / Router |
| 大上下文领域 | Subagents / Router |
| 简单聚焦任务 | Router |
| 确定性业务流程编排 | Custom workflow（万物云用这个） |

## 附录 D：关键纠偏（面试别说错，🟢）

1. 别再说老三种（Supervisor/Swarm/Team）-- 新官方 5 种。Supervisor = Subagents 别称；Swarm 已消失
2. multi-agent 文档在 **langchain 包下**（`/oss/python/langchain/multi-agent`），不在 langgraph。底层用 LangGraph 的 Command/Send/StateGraph
3. `create_react_agent` -> `create_agent`（v1 迁移）
4. **没有 `handoff()` 函数**，手写 `@tool` + `Command`
5. `langgraph-supervisor` / `langgraph-swarm` 包不再维护
6. 官方推荐 built-in multi-agent 用 **Deep Agents**（更高层 harness）

## 附录 E：API 速查（🟢）

```python
from langchain.agents import create_agent, AgentState           # 新统一入口（替代 create_react_agent）
from langchain.tools import tool, ToolRuntime, InjectedToolCallId
from langchain.messages import ToolMessage, AIMessage
from langchain.agents.middleware import wrap_model_call          # handoffs middleware
from langgraph.types import Command, Send, interrupt             # 路由/并行/中断
from langgraph.graph import StateGraph, START, END               # custom workflow / 多 subgraph
from langgraph.checkpoint.memory import InMemorySaver            # 持久化
```
