# Agent 工程 Subgraph 全量总结（基础补课）

> subgraph 在 Handoffs 实现2、Custom workflow（node 第4种"整个 multi-agent 系统"）、状态检查/HITL 场景都出现，但之前没系统讲。这篇一次性讲透：subgraph 是啥、为什么需要、和包成 tool 的区别、父子图怎么交互。
>
> 看完这篇再回 Handoffs 实现2 / Custom workflow，就不会觉得"突然冒出来"。
>
> 标注：🟢 官方确认（agent_pattern_subagents / ma_handoffs）/ 🟡 后端类比 / 🔴 推断或待核

---

## 0. 先回答你的三个困惑（源头讲清，别再觉得突然冒出来）

> 你这次问的三句话，先逐句白话答，再看后面深入。这三句不解决，后面全卡。

### 困惑1：subgraph 是 LangGraph 的概念吗？

**是。** subgraph 是 LangGraph StateGraph 的能力，不是别的框架、不是新引擎。你在学 LangGraph 时遇到的"图套图"就是它，没跑出 LangGraph 范围（🟢）。

### 困惑2："不是就是 node + edge 吗？为啥还要 subgraph？"

**对，你还是用 node + edge。subgraph 不是替代 node/edge 的新东西，别被名字吓到。**

复习你已懂的：StateGraph = 用 `add_node` 加节点 + `add_edge` 连边拼出来的一张图。每个 node 平时是一个**函数**（跑完返回 state 更新）。

subgraph 做的事只有一件：**让某个 node 的内容从"一个函数"变成"一整张小图"**。
- 原来：node = 普通函数 `def node(state): return {...}`
- subgraph：node = 另一张编译好的 StateGraph（小图内部**还是 node + edge** 组成）

所以 subgraph = **"一个 node，内部套了张图"**。你没学新东西，还是 node + edge，只是某个 node 内部是张小图而不是单个函数。图套图，仅此（🟢）。

**那为啥还要这个能力？** 因为普通 node 是个函数，函数内部 LangGraph **看不见**（黑盒）。如果这个 node 内部是个复杂流程（比如一个带反思+检索的 agent），你想从外面看它跑到哪了、想中断它内部某一步--函数做不到。把 node 换成 subgraph（一张小图），LangGraph 就能看见小图内部、能中断小图内部某节点（白盒）。**subgraph 存在就是为了"让一个复杂节点内部可被外部看见和中断"**。这是第 3 节的核心。

后端类比（🟡）：你已经懂 Spring Controller 调 Service。subgraph = 这个 Service **内部不是几个方法，而是自己走了一套完整流程（又是一个小 Spring 流程）**。对 Controller 来说还是调一次 Service，但 Service 内部是个小世界。Activiti 里就是**子流程（sub-process）**：大流程一个节点是个子流程，子流程内部又有自己的节点和边。

### 困惑2 深挖：为什么 subgraph 能看见，普通函数 node 不能？（你抓的矛盾点）

你抓到的矛盾很准。问题出在我"图套图"没讲清"为什么图就能被看见"。先纠正一个关键误解：

**普通 node 内部不是图，是函数。** 别把"subgraph 内部是图"理解成"所有 node 内部都是图"。
- 普通 node：`def node(state): return {...}`——内部是**一个函数**，不是图
- subgraph node：这个 node 的内容是**一张编译过的图**（小图内部才是 node+edge）

这是**两种不同的 node**。subgraph 不是"给 node 外面包一层"，而是"**把 node 的内容从函数换成图**"。你问"subgraph 包住就能看到了？"——不是"包住"，是"node 的内容本身变成了引擎认识的图"。

那为什么"内容是图"就能被外部看见，"内容是函数"就不能？核心一句话：

**可见性来自"是不是 LangGraph 引擎在执行"。**

- **普通函数 node**：父图跑到这个 node，引擎做的是——**调用这个函数**，传 state 进去，等函数 return，拿 state 更新。函数内部怎么跑（for 循环？调 LLM 几次？），引擎**一无所知**，也不参与。函数是个**黑盒**，引擎只在函数返回时拿到结果。你想从外面看"这个函数跑到第几步了"、想"中断在函数内部某一行"——做不到，因为引擎根本不在函数内部，函数内部就是普通 Python 代码，引擎没有钩子。

