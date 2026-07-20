# Agent 工程 LangGraph 心智模型（地基）

> 这是 multi-agent / 流式 / HITL 所有内容的**地基**。读主辅导文档第 24 步前先看这个。
> 不懂这个，第 24 步的 5 模式、Command、interrupt 全是天书。
>
> 标注：🟢 官方 graph-api 文档明确 / 🟡 后端类比（Activiti，非官方，帮理解用）/ 按真实 = 万物云实际做法

---

## 1. LangGraph 是什么（一句话）

**LangGraph = 一个图执行引擎**，类比 Activiti 工作流引擎。

你定义一张图（StateGraph），引擎按"节点-边"跑，状态在节点间流转，能存档、能暂停、能恢复。前面第 22 步的流式、第 23 步的 HITL、第 24 步的 multi-agent，全都是搭在这个图引擎上的不同用法。

---

## 2. 图的 5 个元素（🟢 官方 + 🟡 Activiti 对照）

| LangGraph | Activiti 对应 | 是啥 | 一句话 |
|---|---|---|---|
| **State** | Process Variable（流程变量） | 图运行时流转的数据，是个 dict，所有节点读写 | "流程里带着走的数据包" |
| **Node** | Service Task（任务节点） | 图的一个处理步骤，**就是个普通函数** `def node(state) -> dict` | "图上的一个处理点" |
| **Edge** | Sequence Flow + Gateway（连线+网关） | 节点间流转，三种：固定/条件/动态 | "节点之间怎么连" |
| **Checkpointer** | ACT_RU_EXECUTION 持久化表 | 把 state 落库，支持恢复/回放/HITL | "流程存档点" |
| **START / END** | startEvent / endEvent | 图的入口和出口 | "图的起止" |

---

## 3. node 是什么（关键澄清，最容易搞错的地方）

**node ≠ agent。node 是个普通函数，函数里装啥都行：**

- 普通业务逻辑（查 DB、调接口、算数）
- 一次 LLM 调用
- 一个完整 agent（`create_agent()` 包出来的）
- 另一张子图（subgraph）

类比（🟡）：Activiti 的 ServiceTask 里 delegate 代码可以是任何 Java 逻辑。node 一样，是个壳，里面装啥都行。

### 单 agent vs multi-agent 在图上的区别

```
单 agent:    START -> [agent_node] -> END
             （一个 node 里放一个 agent）

multi-agent: START -> [router_node] -> [sales_agent / support_agent] -> END
             （多个 node 各放一个 agent，用 edge 串起来）
```

**所以 multi-agent 不是新东西**，就是"图里放多个 agent-node，用边连起来"。第 24 步的 5 种模式 = "怎么组织这些 agent-node 和它们之间跳转"的 5 种套路，不是 5 个新引擎。

---

## 4. 控制流两个维度（Command vs interrupt，🟢）

这是最该归纳的一块。控制流有**两个正交维度**：

### 维度 A：流转控制（节点之间怎么走）
- 静态：`add_edge("A", "B")` -- 固定 A->B
- 条件：`add_conditional_edges("A", router_fn)` -- 按函数返回选边
- 动态：节点 `return Command(goto="B")` -- 代码里跳，最灵活

### 维度 B：HITL 暂停（停下来等人类）
- 静态配置：`compile(interrupt_before=["X"])` -- 编译时定"X 节点前停"
- 动态触发：节点内 `interrupt()` -- 跑到一半主动停
- 恢复：`Command(resume=...)` -- 把人输入塞回去接着跑

### 对照表（🟢 + 🟡）

| | Command | interrupt_before / after | interrupt() |
|---|---|---|---|
| 管啥 | **流转**（走哪+带啥状态） | **HITL 暂停** | **HITL 暂停** |
| 谁触发 | 节点**执行完** return | **编译时**配置 | 节点**执行中**主动调 |
| 类型 | 动态 | 静态 | 动态 |
| Activiti 类比（🟡） | 节点代码里 setVariable+路由 | 流程定义里设 receiveTask | 节点代码里挂起等 signal |
| 什么时候用 | handoff/router/正常跳转 | 提前知道某节点要人工审核 | 节点跑到一半才发现要问人 |

### 一句话归纳（记住这句）

> **Command 管"走"，interrupt 管"停"，停完用 `Command(resume=...)` 接着走。**

Command 不是 multi-agent 专属，它是 LangGraph 的**统一控制流原语**：`goto/update` 管流转，`resume` 管 HITL 恢复。一个原语管两件事。

