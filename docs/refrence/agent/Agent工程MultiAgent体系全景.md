# Agent 工程 Multi-Agent 体系全景

> 体系化全列，不限原 5 模式大纲。把 ReAct / multi-agent / team 这些常被混谈的概念分清。
> 🟢 官方核实（docs.langchain.com / microsoft.github.io/autogen / docs.crewai.com，Agent 抓正文确认）
> 🟡 概念映射/后端类比/通用知识（非官方原文）
> 🔴 推断/历史模式
> 按真实 = 万物云实际做法

---

## 0. 先理清四个层次（最关键，别混）

很多人把"ReAct""multi-agent""team"混在一起谈，其实分四个层次：

| 层次 | 问什么 | 例子 |
|---|---|---|
| **层1 单agent推理模式** | 一个 agent 内部怎么思考/决策 | ReAct、Plan-and-Execute、Reflection |
| **层2 工作流模式** | 多个步骤怎么编排（不一定多agent） | prompt chaining、parallelization、orchestrator-worker |
| **层3 multi-agent模式** | 多个 agent 怎么协作 | subagents、handoffs、router、custom workflow |
| **层4 框架team抽象** | 框架怎么封装上述 | AutoGen Team、CrewAI Crew、Deep Agents |

后端类比（🟡）：
- 层1 = 一个 service 内部的算法（ReAct = while 循环里调工具）
- 层2 = 业务流程编排（多个 service 调用怎么串/并/路由）
- 层3 = 微服务间协作（多个 agent service 怎么分工）
- 层4 = 框架脚手架（Spring Batch / Activiti 这种封装好的引擎）

---

## 1. 层1：单 agent 推理模式

### 关键纠偏（🟢 Agent 核实）
当前 docs.langchain.com **已弃用** ReAct/Plan-and-Execute/Reflection/ToT/Reflexion/ReWOO/Self-Ask 这些"命名推理模式"的概念页（搜 llms.txt 全索引无匹配，旧 python.langchain.com 页下线）。当前用 `create_agent`（工具调用循环）+ middleware 扩展。但概念上这些模式还在业界用，面试要知道。

### 模式表

| 模式 | 是什么（🟡 学术/通用） | 当前 LangChain 对应（🟡 映射） | 状态 |
|---|---|---|---|
| **ReAct** | 推理->行动->观察->再推理的循环 | `create_agent` 默认就是（🟢 原文"model calling tools in a loop"） | ✅ 主流 |
| **Plan-and-Execute** | 先规划成子任务，再逐个执行 | ≈ orchestrator-worker（层2） | ✅ 有对应 |
| **Reflection** | 生成->自我评估->按反馈改进循环 | ≈ evaluator-optimizer（层2） | ✅ 有对应 |
| **Tree of Thoughts (ToT)** | 树形展开多条思维路径，搜索最优 | 当前官方无专门页（🔴 旧版实验性已下线） | ⚠️ 历史 |
| **Reflexion** | 带跨 trial 记忆的强化反思 | 当前官方无（🔴） | ⚠️ 历史 |
| **ReWOO** | 无观察推理（一次规划好工具调用，不逐步观察） | 当前官方无（🔴） | ⚠️ 历史 |
| **Self-Ask with Search** | 自问自答+搜索 | 当前官方无（旧 AgentType 已移除，🔴） | ⚠️ 历史 |

### ReAct 详解（🟢 当前 create_agent 默认）
- **是什么**：model 在循环里调工具直到任务完成。推理(想该不该调工具)->行动(调工具)->观察(看结果)->再推理
- **伪代码**（🟢 agents 页机制）：
```python
from langchain.agents import create_agent
agent = create_agent(model=..., tools=[...])
# 内部循环：LLM 决定调工具 -> 调 -> 观察结果 -> 再让 LLM 决定，直到不再调工具
```
- **后端类比**（🟡）：一个 while(true) 的 service，循环里调外部工具直到业务完成
- **适用**：大部分单 agent 场景，工具调用决策

### Plan-and-Execute / Reflection
当前不单独命名，归入层2 的 orchestrator-worker / evaluator-optimizer（见下）。

---

## 2. 层2：工作流模式（6种，🟢 workflows-agents 页核实）

这层是"多个 LLM 步骤怎么编排"，不一定多 agent。是 multi-agent 的基础。

