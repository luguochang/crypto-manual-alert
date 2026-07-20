# Agent 工程 Command 全量总结（基础补课）

> 前面第 23 步（HITL）、第 24 步（multi-agent）、Handoffs 里都出现 `Command(...)`，但长得不一样，看着像三套东西。这篇一次性讲透：Command 是啥、语法、所有用法、为什么各处不同。
>
> **没懂这个，Handoffs / multi-agent / HITL 全是半懂。** 看完这篇再回 Handoffs。
>
> 标注：🟢 官方文档确认（来自已核实的 handoffs/subagents/router 官方页用法）/ 🟡 后端类比 / 🔴 推断或待核

---

## 1. Command 是什么（一句话先立住）

**Command 是 LangGraph 的一个类（在 `langgraph.types` 里），它是一个"控制流对象"--你 return 一个 Command，等于一次性告诉引擎两三件事：**

1. **改 state**（update）：把哪些字段写进流程变量
2. **跳节点**（goto）：下一步去哪个 node
3. **恢复 interrupt**（resume）：把人的输入塞回去接着跑（HITL 专用）

**关键：这三件事不是三套 API，是同一个 Command 类的三个参数。** 你按需组合，return 出去，引擎按 Command 里的指示执行。

后端类比（🟡）：
- Command 像 Activiti 节点 delegate 里 `execution.setVariable(...)`（改流程变量）+ 强制跳转合一
- 也像 Spring MVC 里 `return "redirect:/path"` + model attribute--一个返回值既带数据又带跳转指令
- 还像普通 Java 方法 `return new Result(data, nextRoute)`--返回值同时携带"数据"和"下一步去哪"

**所以 Command 不是"新东西"，是"把改 state 和跳节点打包成一个返回值"的语法。** 不用 Command 你也能干活（用 add_edge + return dict），但用了 Command 更灵活（运行时动态决定跳哪）。

---

## 2. 为什么各处看起来不同（核心困惑点，先解开这个）

你在不同步看到这些，以为是不一样的东西：

| 出现位置 | 代码 | 你可能以为 |
|---|---|---|
| 第23步 HITL | `Command(resume={"approved": True})` | "恢复专用的 Command" |
| 第24步 router | `Command(goto="sales_agent")` | "跳转专用的 Command" |
| Handoffs | `Command(goto="sales_agent", update={...}, graph=Command.PARENT)` | "又一个新 Command？还有 graph？" |

**真相：全是同一个 Command 类，只是填了不同参数。**

- 第23步只填了 `resume`（恢复用，不用跳不用改）
- 第24步只填了 `goto`（跳转用，不改 state）
- Handoffs 填了 `goto + update + graph`（跳转 + 改 state + 作用父图，三件齐上）

**就像同一个 HashMap，你可以 put 一个键、put 两个键、put 三个键，不是三个 HashMap。** Command 一样，参数按需填，缺的参数就是"这事不干"。

---

## 3. Command 的参数全表（🟢 已核实用法）

从官方 handoffs/subagents/router 页用到的 Command，归纳出这些参数（🟢 都是官方用法里出现过的）：

| 参数 | 类型 | 干啥 | 出现在 | 来源 |
|---|---|---|---|---|
| `update` | dict | 把 dict 里的字段**合并**进当前 state（不是替换整个 state） | subagent outputs / handoffs | 🟢 ma_subagents / ma_handoffs |
| `goto` | str 或 list[str] | 下一步跳到哪个 node（可多个=并行） | router / handoffs | 🟢 ma_router / ma_handoffs |
| `resume` | Any | HITL 恢复时，把人的输入塞回 `interrupt()` 处 | 第23步 HITL | 🟢 心智模型文档 / 第23步 |
| `graph` | `Command.PARENT` | 这个 Command 作用于**父图**而非当前子图（subgraph 场景） | handoffs multiple subgraphs | 🟢 ma_handoffs |

**注意**：
- `update` 是**合并**不是替换。你 `update={"current_step":"X"}`，state 里其他字段不变，只改 current_step。🟢
- `goto` 可以是 list（多个节点并行跳），但常用单个 str。🟡
- `resume` 和 `goto/update` **不混用**：HITL 恢复用 resume，正常流转用 goto/update。🟢
- `graph=Command.PARENT` 只在**子图（subgraph）里**用--你在子图节点里 return Command，默认作用于子图内部；要跳父图的节点或改父图的 state，才加 `graph=Command.PARENT` 把命令"冒泡"给父图。🟢