---

## 5. 串起前面的步骤（重要，别再以为是两套东西）

- 第 22 步流式：`stream_events` 读图执行过程的事件
- 第 23 步 HITL：`Command(resume=...)` 恢复暂停
- 第 24 步 multi-agent：`Command(goto=..., update=...)` 在 agent-node 间跳转

**第 23 步的 `Command(resume=...)` 和第 24 步的 `Command(goto=...)` 是同一个 Command 的两个用法**，不是两套东西。之前分两步讲，容易以为是分裂的，实际是一个原语：
- `resume` = HITL 恢复那个用法
- `goto/update` = 流转控制那个用法

---

## 6. 万物云口径（按真实，面试照实说）

- HITL 用 `interrupt_before`（**静态配置**，编译时定哪个节点前停），**不是**官方推荐的动态 `interrupt()`
- 恢复用 `Command(resume=...)`（不管哪种暂停，恢复都走这个）
- 面试口径："我们用 `interrupt_before` 在指定节点前暂停等人工审核，恢复用 `Command(resume=...)`。知道官方现在推荐动态 `interrupt()` + `HumanInTheLoopMiddleware`，但我们项目用的是静态配置。"

---

## 7. 最小可跑骨架（把 5 元素 + Command + interrupt 全串起来，🟢 graph-api）

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command, interrupt

# ① State = 流程变量（dict schema）
class State(TypedDict):
    messages: list
    current_step: str

# ② Node = 普通函数，里头装啥都行
def router_node(state) -> Command:            # 装业务逻辑：分类 + 跳转
    step = classify(state["messages"][-1])
    return Command(goto=f"{step}_agent",       # 流转：跳到对应 agent 节点
                   update={"current_step": step})  # 改 state

def support_agent_node(state):                 # 装 agent
    result = support_agent.invoke(state)
    return {"messages": [result]}

def review_node(state):                        # HITL：跑到一半暂停问人
    decision = interrupt({"need": "approve"})  # 暂停，等 Command(resume) 恢复
    return {"messages": [decision]}

# ③ Edge = 流转
graph = (StateGraph(State)
    .add_node("router", router_node)
    .add_node("support_agent", support_agent_node)
    .add_node("review", review_node)
    .add_edge(START, "router")                 # 固定边
    .add_edge("support_agent", "review")
    .add_edge("review", END)
    .compile(
        checkpointer=PostgresSaver(...),       # ④ Checkpointer = 持久化
        interrupt_before=["review"]            # ⑤ HITL 静态暂停点（万物云用这个）
    ))