| 模式 | 是什么 | 后端类比（🟡） | 适用 |
|---|---|---|---|
| **prompt chaining** | 串行链：前一步输出作后一步输入 | 责任链/管道 pipeline | 生成->翻译->摘要 等固定流水线 |
| **parallelization** | 并行：分片(sharding)或多投票(voting) | CompletableFuture.allOf | 大任务分片并行 / 多模型投票提准确率 |
| **routing** | 路由分类，按输入走不同分支 | API 网关路由 | 客服分流、分类处理 |
| **orchestrator-worker** | 编排者生成计划，动态派 worker，合成结果（=Plan-and-Execute） | 门面+任务分派 | 复杂研究、动态子任务 |
| **evaluator-optimizer** | 生成->评估->按反馈改进循环（=Reflection） | 质检+返工 | 代码生成+审查、翻译润色 |
| **agents** | LLM 自主调工具循环（=ReAct 升层） | 自治 service | 开放式任务 |

### orchestrator-worker 详解（=Plan-and-Execute，🟢 workflows-agents + 🟡 类比）

**orchestrator 是啥？**
- 中文：**编排器 / 协调者 / 调度中枢**
- 动词 orchestrate = 编排（像乐队指挥编排各声部）
- 分布式系统常见词：Kubernetes 叫 container orchestrator（容器编排器），工作流引擎叫 orchestration

**这个模式干啥（解决什么问题）**
复杂任务不能一次做完，需要：先**拆**成子任务 -> 分别**派**给 worker 做 -> 再**合**成结果。三个角色：
- **orchestrator（编排者）**：不干具体活，负责 ①理解任务 ②拆成子任务 ③派给 worker ④收结果 ⑤合成最终结果
- **worker（工作者）**：干实际子任务（可以是 LLM/agent/工具）
- = 学术名 **Plan-and-Execute**（orchestrator = Planner + Synthesizer，worker = Executor）

**后端类比（🟡，挑你熟的）**

| 类比 | orchestrator | worker |
|---|---|---|
| Master-Worker（Java并发） | Master 拆任务派发 + 收结果合并 | Worker 线程干具体活 |
| 项目组 | 项目经理拆需求派给开发 + 汇总 | 开发干活 |
| 工作流引擎 | 编排节点拆子流程 | 执行节点干活 |
| Kubernetes | controller 编排 | worker node 跑容器 |

**具体例子**：用户问"研究 RAG 原理、对比 3 个框架、写报告"
1. orchestrator 拆成 3 子任务：[研究RAG原理, 对比框架, 写报告]
2. 前 2 个并行派给 worker，第 3 个等前两个结果
3. orchestrator 收 worker 结果，合成最终报告

**伪代码（🟢 workflows-agents 机制）**
```python
from pydantic import BaseModel
from langgraph.types import Send

# 1. orchestrator 拆任务（structured_output 强制结构化输出）
class Plan(BaseModel):
    subtasks: list[str]   # 子任务列表

plan = orchestrator.with_structured_output(Plan).invoke("研究RAG并写报告")
# plan.subtasks = ["研究RAG原理", "对比3个框架", "写综合报告"]

# 2. 用 Send 并行派发 worker（每个子任务一个 worker 实例）
return [Send("worker", {"task": sub}) for sub in plan.subtasks]

# 3. worker 节点干实际活
def worker(state):
    result = do_work(state["task"])
    return {"results": [result]}

# 4. synthesizer 合成所有 worker 结果
def synthesizer(state):
    return {"final": combine(state["results"])}
```

**vs 其他模式（关键区别）**

| | orchestrator-worker | prompt chaining | Subagents |
|---|---|---|---|
| 拆解方式 | **动态**（LLM 现场拆） | **静态**（预先定义步骤） | 不拆，主 agent 按需调 |
| 派发 | Send 并行 | 串行 | 主 agent ReAct 循环里调工具 |
| 编排者 | 结构化"拆+派+合"流程 | 固定管道 | 对话型 agent |
| 适合 | 复杂动态子任务、可并行 | 固定流水线 | 主 agent 智能调度子 agent |

**何时用**：任务复杂需先拆解、子任务可并行、子任务列表动态（不能预先定死）。

**一句话**：orchestrator-worker = "项目经理模式"--编排者拆活派活收活，worker 干活。动态版的项目分解，不是固定流水线。

### evaluator-optimizer 伪代码（🟢）
```python
# generator 生成
response = generator.invoke(input)
# evaluator 评估（structured output 给反馈）
eval = evaluator.with_structured_output(EvalResult).invoke(response)
# 条件边：通过则 END，否则带 feedback 回 generator
if eval.passed: return END
else: return Command(goto="generator", update={"feedback": eval.feedback})
```

---

## 3. 层3：multi-agent 5 模式（简表，详见 `Agent工程MultiAgent模式.md`）

| 模式 | 一句话 |
|---|---|
| Subagents | 主 agent 把子 agent 包 @tool 调度 |
| Handoffs | tool 返回 Command 改 state 触发切 agent |
| Skills | 单 agent 按需加载专门 prompt |
| Router | 路由步骤分类分发 |
| Custom workflow | StateGraph 自定义流（万物云用） |