- **subgraph node**：父图跑到这个 node，引擎做的是——**执行这张子图**。子图的每个节点、每条边都是**用 add_node/add_edge 注册到引擎的**，引擎**知道子图的完整结构**。执行子图时，子图的每个节点触发、每次 state 更新、每条边转移，**都经过引擎运行时**（写 checkpoint、走状态机）。所以引擎**全程在场**，能看见子图跑到哪个节点、state 是什么、能停在子图内部任意节点（因为"停"=引擎不往下走，而引擎控制着每一步）。

一句话：**函数 node 是"引擎委托给函数跑"（引擎不参与内部，干等返回）；subgraph 是"引擎自己跑子图的每一步"（引擎全程在场，所以全程可见可中断）。**

后端类比（🟡，你熟的 Spring/Activiti）：
- **函数 node** = Spring Controller 调 `service.process(data)`。process() 是个普通 Java 方法，内部怎么 for 循环、调什么，Spring 容器**不知道**（就是个方法调用）。你想从 Spring 容器层面看 process 内部跑到哪、中断 process 内部某行——做不到，process 内部不是 Spring 管理的流程，是普通 Java 代码。
- **subgraph** = Activiti 子流程。子流程的每个节点都**注册在 Activiti 引擎**（写 ACT_RU_TASK 表），引擎执行子流程时**每一步都过 Activiti 引擎**。所以引擎能查子流程跑到哪个节点（查表）、能 suspend 子流程某节点。因为子流程内部**也是引擎在跑**，不是黑盒方法调用。

所以"图套图能看见"的本质，不是"图"这个字有魔力，而是：**子图是引擎注册+执行的，引擎在子图内部每一步都在场；函数是引擎委托出去的，引擎在函数外面干等。引擎在场=可见可中断，引擎不在场=黑盒。** 这才是第 3 节"白盒 vs 黑盒"的底层原因。

---

### 困惑3："subagent 我可以理解，subgraph 和它啥区别？"

这两个是**不同层面**的东西，别混：

| | subagent（子智能体）| subgraph（子图）|
|---|---|---|
| 是什么 | 一个 agent（create_agent 产物，有自己的 prompt/tools/模型）| 一张图（编译后的 StateGraph，内部是 node+edge）|
| 层面 | **角色层面**："谁干活"（一个智能体）| **结构层面**："图怎么嵌套"（图套图）|
| 例子 | 销售agent、客服agent（一个个会干活的智能体）| 父图某节点内部套了张小图 |

**关系**（重点）：subagent 可以**装进 subgraph 这个壳**，也可以**不装**：
- subagent **作为 subgraph 节点**放进父图 → 白盒（父图能看到子 agent 内部状态，HITL 能停子 agent 内部）🟢
- subagent **包成 @tool** 放进父图 → 黑盒（父图看不到子 agent 内部，调用完拉倒）🟢

一句话记死：**subagent = 谁干活（智能体）；subgraph = 图怎么嵌套（结构形式）。subagent 是内容，subgraph 是装它的壳之一。** 你可以把 subagent 装进 subgraph 壳（白盒），也可以装进 tool 壳（黑盒）（🟢）。

所以不是"subagent vs subgraph 二选一"，而是"**subagent 这个智能体，用 subgraph 形式还是 tool 形式放进图**"。subagent 是要放的东西，subgraph 是放它的两种壳里更透明的那种。

### 一句话串起来
subgraph 是 LangGraph 的"图套图"能力（🟢），本质还是 node+edge，只是某个 node 内部是张小图（🟢）；它存在的价值是让复杂节点内部可被外部看见和中断（白盒，🟢）；subagent 是智能体（角色），可以装进 subgraph 壳（白盒）或 tool 壳（黑盒）放进图（🟢）。

这三句懂了，再看第 1 节往后深入。

---

## 1. Subgraph 是什么（一句话先立住）

**Subgraph = 一个编译后的 StateGraph，作为另一个 StateGraph 的节点。**

通俗说：你有一张大图（父图），其中一个节点不是普通函数，而是**另一张完整的小图（子图）**。跑父图跑到这个节点时，实际是跑整张子图，子图跑完返回，父图继续。