🔴 **待核**：Command 类可能还有其他参数（如 `end`/`meta` 等），已核实用法里没出现，这篇不展开。要用时查官方 API。

---

## 4. Command 的 5 种用法（每种：场景 + 伪代码 + 在哪步出现）

### 用法 1：纯 update（只改 state，不跳转）

场景：节点跑完想改 state，但下一步走哪由图的 edge 决定（不用 Command 跳）。

```python
def research_node(state) -> Command:
    result = do_research(state["query"])
    return Command(update={"research_result": result})  # 只改 state，不指定 goto
    # 下一步走哪 = 看 add_edge 配的边
```

出现：subagent outputs（🟢 ma_subagents：subagent 把结果写回主 agent state 用 `Command(update={...})`）

后端类比（🟡）：Activiti delegate 里 `execution.setVariable("k", v)` 改完变量，流程按连线继续。

### 用法 2：纯 goto（只跳转，不改 state）

场景：根据运行时条件跳节点，但不改 state。

```python
def route_node(state) -> Command:
    agent = classify(state["query"])        # 运行时算出跳哪
    return Command(goto=agent)              # 只跳，不改 state
```

出现：router 模式（🟢 ma_router：`Command(goto=active_agent)`）

后端类比（🟡）：Activiti 节点代码里强制跳转 `execution.execute(activityId)`，不碰变量。

**和 add_conditional_edges 区别**（常见疑问，下面 Q3 详讲）：
- `add_conditional_edges("A", fn, {"x":"nodeX"})`：**编译时**配好映射 fn 返回 "x" -> nodeX，运行时 fn 返回值查表跳。映射写死。
- `Command(goto=agent)`：**运行时**直接算出节点名跳，不用预配映射。更灵活，但跳哪完全靠代码逻辑，图静态分析看不到。

### 用法 3：goto + update（跳转 + 改 state，最常见组合）

场景：跳节点的同时改 state。

```python
def router_node(state) -> Command:
    step = classify(state["messages"][-1])
    return Command(
        goto=f"{step}_agent",              # 跳到对应 agent 节点
        update={"current_step": step}      # 同时把当前步骤写进 state
    )
```

出现：handoffs single agent + middleware（🟢 ma_handoffs）、心智模型文档骨架

后端类比（🟡）：Activiti delegate 里 `setVariable` + 跳转合一。

### 用法 4：goto + update + graph=PARENT（subgraph 里跳父图节点）

场景：你在**子图（subgraph）**的节点里，要跳**父图**的另一个节点（不是子图内部的节点）。

```python
# 这个 tool 在子图的 agent 节点里被调用
@tool
def transfer_to_sales(runtime) -> Command:
    return Command(
        goto="sales_agent",               # 跳父图的 sales_agent 节点
        update={"active_agent": "sales_agent"},
        graph=Command.PARENT               # 关键：命令冒泡到父图（否则只作用于子图内部）
    )
```

出现：handoffs multiple subgraphs（🟢 ma_handoffs）

**graph=Command.PARENT 是啥**（🔴 推断澄清，官方代码有但没直说原理）：
- 子图是一个独立 StateGraph，它有自己的节点和边。（subgraph 全貌--是什么、和包 tool 的可见性区别、父子图交互--看《Agent工程Subgraph全量总结》）
- 子图节点里 `return Command(goto="X")` 默认跳**子图内部**的 X 节点。
- 但 handoffs 要跳的是**父图**的另一个 agent 节点（sales_agent 在父图里），所以加 `graph=Command.PARENT` 告诉引擎"这个 goto/update 作用于父图，不是子图"。
- 类比（🟡）：Activiti 子流程里抛事件，父流程的事件监听器接住处理--子流程影响父流程，要"冒泡"。

### 用法 5：resume（HITL 恢复，和上面 4 个不一样的地方：它是新请求传入的）

场景：图被 interrupt 暂停了（interrupt_before 或 interrupt()），人审核完，用 resume 把结果塞回去接着跑。

```python
# 注意：这是"恢复"调用，不是节点 return
graph.invoke(
    Command(resume={"approved": True}),    # 把审核结果塞回 interrupt() 处
    config={"configurable": {"thread_id": "xxx"}}
)
```

出现：第23步 HITL（🟢）