详细伪代码/父子通信/检查题见 [`Agent工程MultiAgent模式.md`](./Agent工程MultiAgent模式.md)。

---

## 4. subagent 的 5 种形式（🟢 核实扩展，带伪代码）

不止 tool-per-agent 和 single-dispatch，共 5 种。**先分两组**：
- **A/B/C** 来自 multi-agent/subagents 页（通用 LangGraph multi-agent，主 agent 用 `create_agent`）
- **D/E** 来自 deepagents/subagents 页（Deep Agents 高层 harness，主 agent 用 `create_deep_agent`）

### 速览表

| 形式 | 是啥 | 何时用 | 来源 |
|---|---|---|---|
| A. Tool per agent | 每个 subagent 包独立 @tool | 子agent少，要细粒度控制 | 🟢 multi-agent/subagents |
| B. Single dispatch tool | 一个 task(agent_name,desc) 按名派发 | 子agent多，多团队独立开发 | 🟢 multi-agent/subagents |
| C. subagent 作 graph 节点 | 从 node function 调（不包 @tool） | 要读嵌套图状态（如 interrupt） | 🟢 multi-agent/subagents |
| D. SubAgent（字典） | 字典定义传 create_deep_agent | 用 Deep Agents，简单 subagent | 🟢 deepagents/subagents |
| E. CompiledSubAgent | 编译后的图当 subagent | 用 Deep Agents，subagent 本身复杂 | 🟢 deepagents/subagents |

---

### A. Tool per agent（🟢 原文伪代码）
每个 subagent 包成独立 @tool，主 agent 像调普通工具一样调。
```python
from langchain.tools import tool
from langchain.agents import create_agent

subagent = create_agent(model="...", tools=[...])   # 子 agent

@tool("research", description="Research a topic and return findings")
def call_research(query: str):
    result = subagent.invoke({"messages":[{"role":"user","content":query}]})
    return result["messages"][-1].content           # 只回传最终结果

main_agent = create_agent(model="...", tools=[call_research])  # 主 agent
```
- **何时用**：子 agent 少，要细粒度控制每个的输入/输出
- **后端类比**（🟡）：每个子 service 封成独立接口给门面调

### B. Single dispatch tool（🟢 原文伪代码）
一个参数化 `task(agent_name, description)` tool，按名字从注册表派发。
```python
SUBAGENTS = {"research": research_agent, "writer": writer_agent}  # 注册表

@tool
def task(agent_name: str, description: str) -> str:
    """Launch an ephemeral subagent. Available: research/writer"""
    agent = SUBAGENTS[agent_name]
    result = agent.invoke({"messages":[{"role":"user","content":description}]})
    return result["messages"][-1].content

main_agent = create_agent(model="...", tools=[task],
    system_prompt="You coordinate sub-agents. Use task tool to delegate.")
```
- **何时用**：子 agent 多、多团队独立开发、不想改主 agent 代码就能加新 agent
- **三种子 agent 发现方式**（🟢，主 agent 怎么知道有哪些子 agent）：
  - system prompt 枚举（<10 个，直接列在 prompt 里）
  - enum 约束（<10 个，agent_name 参数加 Enum 类型安全）
  - tool-based discovery（>10 个，加个 list_agents 工具按需查）
- **后端类比**（🟡）：统一 dispatch 接口按服务名路由，类似服务发现的 RPC 网关

### C. subagent 作 custom graph 节点（🟢）
**不包成 @tool**，从 custom graph 的 node function 里直接调 subagent。
```python
from langgraph.graph import StateGraph, START, END

def subagent_node(state):
    # 直接 invoke subagent（不包 tool），能被图管理、能读嵌套图状态
    result = subagent.invoke({"messages": state["messages"]})
    return {"messages": [result["messages"][-1]]}

graph = (StateGraph(State)
         .add_node("subagent_node", subagent_node)
         .add_edge(START, "subagent_node")
         .compile(checkpointer=...))
```
- **何时用**：需要读嵌套图状态（如 interrupt 期间用 get_state 查 subagent 内部状态）
- **官方原文**（🟢）："Because subagents are called inside tool functions, LangGraph cannot statically discover them... If you need to read nested graph state (e.g., during an interrupt), invoke the subagent from a node function in a custom graph instead."
- **关键区别**：A/B 包成 tool 后 LangGraph 静态发现不了 subagent 内部状态；C 作节点就能被图管理、能读嵌套状态
- **后端类比**（🟡）：子 service 不通过 RPC 调，而是作为流程节点内嵌进工作流图（像 Activiti 把逻辑直接写进 ServiceTask delegate，而不是调外部 service）