后端类比（🟡）：
- subgraph = **Activiti 子流程（sub-process）**：一个大流程里嵌一个完整子流程，子流程有自己的节点/边/变量，跑完回流父流程
- 也像 **Spring 里一个 Controller 调一个 Service，Service 内部又是一套完整业务流程**--对 Controller 是一次调用，内部是个小世界

**关键**：subgraph 不是新引擎，还是 StateGraph，只是"图套图"。

---

## 2. 为什么之前没讲、现在突然冒出来

subgraph 在多处用到但没单讲，是我的问题（和 Command 一样）。它出现在：
- **Handoffs 实现2**（多个 agent 各是 subgraph 节点，handoff 用 Command.PARENT 跳父图）
- **Custom workflow 的 node 第4种**（node 可以是"整个 multi-agent 系统"= subgraph）
- **状态检查/HITL 场景**（要读子图内状态、interrupt 要停子图内时，必须用 subgraph 不能包 tool）

这篇补上。以后遇到 subgraph 都引用这里。

---

## 3. 两种把 agent 放进图的方式（核心区别，先搞懂这个）

同一个 agent，有两种方式放进 StateGraph，**可见性完全不同**：

| | 方式 A：包成 @tool | 方式 B：作为 subgraph 节点 |
|---|---|---|
| 怎么放 | `@tool def call_agent(query): return agent.invoke(...)`，tool 放进主 agent tools | `graph.add_node("agent", agent_compiled)`，agent 编译后当节点 |
| LangGraph 可见性 | **黑盒**（🟢）| **白盒**（🟢）|
| get_state 看子图内 | ❌ 看不到 | ✅ 能看到（get_state with subgraphs 返回子图 state）|
| interrupt 停子图内 | ❌ 停不了（子图是 tool 调用，黑盒）| ✅ 能停子图内某个节点 |
| 适合 | 普通调度，不关心子图内部 | 需要读嵌套状态 / HITL 停子图内 / 复用复杂图 |

官方原话（🟢 agent_pattern_subagents）：
> "Because subagents are called inside tool functions, LangGraph cannot statically discover them. This means get_state with subgraphs will not return subagent state. If you need to read nested graph state (e.g., during an interrupt), invoke the subagent from a node function in a custom graph instead."

翻译：subagent 包成 tool 时，LangGraph 静态发现不了它（黑盒），get_state with subgraphs 不返回 subagent state。**需要读嵌套图状态时（比如 interrupt 期间），把 subagent 从 custom graph 的 node function 调用（= 作为 subgraph 节点），而不是包成 tool。**

**这就是 subgraph 存在的核心价值：可见性 + 状态检查 + HITL 能停子图内。** 包成 tool 做不到这三点。

---

## 4. 父子图怎么交互

### 4.1 父子 state（🔴 待核 API 细节）
- 父图和子图各有自己的 State schema
- 通用做法（🟡，API 细节🔴待核）：父子 schema 有相同 key 时，子图能读写这些 key（state 共享）；不同 key 时子图只管自己的
- Deep Agents 的 CompiledSubAgent 要求子图有 `messages` 这个 state key（🟢）--说明父子图通过 messages 等约定 key 通信
- 🔴 具体父子 state 映射机制（自动共享 vs 手动映射）我没核实官方 API，用到时查

### 4.2 Command(graph=Command.PARENT)：子图命令冒泡父图（🟢）
子图节点里默认 return Command 作用于**子图内部**。要影响**父图**（跳父图节点 / 改父图 state），加 `graph=Command.PARENT` 把命令冒泡给父图。

```python
# 子图的 handoff tool 里
return Command(
    goto="sales_agent",          # 跳父图的 sales_agent 节点（不是子图内部）
    update={"active_agent": "sales_agent"},
    graph=Command.PARENT          # 冒泡到父图
)
```
（Command 全貌看《Agent工程Command全量总结》用法4）

### 4.3 可见性（🟢 上面第3节）
父图能 get_state 看子图内状态、interrupt 能停子图内节点--这是 subgraph 相对 tool 的核心优势。

---

## 5. 何时用 subgraph（决策）