**关键区别**：用法 1-4 都是**节点函数 return** 一个 Command（引擎执行到节点末尾拿到 Command 去跳/改）；用法 5 是**新请求 invoke 时传入** Command(resume)（图已经停了，新请求用它读档接着跑）。

**resume 的机制**：图暂停后 state 落 checkpointer，HTTP 请求结束返回前端；用户审核后发**新请求**带 `Command(resume=...)`，引擎从 checkpointer 读 state，把 resume 的值交回 `interrupt()` 处，接着跑后面的代码。

后端类比（🟡）：Activiti receiveTask 挂起落库，外部 `signal(payload)` 新请求恢复。

---

## 5. Command 和 interrupt/HITL/goto 的关系（一张图理清，别再以为是冲突）

```
控制流两件事：
├── 走（流转 + 改 state）  -> Command(goto=..., update=...)    [用法 1/2/3/4]
└── 停（HITL 暂停）        -> interrupt_before / interrupt()
       └── 停完接着走       -> Command(resume=...)              [用法 5]
```

- **interrupt 管"在哪停"**：interrupt_before（编译时配）/ interrupt()（运行时调）
- **Command 管"怎么走"**：goto/update（正常流转）/ resume（恢复后接着走）
- **停完用 Command(resume) 接着走**：不管哪种 interrupt 停的，恢复都走 Command(resume=)

**所以 Command 和 interrupt 不是对立，是配合**：
- 正常流转：node return `Command(goto/update)` -> 引擎跳节点
- HITL：node 遇到 `interrupt()` 或 `interrupt_before` -> 停 -> 人审核 -> 新请求 `Command(resume)` -> 接着跑（跑完可能又 return `Command(goto)` 跳下一个节点）

**一句话**（心智模型那句，再强调）：
> **Command 管"走"，interrupt 管"停"，停完用 `Command(resume=...)` 接着走。**
> 但"走"有两种走法：正常流转走 `goto/update`，HITL 恢复走 `resume`。都是同一个 Command 类。

---

## 6. 常见疑问预判（一口气讲透，别看完一堆疑问）

**Q1：Command 是函数还是类？**
类（在 `langgraph.types`）。你 `from langgraph.types import Command`，然后 `Command(goto=...)` 是构造一个 Command 对象 return 出去。🟢

**Q2：Command 只能在 node 里 return 吗？**
不是。Command 可以在三个地方出现（🟢）：
- **node 函数 return**：`def node(state) -> Command: return Command(goto=...)`
- **tool 函数 return**：handoffs 的 `@tool def transfer_to_sales(...) -> Command: return Command(goto=..., graph=PARENT)`
- **恢复调用传入**：`graph.invoke(Command(resume=...))`（用法5，不是 return，是新请求的参数）

**Q3：Command(goto) 和 add_conditional_edges 都能跳节点，用哪个？**
- `add_conditional_edges("A", fn, {"x":"nodeX"})`：**编译时**配好映射表，运行时 fn 返回 "x" 查表跳 nodeX。映射写死，图结构静态可分析。
- `Command(goto=agent)`：**运行时**直接算出节点名跳，不用预配映射表。更灵活，但跳哪完全靠代码逻辑，图静态分析看不到。
- 选择：能用 add_conditional_edges 就用（图结构清晰、跳哪是有限集合）；运行时才知道跳哪（如 LLM 动态决定 agent 名）用 Command。🟡

**Q4：graph=Command.PARENT 什么时候用？**
只在**子图（subgraph）节点里**，且要跳/改**父图**的东西时用。单图（没子图）不用。handoffs multiple subgraphs 才用。🟢
- 你在普通 StateGraph（没子图）里 return Command(goto="X")，不用 graph 参数。
- 你在子图节点里 return Command(goto="X")，默认跳子图内部的 X；要跳父图的 X，加 graph=Command.PARENT。

**Q5：return Command 和 return dict 啥区别？**
- `return {"key": val}`：只改 state，下一步走 edge 配的边（等价用法1的简化版）
- `return Command(update={...})`：改 state（同上），但 Command 是显式控制流对象
- `return Command(goto=..., update=...)`：改 state + 动态跳（dict 做不到跳转）
- 简单改 state 用 dict 够；要动态跳或恢复，用 Command。🟡