### D. SubAgent 字典定义（🟢 Deep Agents）
Deep Agents harness 里用字典定义 subagent，传 create_deep_agent。
```python
from deepagents import create_deep_agent

research_subagent = {
    "name": "research-agent",                     # 必需，主 agent 用这个名字调
    "description": "Used to research questions",   # 必需，主 agent 据此决定何时委派
    "system_prompt": "You are a great researcher", # 必需，子 agent 自己的指令
    "tools": [internet_search],                    # 可选，默认继承主 agent
    "model": "openai:gpt-5.5",                     # 可选，默认继承主 agent
}
agent = create_deep_agent(model="...", subagents=[research_subagent])
```
- **字段**（🟢）：name/description/system_prompt 必需；tools/model/middleware/interrupt_on/skills/response_format/permissions 可选
- **何时用**：用 Deep Agents（官方推荐高层 harness），subagent 逻辑简单（prompt + 工具）
- **后端类比**（🟡）：用配置（字典）声明一个子服务，框架自动装配

### E. CompiledSubAgent（🟢 Deep Agents）
把**编译后的 LangGraph 图**当 subagent（runnable 字段传 compiled graph）。
```python
from deepagents import CompiledSubAgent, create_deep_agent
from langchain.agents import create_agent

# 先建一个自定义 agent 图（可以是复杂 graph）
custom_graph = create_agent(model="...", tools=[...],
                            system_prompt="You are a specialized agent...")
# custom_graph 已是 compiled（create_agent 返回编译好的图）

custom_subagent = CompiledSubAgent(
    name="data-analyzer",
    description="Specialized agent for complex data analysis",
    runnable=custom_graph,    # 必需：传编译后的 LangGraph 图
)
agent = create_deep_agent(model="...", subagents=[custom_subagent])
```
- **字段**（🟢）：name/description 必需；runnable 必需（原文 "A compiled LangGraph graph, must call .compile() first"）
- **何时用**：用 Deep Agents，且 subagent 本身是复杂工作流（多节点子图、带反思/检索步骤）
- **官方原文**（🟢）："For complex workflows, use a prebuilt LangGraph graph as a CompiledSubAgent"
- **后端类比**（🟡）：把一个完整子工作流（子流程图）封装成可复用单元，主流程像调组件一样调它

---

### A vs B 区别（重点：tool 数量，别再搞混）

**核心区别**：
- **A**：N 个子 agent = **N 个独立 @tool**（主 agent tools 列表有 N 个，LLM 直接选一个调）
- **B**：N 个子 agent = **1 个 task tool** + agent_name 参数（主 agent tools 列表只有 1 个，LLM 调 task 传 agent_name 选）

**A 伪代码（多 tool）**：
```python
@tool("research", description="研究问题")
def call_research(query: str) -> str:
    return research_agent.invoke({"messages":[{"role":"user","content":query}]})["messages"][-1].content

@tool("writer", description="写内容")
def call_writer(query: str) -> str:
    return writer_agent.invoke({"messages":[{"role":"user","content":query}]})["messages"][-1].content

# 主 agent tools 列表有 2 个工具，LLM 看到 [research, writer] 直接选一个调
main_agent = create_agent(model=..., tools=[call_research, call_writer])
```

**B 伪代码（1 个 task tool + 注册表）**：
```python
SUBAGENTS = {"research": research_agent, "writer": writer_agent}  # 注册表

@tool
def task(agent_name: str, description: str) -> str:
    """Available: research/writer"""
    agent = SUBAGENTS[agent_name]   # 按名查注册表
    return agent.invoke({"messages":[{"role":"user","content":description}]})["messages"][-1].content

# 主 agent tools 列表只有 1 个工具，LLM 调 task(agent_name="research", description="...")
main_agent = create_agent(model=..., tools=[task])
```

**类比**（🟡）：
- A = 每个子 service 暴露独立端点（/research, /writer），客户端直接调对应端点
- B = 统一 dispatch 端点 /task?agent=research，客户端调统一端点带参数路由

**何时用 B**（A 的痛点）：
- 子 agent 多（几十个）时，A 让 tools 列表很长 -> LLM context 膨胀、选错工具
- B 只 1 个 tool，加新子 agent 不用改主 agent tools（只改注册表 + 用 prompt/enum/list_agents 告诉主 agent 有哪些）
- 多团队独立开发：各团队维护子 agent，主 agent 不用改

### 各形式父子交互对比（重点：怎么传参/返回/拿结果）

**A/B/D/E 都是 tool 机制**（主 agent 调工具 -> 工具跑子 agent -> 结果回 ToolMessage），**C 是唯一非 tool 的**（graph 节点 + state 流转）。