```

### 逐行对应 5 元素
1. `State(TypedDict)` -- ① State（流程变量 schema）
2. `router_node` / `support_agent_node` / `review_node` -- ② Node（普通函数，分别装业务逻辑/agent/HITL）
3. `add_edge(START, "router")` -- ③ Edge（固定流转）；`router_node` 里 `Command(goto=...)` -- ③ Edge 的动态形式
4. `checkpointer=PostgresSaver(...)` -- ④ Checkpointer（持久化存档）
5. `interrupt_before=["review"]` -- 维度 B 的 HITL 静态暂停；`review_node` 里 `interrupt()` -- 维度 B 的动态暂停；恢复用 `Command(resume=...)`

---

## 8. 检查题（验证地基通了没，答出来再回第 24 步）

1. node 是 agent 吗？一个图里的 node 可以是什么？单 agent 和 multi-agent 在图上区别是啥？
2. Command 和 interrupt 各管啥？为啥说"一个管走一个管停，停完用 Command(resume) 接着走"？
3. 第 23 步的 `Command(resume=...)` 和第 24 步的 `Command(goto=...)` 是两套东西吗？为啥不是？
4. `interrupt_before` 和 `interrupt()` 区别？万物云用哪个？官方推荐哪个？

---

## 9. 地基检查题答案（复盘，面试口径）

### Q1：node 是 agent 吗？单/多 agent 区别？条件边是 if 吗只有这种？

**用户原答**：node 是函数能装任何东西（create_agent 等），单/多 agent 就是每个 agent 作为 node，条件边路由是 if 吗只有这种逻辑吗。

**标准答案/补充**：
- node 是函数、装啥都行、单/多 agent 区别 ✅ 对
- 条件边**不止 if**。流转控制有三种（🟢 graph-api）：

| 方式 | API | 是啥 | Activiti 类比（🟡） |
|---|---|---|---|
| 静态固定 | `add_edge("A","B")` | A 永远去 B，写死 | 固定连线 |
| 条件 | `add_conditional_edges("A", fn, {"x":"nodeX","y":"nodeY"})` | fn 返回值决定去哪 = if/switch | 排他网关（XOR gateway） |
| 动态 | 节点内 `return Command(goto="B")` | 代码里直接跳，不预定义映射 | 节点代码强制跳转 |

- 条件边确实是 if（排他网关），用户理解对，但**不是唯一**。Command(goto) 是更灵活的动态跳（运行时算出跳哪，不用预先配映射）。

### Q2：Command 管"走" interrupt 管"停"？Command 只 langgraph 能用？interrupt 像 await 吗？

**用户原答**：一个继续一个停，Command 只有 langgraph 能用？什么方式停才能用，类似线程里的 await 吗。

**标准答案/补充**：
- "一个走一个停" ✅ 对
- **Command 只 langgraph 能用？** Command 这个原语是 langgraph 的（框架内控制流）。但"中断-恢复"这个**模式**别的框架也有（🟡 类比）：
  - Activiti：receiveTask 挂起 + `signal()` 恢复
  - 线程：`await` / `Object.wait()` + `notify()` 恢复
  - langgraph：`interrupt()` + `Command(resume=)` 恢复
- **interrupt 像 await 吗？** 很贴切的类比（🟡），但有本质区别：

| | await（线程） | interrupt()（langgraph） |
|---|---|---|
| 相似 | 执行到某点挂起，等外部唤醒 | 执行到某点挂起，等外部唤醒 |
| 作用域 | **同进程内**（线程挂起占内存，唤醒继续） | **跨请求/跨进程** |
| 机制 | 线程阻塞等 notify | state 落 checkpointer（DB），HTTP 请求结束返回；新请求带 Command(resume=) 读档接着跑 |
| Activiti 类比（🟡） | -- | receiveTask 持久化到 ACT_RU_EXECUTION，外部 signal 新请求恢复 |

- 关键：interrupt **不是"线程挂着等"**，是"**存档退出，下次读档继续**"。节点函数到 interrupt() 处，整个 state 落库，当前 HTTP 请求结束返回前端；用户审核后发**新的 HTTP 请求**带 Command(resume=)，引擎从 checkpointer 读 state 接着 interrupt() 后面跑。
- **什么方式停才能用 Command(resume)？** 必须是 interrupt 系列停的（interrupt_before/after 静态 或 interrupt() 动态）。普通节点正常执行完不需要 resume，直接 Command(goto) 流转即可。

### Q3：Command(resume=) 和 Command(goto=) 是两套吗？

**用户原答**：一个恢复对话，一个路由到节点去执行。

**标准答案/补充**：
- ✅ 对，理解到位
- 补充：是同一个 Command 类的两个参数，不是两套系统。resume 用于 HITL 恢复，goto/update 用于正常流转，**场景不混用**：
  - HITL 暂停后恢复 -> `Command(resume={...})`
  - 正常节点间跳转 -> `Command(goto=..., update=...)`

### Q4：interrupt_before 和 interrupt() 区别？打断后分别怎么恢复？

**用户原答**：不清楚区别，打断后分别怎么恢复。

**标准答案/补充**：
- **区别（在哪停、谁触发）**：

| | interrupt_before/after | interrupt() |
|---|---|---|
| 触发 | 编译时静态配置 `compile(interrupt_before=["X"])` | 节点内动态调用 |
| 在哪停 | X 节点**执行前**（before）/执行后（after） | 节点函数跑到 `interrupt()` 这行 |
| 改节点代码 | 不改 | 要在节点里写 interrupt() |
| 适合 | 提前知道 X 要人工审核 | 跑到一半才发现要问人 |

- **打断后怎么恢复？关键：两种打断，恢复方式一样，都是 `Command(resume=...)`（🟢）**
  - 不管 interrupt_before 停的还是 interrupt() 停的，恢复都走 `Command(resume={"approved": True})`
  - 引擎从 checkpointer 读 state，从暂停点接着跑
  - interrupt 管"在哪停"，Command(resume) 管"停完怎么接着走"
- **万物云口径（按真实）**：用 interrupt_before（静态），恢复用 Command(resume=)
- **面试口径**："两种暂停——interrupt_before 编译时静态配暂停点，interrupt() 节点内动态暂停。但恢复统一用 Command(resume=)，引擎从 checkpoint 接着跑。我们项目用 interrupt_before，知道官方现在推荐 interrupt() + HumanInTheLoopMiddleware。"