**Q6：为什么 Handoffs 里 tool 能 return Command？不是 tool 该返回结果给 LLM 吗？**
LangGraph 的 tool 机制支持 tool 返回 Command（不只是返回字符串结果）。tool return Command 时，引擎把 Command 当作"控制流指令"执行（跳节点/改 state），而不是把 Command 当 tool 结果塞回 LLM。🟢 ma_handoffs 的 handoff tool 就是 return Command。
- 但要注意：handoff tool 如果改了 messages（handoff 常改），必须配 `ToolMessage` 闭合 tool-call 循环（LLM 调 tool 期待响应，ToolMessage 是那个响应，没有它对话历史就坏了）。这点 Handoffs 文档详讲。

**Q7：Command 是 multi-agent 专属吗？**
不是。Command 是 LangGraph 的**通用控制流原语**，单 agent 图也能用（任何 node 都能 return Command 跳转）。multi-agent 只是 Command 的一个使用场景（agent-node 间跳转）。🟢

---

## 7. 万物云口径（按真实，面试照实说）

- **HITL 恢复**：用 `Command(resume=...)` 恢复 interrupt_before 暂停 🟢
- **multi-agent 流转**：万物云用 StateGraph **条件边（add_conditional_edges）**路由为主，**不是**靠 Command(goto) 🟡（推断：万物云用 StateGraph，条件边是标准路由方式；万物云是否也用了 Command(goto) 🔴 待核）
- **没用 subgraph + Command.PARENT**：万物云 multi-agent = Custom workflow（StateGraph），agent 作为节点，节点间条件边路由，没用 handoffs 的 subgraph + PARENT 形式 🔴 推断
- 面试口径："Command 是 LangGraph 的控制流原语，goto/update 管流转，resume 管 HITL 恢复。我们万物云 HITL 恢复用 Command(resume)，multi-agent 路由主要用条件边，没用 handoffs 的 subgraph + Command.PARENT 那套。"

---

## 8. 检查题（看完这篇答，答得出再回 Handoffs）

1. Command 是什么？它把哪几件事打包成一个返回值？
2. 第23步的 `Command(resume=...)` 和 Handoffs 的 `Command(goto, update, graph=PARENT)` 是同一个东西吗？为什么看着不一样？
3. Command 的 4 个参数（goto/update/resume/graph）各干啥？`graph=Command.PARENT` 什么时候用？
4. `return Command(goto="X")` 和 `add_conditional_edges("A", fn, {"x":"X"})` 都能跳 X，区别是啥？
5. tool 函数能 return Command 吗？handoffs 的 handoff tool 为什么 return Command 而不是返回字符串？
6. interrupt 和 Command 什么关系？"停完用 Command(resume) 接着走"怎么理解？resume 和 goto/update 能同时用吗？

## 9. 参考答案（🟢 核实自 ma_handoffs.txt + 官方 Command 文档）

> 用户未先作答，直接给标准答案。三色：🟢 官方确认 / 🟡 通用规范或后端类比 / 🔴 推断待核。
>
> 题3/题5 提到 subgraph，不清楚是啥先看《Agent工程Subgraph全量总结》第 0 节（专门从源头讲 subgraph 是 langgraph 概念、为啥不是多余、和 subagent 区别）。

**1. Command 是什么？打包哪几件事？**
Command 是 LangGraph 的统一控制流原语类（`langgraph.types.Command`），一个对象表达"图接下来怎么走 + 顺便改 state"（🟢）。打包 4 件事：goto（跳哪个节点）/ update（改 state）/ resume（HITL 恢复传值）/ graph（冒泡到哪层图，Command.PARENT）（🟢）。核心一句：Command 管"走（goto/update）+ 停完接续（resume）"（🟡 总结口径）。后端类比（🟡）：Command = Activiti 流程引擎把"出流 + 设变量"打包成一个 transition 对象，节点 return Command = 节点执行完返回"下一步指令"而不是节点内部直接跳。

**2. 第23步 Command(resume) 和 Handoffs Command(goto,update,graph=PARENT) 是同一个东西吗？**
是同一个类 `langgraph.types.Command`（🟢）。看着不一样是因为**同类不同参数组合**：resume 模式只填 resume 参数（HITL 恢复），handoff 模式填 goto+update+graph=PARENT（跳转+改 state+冒泡父图）（🟢）。同一个类不同参数 = 不同用法，这就是为什么各处看着像 3 个东西（见第 2 节）。后端类比（🟡）：同一个 Activiti Command 对象，填 transitionId 走跳转、填 variables 设变量、填 signal 触发信号，填啥干啥。