| 形式 | 传参方式 | 返回方式 | 主 agent 拿结果 | tool 怎么来 |
|---|---|---|---|---|
| A. Tool per agent | tool 参数(query) | return 字符串 | ToolMessage 进对话历史，LLM 解析 | 自写 N 个 @tool |
| B. Single dispatch | task 参数(agent_name, desc) | return 字符串 | ToolMessage 进对话历史 | 自写 1 个 task tool + 注册表 |
| C. graph 节点 | 节点读 state | return state 更新(dict) | 下个节点读 state | 不是 tool，是 graph 节点 |
| D. SubAgent 字典 | task 工具(name, task) | 最终消息 | ToolMessage 进对话历史 | Deep Agents 内置 task，声明字典 |
| E. CompiledSubAgent | task 工具(name, task) | 最终消息 | ToolMessage 进对话历史 | Deep Agents 内置 task，传编译图 |

**C 的交互详解**（非 tool，最不同）：
- 传参：节点函数读 state（不是 tool 参数）
- 返回：节点 return state 更新（dict），不是 ToolMessage
- 拿结果：节点的 return 更新 state，下个节点（或主流程）读 state
- 没有 tool_call/ToolMessage 这套，是 graph 的 state 流转
- 和 A/B 区别：A/B 是主 agent ReAct 循环里**动态**调 tool（LLM 现场决定调谁）；C 是图**静态**编排节点（边定义执行顺序，不是 LLM 决定）
- 后端类比（🟡）：A/B = RPC 调用（运行时动态调）；C = 工作流节点（编译时定死流程，像 Activiti 节点）

**D/E 的交互详解**（和 A 类似但不用自写 @tool）：
- Deep Agents **内置 task 工具**，你只声明 subagent（字典/编译图），框架自动让主 agent 能调 `task(name="...", task="...")`
- 传参：主 agent 调 task 工具传 name + 任务描述
- 返回：subagent 跑完，最终消息作为 ToolMessage 回主 agent，LLM 解析
- 和 A 区别：A 自己写 @tool + 自己 invoke subagent；D/E 只声明 subagent（字典/编译图），框架自动处理 task 调用和结果返回

---

### D vs E 区别（Deep Agents 两种 subagent 定义）
- **D（字典）**：声明式，给 prompt + 工具，框架内部装配。简单 subagent 用这个
- **E（CompiledSubAgent）**：传一个已编译的图，subagent 本身是复杂图。复杂 subagent 用这个
- **官方建议**（🟢）："For most use cases, define subagents as dictionaries. For complex workflows, use a CompiledSubAgent."

### 补充：subagent 通用特性（🟢）
- **默认无状态**：每次 invoke 全新上下文，记忆在主 agent 维护（见 `Agent工程MultiAgent模式.md` ①Subagents 父子通信）
- **可改有状态**：compile checkpointer=True，subagent 跨调用保持历史（continuations mode）
- **sync vs async**：sync（默认，主 agent 阻塞等结果）/ async（后台跑 job，主 agent 继续响应）
- **inputs/outputs 可定制**：inputs 可传 full context（不只 query）；outputs 可用 Command 回传额外 state
- **context 隔离**：subagent 干活过程不污染主 agent 上下文，主 agent 只收最终结果（解决 context bloat）

---

## 5. 层4：框架 team 抽象

市面上说的"team"主要三个来源：AutoGen 的 Team、CrewAI 的 Crew、老 LangGraph 的 Team（已消失）。

### 5.1 AutoGen（微软 v0.4+）4 种 Team（🟢 核实）

官方原文："A team is a group of agents that work together to achieve a common goal."

| Team | 编排方式 | 谁决定发言 | 适用 |
|---|---|---|---|
| **RoundRobinGroupChat** | 轮流发言，固定顺序循环 | 列表顺序 | 固定流程协作（生成->审查->改进） |
| **SelectorGroupChat** | LLM 每轮动态选下一个发言者 | LLM 模型选 | 动态协作、多专家 |
| **Swarm** | agent 通过 HandoffMessage 自主交接，无中央编排 | agent 自己决定交接给谁 | 去中心化、agent 自治 |
| **MagenticOneGroupChat** | Orchestrator 维护 Task Ledger(计划)+Progress Ledger(进度) | Orchestrator 委派 | 开放式 web/文件任务 |

伪代码（RoundRobin，🟢）：
```python
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat

primary = AssistantAgent("primary", model_client=..., system_message="...")
critic = AssistantAgent("critic", model_client=..., system_message="...回复 APPROVE 表示通过")

team = RoundRobinGroupChat([primary, critic],
                           termination_condition=TextMentionTermination("APPROVE"))
result = await team.run(task="写一首关于秋天的短诗")
```

**终止条件**（🟢 11种）：MaxMessage/TextMention/TokenUsage/Timeout/Handoff/SourceMatch/External... 可用 `&`(AND) `|`(OR) 组合。

**通信模型**（🟢）：**广播式**，所有 agent 共享同一份消息上下文，每个 agent 发言广播给所有人。