用 subgraph（不用包 tool）当：
1. **要读嵌套图状态**（如 HITL interrupt 期间要看子图跑到哪了）--🟢 官方首要场景
2. **HITL 要停在子图内部某个节点**（包 tool 停不了，黑盒）
3. **复用复杂图**（某 agent 本身是带反思/检索的多节点图，编译后当 subgraph 节点复用）--🟢 Handoffs 实现2 的场景
4. **团队分工**（不同团队各维护一个子图，编译后拼进父图）

不要求这些时，**包成 tool 更简单**（Subagents 模式）。

---

## 6. 和 Handoffs 实现2 的关系（解决你这次的困惑）

Handoffs 实现2 "多个 agent subgraph" 就是：
- 每个 agent 是父图里的一个**节点**，这个节点本身是一张**子图**（编译后的 agent）
- 转话筒 = handoff tool 用 `Command(goto, graph=Command.PARENT)` 从当前子图跳到父图的另一个 agent 节点
- 因为是 subgraph（白盒），父图能看到各 agent 节点状态，handoff 能精确跳转

对比实现1（单 agent + middleware）：实现1 只有 1 个 agent，靠 state 切配置，**没有 subgraph**，所以不用 Command.PARENT。这就是为什么实现1 简单、实现2 复杂（要管 subgraph + PARENT）。

---

## 7. 常见疑问预判

**Q1：subgraph 和 Subagents 里的"子 agent"啥关系？**
子 agent 是个 agent（create_agent 产物）。把它放进图有两种方式：包成 tool（Subagents 模式，黑盒）或作为 subgraph 节点（白盒）。subgraph 是"子 agent 作为节点"的实现形式。（🟢 agent_pattern_subagents 形式C）

**Q2：subgraph 一定要是 agent 吗？**
不一定。subgraph 是"编译后的 StateGraph 当节点"，里面可以是任意图（纯函数节点 / LLM 节点 / agent 节点混合）。agent 只是最常见的 subgraph 内容。（🟡）

**Q3：为什么包 tool 不行要用 subgraph？**
包 tool 时 LangGraph 静态发现不了子图（黑盒），get_state 看不到子图内状态、interrupt 停不到子图内。需要这些就要用 subgraph（白盒）。（🟢）

**Q4：subgraph 和 Custom workflow 的 node 第4种"整个 multi-agent 系统"啥关系？**
同一个东西。Custom workflow 说 node 可以是"整个 multi-agent 系统（作为单个节点嵌入）"--这个"multi-agent 系统"就是一张 subgraph。（🟢 ma_custom）

**Q5：万物云用 subgraph 吗？**
🔴 推断：万物云 multi-agent = Custom workflow（StateGraph），agent 作为普通节点，节点间条件边路由，**没用 handoffs 的 subgraph + Command.PARENT 形式**。但万物云的"节点可以是子图"这个能力是否用过🔴待核。面试口径："multi-agent 是 StateGraph 自定义工作流，agent 作为图节点条件边路由，没用 handoffs 那套 subgraph + PARENT。"

---

## 8. 后端类比表（🟡）

| LangGraph subgraph | 后端类比 |
|---|---|
| subgraph（编译图当节点）| Activiti 子流程（sub-process）/嵌套流程 |
| 父图调子图节点 | 父流程调子流程 |
| Command(graph=Command.PARENT) | 子流程抛事件给父流程引擎（signal 冒泡）|
| 包 tool（黑盒）| 调一个不透明的外部 service（内部细节看不到）|
| subgraph（白盒）| 调一个同引擎的子流程（状态可见、可中断）|
| get_state with subgraphs | 查子流程的运行时变量（ACT_RU_VARIABLE 嵌套）|

---

## 9. 检查题

1. subgraph 是什么？和普通 node 有什么区别？
2. 把 agent 放进图有两种方式（包 tool vs subgraph 节点），可见性有什么不同？官方原话怎么说？
3. 为什么包 tool 做不到的事，subgraph 能做到？举一个场景（HITL）。
4. Command(graph=Command.PARENT) 是干啥的？什么时候用？
5. Handoffs 实现2 为什么用 subgraph？实现1 为什么不用？
6. 万物云用 subgraph 吗？（🔴 推断怎么诚实答）