**3. 4 个参数各干啥？graph=PARENT 什么时候用？**
- goto（str|list）：跳到哪个节点，单点或列表（🟢）
- update（dict）：合并进 state 的字段值（走的同时改 state）（🟢）
- resume（Any）：HITL 恢复时传入的值，给 interrupt 接续用（🟢）
- graph（Command.PARENT）：命令冒泡到父图，子图里的命令传给父图执行（🟢）
- graph=PARENT 何时用：在 subgraph（子图）里，子图节点 return 的 Command 想让**父图**执行（跳父图节点/改父图 state）时用（🟢）。典型场景：Handoffs 实现2 多 subgraph，子图 agent 要把控制权交回父图跳到另一个子图节点。
- 万物云口径：万物云 HITL 用 Command(resume)（第23步）；Handoffs 没用多 subgraph 实现，所以 graph=PARENT 没用（🔴推断）。

**4. return Command(goto="X") 和 add_conditional_edges("A",fn,{"x":"X"}) 都能跳 X，区别？**
- `return Command(goto="X")`：**节点内部运行时决定**跳哪，动态的，LLM/逻辑跑完才知道（🟢）
- `add_conditional_edges`：**图编译时定义**静态路由表，fn 返回 key "x" 映射到 "X"，预定义分支（🟢）
- 核心区别：Command 是**运行时动态**（agent 边跑边决定），conditional_edges 是**编译时静态**（提前画好分支图）（🟡）
- 何时用哪个：分支逻辑固定可枚举（if A then X else Y）用 conditional_edges；分支要 agent/逻辑运行时决定（LLM 看完上下文才知道转哪个 agent）用 Command goto（🟡）
- 后端类比（🟡）：conditional_edges = Spring 静态路由表（配置时定），Command goto = 代码运行时动态转发（运行时算）
- 万物云口径：意图分类节点后用 add_conditional_edges 静态路由到业务 agent（🟡）；Handoffs 场景用 Command goto 动态转话筒（🔴推断）。

**5. tool 函数能 return Command 吗？handoff tool 为什么 return Command 不返回字符串？**
- 能。LangGraph 支持 tool 函数 return Command，Command 作为该 tool 的执行结果作用于图（跳转/改 state/冒泡）（🟢）
- 为什么 return Command 不返回字符串：
  - 返回字符串 = 只是 ToolMessage 内容进上下文，控制权还在原 agent，没转走（🟡）
  - `return Command(update={current_agent: B})` = 改 state 切配置，下轮 B agent 接话，真正"转话筒"（🟢）
  - handoff 本质是"转控制权"，必须改图的状态（current_agent / update messages），光返回字符串转不了
- 后端类比（🟡）：tool 返回字符串 = 方法返回值（调用方继续）；tool return Command = 抛流程跳转信号（引擎接管转下一步）
- 关键：tool return Command 是 Handoffs 实现1（单 agent + middleware）的机制--handoff tool 改 current_agent state，middleware 下轮按 state 切 agent 配置（🟢）

**6. interrupt 和 Command 什么关系？"停完用 Command(resume) 接着走"怎么理解？resume 和 goto/update 能同时用吗？**
- interrupt 管"停"（图执行到 interrupt 暂停，等外部输入）；Command 管"走 + 停完接续"（🟡 总结口径）
- "停完用 Command(resume) 接着走"：图 interrupt 暂停后，外部用 `Command(resume=value)` 重新 invoke，value 作为 interrupt 的返回值传给图，图从暂停点接着执行（🟢）
- 关系：interrupt 是"暂停信号"，Command(resume=) 是"恢复信号"，配对用--interrupt 停下，resume 接着走（🟢）
- resume 和 goto/update 能同时用吗：
  - resume 是**新请求传入**的（invoke 时传 Command(resume=...)），不是节点 return 的（🟢，见用法5）
  - goto/update 是**节点 return** 的（节点执行完 return Command(goto/update)）（🟢）
  - 所以两者**不在同一个地方用**：resume 在 invoke 入口传，goto/update 在节点 return。一次恢复流程里可以既 resume（恢复）又让后续节点 return goto/update（继续跳），但同一个 Command 对象里 resume 和 goto/update 不混用（🟡）
- 万物云口径：万物云 HITL 用 interrupt_before 暂停 + Command(resume) 恢复（第23步），人工审核完传结果接着走（🟡/🔴推断）。