后端类比（🟡）：广播式 = 发布订阅，所有 agent 订阅同一消息总线。

### 5.2 CrewAI 2 种 Process（🟢 核实）

官方原文："A crew represents a collaborative group of agents working together to achieve a set of tasks."

三要素：
- **Agent**：role/goal/backstory/tools/allow_delegation
- **Task**：description/expected_output/agent/context（引用其他task输出）
- **Crew**：agents + tasks + process + manager_llm

| Process | 怎么跑 | 谁分派任务 |
|---|---|---|
| **Sequential**（默认） | 按 tasks 列表顺序，前 task 输出作下 task 上下文 | 固定顺序（task 预分配 agent） |
| **Hierarchical** | manager agent 动态分派、审查、评估 | manager_llm/manager_agent 动态分（task 不预分配） |

伪代码（Sequential，🟢）：
```python
from crewai import Agent, Crew, Task, Process

researcher = Agent(role="数据分析师", goal="分析数据趋势", backstory="...", verbose=True)
writer = Agent(role="报告撰写", goal="写清晰报告", backstory="...", verbose=True)

t1 = Task(description="收集市场数据", expected_output="趋势报告", agent=researcher)
t2 = Task(description="分析影响因素", expected_output="因素分析", agent=writer, context=[t1])

crew = Crew(agents=[researcher, writer], tasks=[t1, t2], process=Process.sequential)
result = crew.kickoff()
```

**通信模型**（🟢）：**任务驱动 + 上下文传递**，task 的 context 参数引用其他 task 输出；Crew 级 memory（short/long/entity）+ cache。

后端类比（🟡）：任务驱动 = 工作流引擎按任务节点顺序跑，节点间靠流程变量传上下文。

### 5.3 AutoGen vs CrewAI 核心差异（🟢）

| 维度 | AutoGen | CrewAI |
|---|---|---|
| 编排单位 | 消息（message） | 任务（task） |
| 通信 | 广播式共享消息上下文 | 任务上下文传递 + memory |
| 编排方式数 | 4种 | 2种 |
| 设计哲学 | 消息驱动多agent对话 | 任务驱动角色分工 |

### 5.4 "team" 市面说法澄清
- **AutoGen Team**：4种预设（RoundRobin/Selector/Swarm/MagenticOne），消息驱动
- **CrewAI Crew**：2种 Process（Sequential/Hierarchical），任务驱动
- **老 LangGraph Team**：已从官方文档消失（之前 Supervisor/Swarm/Team 三模式），现归入 multi-agent 5模式
- **Deep Agents**：LangChain 官方推荐的高层 harness（含 subagents/skills/planning/虚拟文件系统/上下文管理），类似框架级 team 封装

⚠️ 注意：AutoGen 的 **Swarm** 还在用（agent 间 HandoffMessage 交接），和 LangGraph 老 Swarm（已消失）不是一回事，别混。

### 5.5 老 LangGraph Team 历史（面试怎么说，🟢 核实）

**老的多 agent 模式**（已弃用）：
- 之前 LangGraph multi-agent 有 **Supervisor / Swarm / Team** 等模式，分别在 `langgraph-supervisor` / `langgraph-swarm` 包里
- `langgraph-supervisor`：`create_supervisor` 把 worker agent 作为 graph node，supervisor 用 handoff tool 路由
- `langgraph-swarm`：Swarm 模式（agent 间 handoff 交接）

**现状**（🟢 核实）：
- `langgraph-supervisor` / `langgraph-swarm` 包**不再维护**
- 官方重组 multi-agent 为 **5 模式**（subagents/handoffs/skills/router/custom workflow）
- 老 Supervisor ≈ 新 **Subagents**（主 agent 包子 agent 为 @tool 调度）
- 老 Swarm **概念消失**（注意：AutoGen 的 Swarm 还在，别混）
- 老 Team 概念归入 5 模式

**迁移映射**（🟢 ma_migrate_sup.txt 原文）：

| 老（langgraph-supervisor） | 新（subagents 模式） |
|---|---|
| `create_supervisor`（worker 作 graph node） | `create_agent` + subagents 包成 @tool |
| `output_mode`（消息历史） | 在 tool wrapper 里格式化输出 |
| `create_handoff_tool`（自定义路由） | 自定义 @tool 调 `subagent.invoke(...)` |
| 嵌套 supervisor（supervisor of supervisors） | subagent 包成 @tool 调其他 subagent（或扁平化） |

**老 vs 新代码对比**（🟢）：
```python
# 老：langgraph-supervisor（已弃用）
from langgraph_supervisor import create_supervisor
from langgraph.prebuilt import create_react_agent
research = create_react_agent(model=..., tools=[web_search], name="research_expert", prompt="...")
workflow = create_supervisor([research, math], model=..., prompt="Route research/math...")
app = workflow.compile(checkpointer=...)

# 新：subagents 模式（官方推荐）
from langchain.agents import create_agent
from langchain.tools import tool
research = create_agent(model=..., tools=[web_search], system_prompt="...")
@tool("research_expert", description="...")
def call_research(query: str) -> str:
    return research.invoke({"messages":[{"role":"user","content":query}]})["messages"][-1].content
supervisor = create_agent(model=..., tools=[call_research], system_prompt="...")
```

**面试口径**：
- "之前 LangGraph multi-agent 有 Supervisor/Swarm/Team 等模式在 langgraph-supervisor/swarm 包里，现在这些包不再维护，官方重组为 5 模式。老 Supervisor 对应现在的 Subagents（主 agent 包子 agent 为 tool 调度），Swarm 概念消失。迁移就是 create_supervisor -> create_agent + @tool 包子 agent。"
- 被追问 Swarm："LangGraph 老 Swarm 已消失，但 AutoGen 的 Swarm 还在（agent 间 HandoffMessage 交接），不是一回事。"

**万物云口径**：没用 langgraph-supervisor/swarm，直接用 StateGraph 自建（Custom workflow）。

### 5.6 Deep Agents 详解（面试怎么说，🟢 核实）

**是什么**（🟢 官方原文）：
> "Deep Agents is the easiest way to start building agents...with built-in capabilities for task planning, file systems for context management, subagent-spawning, and long-term memory."

- 是一个 **agent harness**（代理框架/外壳）
- 独立库 `deepagents`，构建在 LangChain 核心 + LangGraph 运行时之上
- 入口：`create_deep_agent`

**为什么官方推荐**（🟢 原文）：
> "It is the same core tool calling loop as other agent frameworks, but with built-in capabilities that make agents reliable for real tasks."

- 同样的工具调用循环（ReAct 风格），但内置一堆让 agent 在真实任务里可靠运行的能力
- `create_agent` 是"不需要这些内置能力时"的轻量替代

**和 create_agent 关系**（🟢，面试别说错）：
- 二者**并列**，都建在 LangChain 核心 + LangGraph 之上，共享同一核心工具调用循环
- **不是**上下层封装关系（总览页没说 Deep Agents 底层调 create_agent）
- create_agent = 裸工具调用循环；Deep Agents = 裸循环 + harness 内置能力

**核心能力清单**（🟢 全部内置）：

| 能力 | 是啥 | 内置工具/机制 |
|---|---|---|
| **subagents** | 生成临时子代理隔离上下文跑 | 内置 `task` 工具 |
| **skills** | 按 Agent Skills 标准（SKILL.md）渐进式加载 | 启动只读 frontmatter，需要才读全文 |
| **planning** | 维护带状态任务列表 | 内置 `write_todos` 工具（pending/in_progress/completed） |
| **虚拟文件系统** | 文件操作 | 内置 `ls/read_file/write_file/edit_file/delete/glob/grep/execute`，后端可插拔 |
| **上下文管理** | 四层：输入上下文 + 压缩(摘要/卸载) + 隔离(子代理) + 长期记忆 | -- |
| **memory** | 跨会话持久记忆 | `AGENTS.md` 文件，**始终加载**（区别 skills 按需） |
| **sandbox** | 隔离环境跑 shell | `execute` 工具 |
| **interpreter** | 跑 JavaScript | QuickJS 运行时，`eval` 工具，无 shell/网络 |
| **streaming** | 事件流 | `stream.subagents` 每个委派任务独立流 |
| **HITL** | 敏感工具前暂停审批 | `interrupt_on` 参数 + LangGraph interrupts |
| filesystem permissions | 声明式 read/write allow/deny | -- |
| prompt caching | 缓存 | Anthropic/Bedrock 默认开 |
| MCP 支持 | 接任意 MCP server | `tools=` 可接 MCP |

> 注：structured output 总览页没列，但 subagents 子页支持 `response_format`（subagent 返回结构化 JSON）。

**最小用例**（🟢）：
```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[my_tool],              # 自定义/MCP 工具
    system_prompt="...",
    subagents=[{                  # 子代理（字典定义，见第 4 节 D）
        "name": "research-agent",
        "description": "...",
        "system_prompt": "...",
    }],
    # 内置能力默认开启：planning/write_todos、filesystem、memory(AGENTS.md) 等
)
```

**适用场景**（🟢）：
- 官方："You can use deep agents for any task, including complex, multi-step tasks."
- 该用：复杂多步、需规划/文件上下文/子代理并行/长期记忆/代码执行/HITL 审批/长任务超单上下文窗口
- 不该用：不需要这些内置能力、想自己定制的，用 `create_agent` 或裸 LangGraph

**后端类比**（🟡）：
- `create_agent` = 裸 Servlet（自己写所有逻辑）
- `Deep Agents` = Spring Boot（内置文件/规划/记忆/子代理/审批等 starter，开箱即用）

**面试口径**：
- "Deep Agents 是 LangChain 官方推荐的高层 agent harness，基于 LangChain 核心 + LangGraph 运行时。和 create_agent 共享同一工具调用循环，但内置了规划(write_todos)、虚拟文件系统、子代理(task)、长期记忆(AGENTS.md)、skills(SKILL.md)、sandbox、HITL 等能力，让 agent 在真实复杂任务里可靠运行。create_agent 是不需要这些的轻量替代。"
- 被追问和 create_agent 关系："并列，不是上下层。都建在 LangGraph 上，Deep Agents 多一层 harness 内置能力。"
- **万物云口径**："我们没用 Deep Agents，用 LangGraph StateGraph 自建 + create_agent。但了解 Deep Agents 是官方推荐的复杂任务 harness。"

---

## 6. 业务场景对应实现

| 业务场景 | 推荐层次 | 具体模式 | 框架示例 |
|---|---|---|---|
| 客服分流（技术/商务/售后） | 层2 routing / 层3 Router | routing / Router | LangGraph Router / AutoGen Selector |
| 复杂研究（分解+并行查+合成） | 层2 orchestrator-worker / 层3 Subagents | orchestrator-worker / Subagents | LangGraph / Deep Agents |
| 代码生成+审查（生成->评估->改） | 层2 evaluator-optimizer | evaluator-optimizer | LangGraph / AutoGen RoundRobin |
| 确定性业务流（查单->分析->报告） | 层3 Custom workflow | StateGraph | 万物云用这个 |
| 多专家角色协作（研究员/作家/审校） | 层4 CrewAI | Sequential/Hierarchical | CrewAI Crew |
| 开放式 web 任务（浏览+操作） | 层4 AutoGen MagenticOne / Deep Agents | MagenticOne | AutoGen / Deep Agents |
| 去中心化 agent 自治交接 | 层4 AutoGen Swarm | Swarm | AutoGen |
| 单 agent 调工具完成任务 | 层1 ReAct | create_agent | LangChain create_agent |

---

## 7. 万物云口径（按真实）
- **层1**：ReAct（create_agent 默认工具调用循环）
- **层3**：Custom workflow（StateGraph 自定义执行流，🔴 推断归类，源文档没明确）
- **没用** AutoGen/CrewAI（用 LangGraph 自建）
- **面试口径**："我们用 LangGraph StateGraph 自定义工作流编排 agent 节点，单 agent 用 create_agent（ReAct 风格工具调用循环）。没用 AutoGen/CrewAI，但了解它们的设计（AutoGen 消息驱动 team、CrewAI 任务驱动 crew）。"

---

## 8. 关键纠偏（面试别说错）
1. ReAct/Plan-and-Execute/Reflection 等命名模式当前 LangChain 官方**弃用概念页**，create_agent 默认就是 ReAct 风格；Plan-and-Execute≈orchestrator-worker，Reflection≈evaluator-optimizer
2. ToT/Reflexion/ReWOO/Self-Ask 是历史/学术模式，当前官方无专门页，旧版实验性已下线--知道概念即可，别说"LangChain 官方推荐 ToT"
3. subagent 不止 2 种形式，共 5 种（含 subagent 作 graph 节点、CompiledSubAgent）
4. "team" 不是 LangGraph 专属：AutoGen Team（4种）/ CrewAI Crew（2种）/ Deep Agents 都算
5. AutoGen Swarm（还在）≠ LangGraph 老 Swarm（已消失）
6. 层次别混：ReAct 是层1（agent 内部思考），multi-agent 是层3（agent 间协作），team 是层4（框架封装）

---

## 9. 选择决策树
```
任务单 agent 能搞定？-> 层1 create_agent (ReAct)
  ├ 要先规划再执行？-> 层2 orchestrator-worker
  ├ 要生成-评估-改进？-> 层2 evaluator-optimizer
  ├ 固定流水线？-> 层2 prompt chaining
  └ 要并行/投票？-> 层2 parallelization
任务要多个 agent 协作？
  ├ 主 agent 调度子 agent？-> 层3 Subagents
  ├ 状态切换 agent？-> 层3 Handoffs
  ├ 分类分发？-> 层3 Router
  ├ 单 agent 多技能？-> 层3 Skills
  └ 确定性业务流？-> 层3 Custom workflow（万物云）
要框架级 team 封装？
  ├ 消息驱动对话？-> AutoGen Team（RoundRobin/Selector/Swarm/MagenticOne）
  ├ 任务驱动角色分工？-> CrewAI Crew（Sequential/Hierarchical）
  └ 长任务 harness？-> Deep Agents
```
