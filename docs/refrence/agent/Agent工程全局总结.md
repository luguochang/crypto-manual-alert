# Agent 工程全局总结

> 这是已完成 7 个模块的全局视图，配合《Agent工程逐步辅导记录.md》用，便于面试快速复盘。
> 辅导记录是「一步一个概念」的小步讲法；这个文档是「把 7 个模块拼成一张图」的全局视角。
> 用法：面试前先看这张主流程图理清骨架，再按模块速查表定位到具体步数复习。

---

## 【主流程图】对话生命周期主流程图

一个用户对话从进入到结束，依次经过 10 个环节。这张图就是面试讲一遍的骨架。

```
========================================================================
          一次用户对话的完整生命周期 (面试讲一遍的骨架)
========================================================================

[用户输入] HumanMessage ("查订单 ORD-001 并判断是否退款")
    |
    |  thread_id = 会话钥匙 (= JSESSIONID)
    v
+======================================================================+
| 1. Agent 受控循环启动  (while true)                                   |
|    模型运行时决定: 调不调工具 / 调哪个 / 何时停                       |
|    (区别普通 Java while: 不是写死代码路径, 是模型实时选路)            |
+======================================================================+
    |
    v
+======================================================================+
| 2. 消息序列构建                                                       |
|    messages = [SystemMessage (全局配置 = web.xml)                    |
|               + ...历史 messages (只增不减 = 审计日志)               |
|               + HumanMessage (当前请求 = @RequestBody)]              |
|    另含每轮重发: 工具定义 JSON + 检索结果(RAG)                       |
|    (LLM 无状态 = stateless REST, 工具定义每轮重发常被漏算)           |
+======================================================================+
    |
    v
+======================================================================+
| 3. 中间件洋葱  (注册顺序 = 外到内, = Spring AOP + Filter 链)          |
|                                                                       |
|  before_agent (整个会话 1 次):                                       |
|    Auth -- 验 token + 加载用户, 没权限直接 raise 不进循环            |
|      |                                                                |
|      |  ============ 每轮循环 (调模型 -> 有 tool_calls? -> 调工具 -> 回喂) ============
|      |                                                                |
|      |  [6. 上下文管理] 在 before_model 钩子内执行:                   |
|      |    模型每轮看 5 部分:                                          |
|      |      System + 历史 messages + 工具定义 + 检索结果 + 长期记忆   |
|      |    超 token 阈值 -> 三解法组合:                               |
|      |      裁剪 (删旧留近 N = LRU 淘汰)                             |
|      |      摘要 (小模型压成 1 段 = 日志滚动归档)                    |
|      |      外移 (存 Store 留指针 = 冷热分离)                        |
|      |    优先级: System 永远留 > 最近 N 轮 > 工具结果 > 旧寒暄      |
|      |                                                                |
|      |  [7. 记忆系统] 三路正交同时运作:                              |
|      |    短期: messages(进程内存) + checkpointer(存快照)            |
|      |         = HttpSession (内存 + session 持久化到 Redis)         |
|      |    长期: store.get(uid) -> 注入 SystemMessage                 |
|      |         = 用户画像表按 userId 查, 不全量塞防 lost-in-middle   |
|      |    任务: State 字段 (intent/risk_level) -> 条件边路由         |
|      |         = Activiti 流程变量, 任务结束清                       |
|      |                                                                |
|      |  wrap_model_call (= @Around, handler 在手可重试)              |
|      |    |                                                           |
|      |    v                                                           |
|      |  4. 模型决策: model.invoke(messages) -> AIMessage             |
|      |    有 tool_calls?                                              |
|      |    /              \                                            |
|      |  否(结束信号)      是(继续循环)                                 |
|      |    |                |                                          |
|      |    |                v                                          |
|      |    |     5. 工具调用 (wrap_tool_call, 每次工具 1 次)           |
|      |    |       args_schema 校验 (= @Valid + Pydantic DTO)         |
|      |    |         |-- 失败: ValidationError -> 错误信息回模型      |
|      |    |         |-- 通过: 执行工具                                |
|      |    |                   |                                       |
|      |    |                高风险?                                    |
|      |    |                /     \                                    |
|      |    |              是       否                                  |
|      |    |               |        |                                  |
|      |    |               v        |                                  |
|      |    |     8. HITL 暂停      |                                  |
|      |    |        interrupt       |                                  |
|      |    |        人工确认        |                                  |
|      |    |        /    \          |                                  |
|      |    |      同意    拒绝       |                                  |
|      |    |        |       \       |                                  |
|      |    |        v        v      v                                  |
|      |    |     ToolMessage (tool_call_id 配对)                       |
|      |    |        |                                                  |
|      |    |        v                                                  |
|      |    |     回循环顶 (模型重读全部历史) --------------------------+
|      |    |                                                           |
|      |    v                                                           |
|      |   after_model: Guardrail 脱敏(身份证/银行卡) + 安全检查       |
|      |                                                                |
|      |  ============================ 每轮循环结束 ===================|
|      |                                                                |
|      v                                                                |
|  after_agent (整个会话 1 次):                                        |
|    Audit -- 记 trace_id/用户/意图/工具调用/耗时/最终回答             |
+======================================================================+
    |
    v  (最终某轮模型无 tool_calls)
+======================================================================+
| 9. 流式输出  (stream / astream_events / SSE 全链路)                  |
|    边生成边推前端, 不等全部生成完                                     |
+======================================================================+
    |
    v
+======================================================================+
| 10. 终止  (4 种条件, 后 3 种是兜底)                                   |
|     1 模型自停 (无 tool_calls, 默认最常见)                            |
|     2 recursion_limit=25 (框架兜底, 防停不下来)                       |
|     3 条件边显式跳 END (你的代码)                                     |
|     4 interrupt / 未捕获异常 (HITL)                                   |
|                                                                       |
|     死循环三层防护 (各管一段, 非冗余):                                |
|       第一层 recursion_limit=25  防"停不下来"  框架数次数兜底         |
|       第二层 证据增量检测       防"原地打转"  结果不变提前止损         |
|       第三层 检索最多 3 跳      防"无限深挖"  = maxDepth=3 硬截断      |
+======================================================================+
    |
    v
[最终回答返回用户]
```

**面试讲法**：用户输入进来 -> Agent 是个 while(true) 受控循环，模型运行时决定下一步（不是写死代码）-> 每轮先把消息序列构建好（System + 历史 + 当前 Human，加工具定义）-> 经过中间件洋葱（before_agent 鉴权，before_model 做上下文管理 + 记忆注入）-> 模型决策调不调工具 -> 要调就过 args_schema 校验执行工具 -> 高风险工具 HITL 暂停等人工确认 -> 工具结果回喂循环 -> 最终模型不调工具了 -> 流式输出给前端 -> 终止（4 种条件 + 3 层防死循环）。

---

## 【7 个模块】

### 第一部分：Agent 本质 = while(true) 受控循环（第1-3步）

#### 核心总结

Agent 的本质就一句话：一个 while(true) 受控循环。每轮把全部历史 messages 喂给模型，返回 AIMessage--带 tool_calls 就执行工具、把结果作为 ToolMessage 塞回去再回循环顶；不带就输出文本结束。和 Java while 最本质的区别：普通循环每一步做什么、何时停都是你写死代码决定的；Agent 循环里调不调工具、调哪个、要不要停，都是模型在运行时决定的。这就是 ReAct：推理->行动->观察循环。messages 只增不减，每轮模型看全部历史才能接着上次继续，这也是上下文膨胀的根源。终止共四种：模型自停(默认)、recursion_limit 兜底、条件边跳END、interrupt/异常。死循环要三层防护各管一段：recursion_limit=25 防"停不下来"、证据增量检测防"原地打转"(结果不变)、检索最多3跳防"无限深挖"(结果在变但跑偏，等于给懒加载设 maxDepth)。

#### 流程图

```
          +------------------------------------------+
          |   messages (只增不减 = 不断追加的请求日志)  |
          |  [0]System  [1]Human  [2]AI  [3]Tool ...  |
          +------------------------------------------+
                               |
                               v
   =======================================================
   |  while(true)  受控循环 (模型运行时决定, 非写死代码)    |
   =======================================================
                               |
                               v
                 +------------------------------+
                 |  model.invoke(messages)      | <-- 每轮看"全部"历史
                 |  -> AIMessage                |     (少看一条决策就错)
                 +------------------------------+
                               |
                               v
                 +------------------------------+
                 |  AIMessage.tool_calls 非空?  |
                 +------------------------------+
                    |                        |
                   否|                       是|  <-- ReAct: Action
                    |                        |
            +-------+--------+      +--------+----------------+
            | 终止条件1       |      | for call in tool_calls: |
            | 模型自停,返回文本|      |   r = run_tool(call)     | <-- 并发执行
            +-------+--------+      |   append ToolMessage(    |
                    |               |     r, tool_call_id=call.id)|<-- id必须关联
                    v               +--------+----------------+
              返回给用户                      |
                                              v
                                   回 while 顶部 <----+
                                  (下一轮看全部历史)  |
                                                     |
   =============== 4 种终止条件 (后3种是兜底) ===============
   1 模型返回纯文本无 tool_calls   谁定: 模型自己  (默认,最常见)
   2 达到 recursion_limit 上限      谁定: 框架兜底  (防死循环)
   3 条件边显式路由到 END           谁定: 你的代码
   4 interrupt / 未捕获异常         谁定: 人工/异常 (HITL)

   =============== 死循环三层防护 (各管一段, 非冗余) ===============
   第一层  recursion_limit=25   防 "停不下来"   框架数次数, 最后兜底
   第二层  证据增量检测         防 "原地打转"   结果不变 -> 第2-3轮提前止损
   第三层  多步检索最多3跳      防 "无限深挖"   结果在变但跑偏 = maxDepth=3
           (第二层抓不住第三层: current==last 永不成立)
```

#### 各部分作用

- **while(true) 受控循环**：Agent 的骨架--模型在运行时决定每一步调不调工具/调哪个/何时停，区别于 Java 写死代码路径的普通 while
- **model.invoke(messages)**：每轮把全部历史 messages 喂给模型，返回 AIMessage（可能带 tool_calls），是 ReAct 的 Reasoning 环节
- **tool_calls 判断分叉**：有 tool_calls 走 Action（执行工具回循环顶），无则输出文本结束--这是循环唯一的正常出口
- **ToolMessage + tool_call_id**：工具结果回传（Observation），id 必须与 AIMessage 里 tool_call 的 id 一一对应，否则多并发工具调用分不清哪个结果对应哪个请求
- **messages 列表**：只增不减的对话日志（add_messages reducer 是追加非覆盖），每轮模型看全部历史才能正确决策，这是上下文膨胀的根源
- **4 种终止条件**：模型自停(默认) / recursion_limit(框架兜底) / 条件边跳END(你的代码) / interrupt或未捕获异常(HITL)，后三种正因为模型可能不停才需要
- **第一层 recursion_limit=25**：框架自带兜底，防"停不下来"，25 是复杂度与成本的平衡点，触发要降级而非报错
- **第二层 证据增量检测**：业务层防"原地打转"，对比连续两次工具结果是否相同，相同则注入换思路提示，重复2次强制结束，能在第2-3轮提前止损
- **第三层 检索最多3跳**：防"无限深挖"，结果每次都在变所以第二层抓不住，用次数硬截断=给懒加载设 maxDepth=3，到顶用已有信息综合回答

#### 后端类比

while(true) 受控循环不是 Spring 某个组件，而是把「在运行时决定调用哪个 Service」的调度权交给了模型--你不再写死 if/else 调 OrderService 还是 RefundService，而是模型读 messages 后自己选路走，像 Activiti 工作流下一步走哪个节点本由流程定义决定，但 Agent 这里「流程定义」是模型实时生成的。messages 列表类比不断追加、只增不减的请求日志/审计日志：普通 Java 方法栈返回栈帧就弹掉，这里每一轮的对话和工具结果都留着，下一轮整体重读一遍。死循环三层防护完全类比 IoT 后端防无限重试的同一思路：次数限制(recursion_limit) + 变化检测(证据增量) + 深度上限(3跳)。第三层特别像 JPA 懒加载引发的 N+1 级联、或图遍历/递归 CTE 不设 maxDepth 会拖出半个库--3 跳限制就是给检索加 fetchDepth/maxDepth=3。注意：实际代码里不是字面 while True，LangGraph 用图的条件边实现（agent 节点->有 tool_calls 走 tools 节点->回 agent；无则走 END），循环由图引擎驱动，while(true) 是教学用的心智模型。

---

### 第二部分：框架层级（LangGraph / create_agent / create_deep_agent 三层 + 万物云为何手动建图）

#### 核心总结

框架三层从底到顶：LangGraph StateGraph（编排骨架，~Spring Framework）-> create_agent（搭好标准 ReAct 图开箱即用，~Spring Boot）-> create_deep_agent（封装规划/文件系统/沙箱，~Spring Cloud）。底层都一样，区别只是封装层次。权衡：越高开发越快但灵活性低，越低越灵活但代码量大。标准 ReAct 用 create_agent；要意图分类+风控分流+计划+人工确认+自定义 State 这种非标准拓扑，退回 LangGraph 手动建图拿拓扑控制权。万物云用底层手动 StateGraph 两个原因：一是时间点，项目启动时 create_agent 还没发布或不成熟；二是硬原因，万物云图是「分类->风控->计划->执行循环->综合」带分支循环的非标准拓扑，固定 ReAct 模板表达不了。

#### 流程图

```
=== 三层封装关系（从底到顶，类比 Spring）===

  顶层  +-------------------------------------------------------+
        | create_deep_agent : 规划/文件系统/子代理/沙箱/权限    |  ~ Spring Cloud
        +-------------------------------------------------------+
                            | 再包装（封装完整能力）
                            v
  中层  +-------------------------------------------------------+
        | create_agent : 标准ReAct图，开箱即用                  |  ~ Spring Boot
        +-------------------------------------------------------+
                            | 内部用 StateGraph 搭标准 ReAct
                            v
  底层  +-------------------------------------------------------+
        | LangGraph StateGraph : 图/State/Node/Edge/路由/循环  |  ~ Spring Framework
        +-------------------------------------------------------+

=== create_agent 内部帮你搭的标准 ReAct 循环（受控循环）===

        +--------------------+
        | model.invoke(msg)  | <-------+
        +--------------------+         |
                 |                    |
          tool_calls 非空?             |
           /            \             |
         是             否            |
          |              +----------> END  (返回文本给用户)
   并行执行 tool(s)       |
          |              |
   ToolMessage 回喂 ------+

=== 万物云的非标准拓扑（create_agent 固定模板表达不了 -> 手动建图）===

  意图分类 -> 风控分流 -> 计划生成 -> 执行(ReAct循环) -> 综合 -> END
                              ^                |
                              +-- 未完成 ------+
                  | 高风险
            人工确认(interrupt)

  [区别] 标准ReAct: 模型<->工具 单循环
         万物云   : 分类(循环前)+风控(路由层)+Plan-Execute+综合节点+分支/循环
```

#### 各部分作用

- **LangGraph StateGraph（底层）**：图/State/Node/Edge/条件路由/循环/interrupt/持久化，底层编排骨架，类比 Spring Framework 手动配 Bean
- **create_agent（中层）**：在 StateGraph 之上组装好标准 ReAct 图（模型+工具+循环），开箱即用，类比 Spring Boot 自动配置；LangChain 1.0+ 才有（前身 create_react_agent）
- **create_deep_agent（顶层）**：再封装规划/文件系统/子代理/沙箱/权限等完整能力，类比 Spring Cloud；注意它更偏「能力/模式层」，是否为单一稳定官方 API 需以当前 langgraph 包为准
- **受控循环/ReAct**：create_agent 内部搭的就是这个--调模型->看 tool_calls 是否非空->执行工具->ToolMessage 回喂->再调模型，直到无 tool_calls 终止；下一步做什么由模型运行时决定，不是写死的代码路径
- **核心权衡**：封装越高=开发越快+灵活性低；越低=越灵活+代码量大易出错。标准 ReAct 用高层省事，定制拓扑退回底层拿控制权
- **万物云手动建图·硬原因**：图是「分类->风控->计划->执行循环->综合」带分支(风控分两路)和循环(未完成回执行)的非标准拓扑，create_agent 的固定 ReAct 模板表达不了；本质是 create_agent 产出「一个 agent」，万物云要的是「多节点编排成一条流程」
- **万物云手动建图·时间原因**：项目启动时 create_agent（LangChain 1.0+ 才有）还没发布或不成熟，客观上没法拿来生产用，面试先说这个历史原因

#### 后端类比

三层就是 Spring 三层：LangGraph StateGraph ≈ Spring Framework（手动配 Bean/ApplicationContext，拿全套控制权）；create_agent ≈ Spring Boot（自动配置几行起一个应用，但改不了内部装配）；create_deep_agent ≈ Spring Cloud（全家桶，规划/沙箱/子代理都现成）。万物云的非标准拓扑更像 Activiti 工作流：线性主链（分类->风控->计划->执行->综合）像责任链，但责任链是纯线性「处理或传递」，万物云还有条件分支（风控分两路）和循环（执行未完成回执行），责任链表达不了--准确说是「责任链的线性骨架 + 状态机/工作流的分支循环」，整体接近 Activiti。Spring Boot 自动配置够写 CRUD，但要做有定制生命周期的流程引擎，自动配置装配不出你要的结构，就退回 Spring Framework 手动配 Bean 和生命周期--万物云要的就是定制拓扑，所以手动建图。

---

### 第三部分：Middleware（Agent 的 AOP）

#### 核心总结

Middleware 就是 Agent 的 AOP：不动 while 受控循环，把鉴权/裁剪/重试/工具权限/脱敏/审计这些横切关注点像洋葱套在循环外，跟 Spring HandlerInterceptor、Servlet Filter 链一个东西。六个钩子分三档触发：before_agent/after_agent 整个会话跑一次；before_model/after_model/wrap_model_call 每轮调模型跑；wrap_tool_call 每次调工具跑。最关键区分是 wrap_* vs before_*：before_* 像 @Before，框架自动调一次模型你管不了次数；wrap_* 像 @Around，handler 在你手里，你决定调不调、调几次（重试）、改参数改结果，所以重试必须用 wrap_model_call。生产坑：工具抛异常别上甩，catch 住转错误信息返回给模型，让它自己换工具或告知用户，别让 agent 循环崩。

#### 流程图

```
注册: create_agent(middleware=[Auth, Context, Retry, ToolGuard, Guardrail, Audit])
  洋葱嵌套(注册顺序=外到内): A进 -> B进 -> C进 -> 核心 -> C出 -> B出 -> A出
        |
        v
+-------------------------------------------------------------------+
| === before_agent (整个会话 1 次) ===  Auth: 验token+加载用户偏好     |
|        没权限直接 raise, 不进循环                                     |
+-------------------------------------------------------------------+
        |
        v
+-------------------------------------------------------------------+
|  while 受控循环 (调模型 -> 有tool_calls? -> 调工具 -> 回喂 -> 再调)    |
|                                                                     |
|  before_model  (每轮1次)  Context: 注入时间/项目 + 超20条裁剪保留15条  |
|        |                                                            |
|        v                                                            |
|  wrap_model_call (每轮包住)  Retry: for attempt: await handler(req)  |
|     handler = pjp.proceed()  <-- @Around, 调用权在你手               |
|        |                                                            |
|        v                                                            |
|     [模型 ModelRequest -> ModelResponse]                             |
|        |                                                            |
|  after_model   (每轮1次)  Guardrail: 输出脱敏(身份证/银行卡)+安全检查   |
|        |                                                            |
|     有 tool_calls?                                                  |
|        |--有--> wrap_tool_call (每次工具1次)                          |
|        |          ToolGuard:                                        |
|        |            1.权限检查(非admin禁调删除工具) fail-fast         |
|        |            2.审计开始日志                                   |
|        |            3.result = await handler(request)  真正调工具     |
|        |            4.catch异常 -> 返回错误信息字符串(不让循环崩)      |
|        |            5.审计结果日志                                   |
|        |          |                                                 |
|        |          v                                                 |
|        |       ToolMessage 回喂模型                                  |
|        |--无--> 跳出 while                                           |
+-------------------------------------------------------------------+
        |
        v
+-------------------------------------------------------------------+
| === after_agent (整个会话 1 次) ===  Audit: 记trace_id/用户/意图/     |
|     调了哪些工具/耗时/最终回答                                        |
+-------------------------------------------------------------------+
        |
        v
     最终回答返回用户

关键区分:
  before_model   = @Before  框架自动调一次模型, 你管不了"调几次" -> 做不了重试
  wrap_model_call= @Around  handler在你手里, for里proceed几次就重试几次
  before_* 能做 : 改参数(before_model)/有限改结果(after_model)
  wrap_*  能做  : 调不调(缓存短路)/调几次(重试)/改参数/改结果 -- 四件事全包
```

#### 各部分作用

- **before_agent / after_agent**：整个 agent 会话级钩子，进门鉴权、出门审计，只跑一次（万物云 Auth、Audit）
- **before_model / after_model**：每轮调模型前后触发，before 改 ModelRequest（注入上下文/裁剪），after 改 ModelResponse（脱敏/安全检查）
- **wrap_model_call**：包住单次模型调用，等价 @Around，handler 在手可重试/缓存短路/改参数改结果（万物云 Retry）
- **wrap_tool_call**：包住单次工具调用，proceed 前权限检查、proceed 后审计、异常转错误信息（万物云 ToolGuard）
- **AgentMiddleware 基类**：继承它重写需要的钩子，类比 Spring 实现 HandlerInterceptor 重写 preHandle/postHandle
- **create_agent(middleware=[...])**：注册入口，注册顺序即洋葱外到内，最外层（如 Auth）放第一个最先挡最后收尾
- **ToolGuardMiddleware 完整示例**：五段生产写法--权限/审计开始/proceed 调工具/异常转换/审计结果，工具失败返回错误信息而非抛异常

#### 后端类比

Spring AOP + HandlerInterceptor 链 + Servlet Filter 链三合一。洋葱嵌套 = Filter 链 doFilter 一层层穿过去再一层层出来，注册顺序 [A,B,C] 即外到内；before_*/after_* = HandlerInterceptor 的 preHandle/postHandle；wrap_* = @Around 带 ProceedingJoinPoint，handler 就是 pjp.proceed()，不 proceed 目标方法不执行、写在 for 里就重试、proceed 前后可改参数改返回值。万物云六个 middleware 等于给 Agent 循环挂六个拦截器：Auth=SecurityFilter 进门验身份；Context=preHandle 注公共参数；Retry=@Retryable 或 @Around 包 RPC 加重试；ToolGuard=@Around 包 DAO 做权限+审计+异常转换；Guardrail=@AfterReturning 改返回值脱敏；Audit=@After 记访问日志。生产坑同 Java：工具抛异常别直接甩上去 = DAO 异常别直接甩给 Controller，转成调用方能处理的错误信息返回。

---

### 第四部分：消息模型（四类消息 + tool_call_id 关联 + @tool 装饰器原理）

#### 核心总结

消息模型是 Agent 的数据载体。四类消息：SystemMessage=全局配置(web.xml)、HumanMessage=用户请求(@RequestBody)、AIMessage=模型输出(Service返回值，带tool_calls就是要调子服务)、ToolMessage=工具结果(DAO返回值)。规律：AIMessage+ToolMessage成对出现，最后一条无tool_calls的AIMessage=循环结束信号(看的是tool_calls有没有，不是看有没有ToolMessage，那是果不是因)。一条AIMessage可并发多个tool_calls各带id，对应ToolMessage的tool_call_id必须匹配--这就是MQ的correlationId，不配对模型就张冠李戴给错答案。工具用@tool定义，等于@Component+@RequestMapping+Swagger三合一，但关键认知是：Python装饰器是import时当场执行转换返回BaseTool对象，不像Java注解只贴标签等容器启动扫描。写法像@Around，但@Around靠运行时代理织入，装饰器自己就是织入动作。

#### 流程图

```
[消息序列生长：一次完整 Agent 执行]

 SystemMessage("你是客服助手...")   <-- 开发者写,全局唯一 (=web.xml)
         |
 HumanMessage("查订单 ORD-001")     <-- 用户输入 (=@RequestBody)
         |
         v
 +---> 调模型
 |
 |   AIMessage(content="我先查一下",
 |             tool_calls=[                    <-- 有 tool_calls => 继续循环
 |               {name:search_order,   id:call_a},
 |               {name:query_logistics,id:call_b}  ])   <-- 可并发多个
 |         |
 |         |  框架按 id 并行执行工具
 |         v
 |   ToolMessage("已发货",       tool_call_id=call_a) --配对--> search_order
 |   ToolMessage("到转运中心",   tool_call_id=call_b) --配对--> query_logistics
 |         |
 +----<----+  (回到循环顶部, 再调模型)
 |
 |   AIMessage("已发货不能退款")   <-- 无 tool_calls => 循环结束
         |
         v
       [END]   最终回答给用户


[@tool 装饰器：函数 -> 工具 的转换]

   @tool                            等价于(语法糖解开)
   def search_order(order_id:str)->str:    search_order = tool(search_order)
       """查订单状态"""                            |
                                                  v
                                     返回 BaseTool 实例 (非原函数!)
                                            |
                   +------------------------+------------------------+
                   |             |                    |              |
                 工具名        描述               参数 schema       原函数
              (=路径)      (=API文档)          (=参数校验)       (=真正逻辑)
                 |             |                    |
           @RequestMapping  @ApiOperation         @Valid
                   \             /                    /
                    \           /                    /
                     @Component (注册为框架管理的工具)

  对比机制：
  Java @Component  = 被动标记 -----> [等Spring容器启动扫描] -----> 注册Bean
  Python @tool     = 主动调用 -----> [import 时当场执行] -------> 已是BaseTool
```

#### 各部分作用

- **SystemMessage**：系统级指令/角色约束/规则，全局一般一条，永远在最前，=web.xml/application.yml 全局配置
- **HumanMessage**：用户每轮输入，=@RequestBody 接收的前端请求
- **AIMessage**：模型输出，带 tool_calls=要调工具(继续循环)，不带 tool_calls=最终回答(循环结束信号)，=Service 返回的 Result<T>(可能夹带'下一步调谁')
- **ToolMessage**：工具执行结果回给模型，=DAO/子服务返回给 Service 的数据，必须有 tool_call_id
- **tool_call_id**：ToolMessage 与 AIMessage 里 tool_call 的配对 key，=MQ 的 correlationId/支付回调订单号，并发多工具时防张冠李戴或重复调用
- **tool_calls 并发**：一条 AIMessage 可含多个 tool_calls，框架并行执行后回多条 ToolMessage，是性能优化(万物云查多设备状态)
- **循环结束判断**：看最后一条 AIMessage 有没有 tool_calls，有=继续，没有=结束(不是看有没有 ToolMessage，那是果不是因)
- **@tool 装饰器**：把普通函数转成 BaseTool 实例，=Spring 的 @Component+@RequestMapping+@ApiOperation 三合一
- **@tool 做的四件事**：包装成 BaseTool + 从签名提取参数 + 从 docstring 提取描述 + 生成 JSON Schema 给模型看
- **Python 装饰器本质**：高阶函数(接收函数返回新对象)，import 时当场执行转换，不等容器扫描；Java 注解是被动标记靠 Spring 运行时织入
- **装饰器 vs @Around**：写法像(前+proceed+后 结构相同)，机制不同--@Around 靠运行时代理织入，装饰器自己就是织入动作

#### 后端类比

整条消息序列=一次HTTP请求处理链。SystemMessage=web.xml/application.yml全局配置(全局一条)；HumanMessage=@RequestBody接收的前端请求；AIMessage=Service返回的Result<T>，带tool_calls相当于"返回值里夹带'下一步调子服务X'的指令"，不带tool_calls=Service返回最终结果给前端、链路结束；ToolMessage=子服务/DAO返回值喂回Service。AIMessage+ToolMessage成对=Service先请求子服务才有返回(因果关系，没请求就没返回)。tool_call_id=CompletableFuture回调关联/RabbitMQ的correlationId/支付回调的订单号--并发发N个异步请求，响应靠id一一配对，漏了就张冠李戴。@tool=Spring的@Component(注册Bean)+@RequestMapping(定义访问路径=工具名)+@ApiOperation(Swagger生成API文档给模型看)三合一，但机制本质不同：Java注解是"贴标签，等Spring容器启动扫描才生效"，Python装饰器是"import这行代码自己执行，当场把函数换成BaseTool对象，不需要容器"。装饰器写法像@Around(前+proceed+后结构一模一样)，但@Around是注解靠Spring运行时创建动态代理织入，装饰器自己就是织入动作--等于@Around的advice代码+Spring AOP运行时织入两个角色合一起，import完即生效。

---

### 第五部分：工具系统（第11-13步：工具描述三要素、args_schema校验、tool_choice与工具失败处理）

#### 核心总结

工具系统三件事。一、工具描述是给模型看的API文档(不是给开发看的),写不好出三类问题:不选(召回)、选错(精确)、参数错(准确)。好描述三要素:使用场景+参数说明+返回内容,跟写Swagger一样认真,但占token要精简。二、args_schema=给工具加@Valid,Pydantic Model=DTO。不写校验弱防不住幻觉--万物云没校验时模型编假订单号查库空又编状态,加格式校验假号门口被拦从源头断。三、tool_choice四种值控制调不调工具:auto自决、required必须调一个(防不查就编)、none禁调、指定具体工具。required配args_schema是防幻觉两道闸。工具失败永远返回错误信息不抛异常--抛异常中断agent循环用户收500,返回错误让模型自己决定重试/换工具/问用户,跟Java DAO抛异常被Service catch返错误码一个理。万物云统一返{error,hint,retryable},retryable防模型对不可重试错误无限重试。

#### 流程图

```
   [模型这一轮要不要调工具]  <-- 受两件事影响:
        |                       +-- 工具描述(三要素) --> 选不选/选对没/参数对没
        |                       +-- tool_choice 四值   --> 控制这一轮调不调
        v
   +--------------------------------------------+
   | tool_choice 闸门 (bind_tools 时绑死)        |
   |  "auto"      -> 模型自决(默认,闲聊用)       |
   |  "required"  -> 必须调一个(防"不查就编")    |
   |  "none"      -> 禁调,纯文本回               |
   |  指定工具名  -> 必须调这个(固定流程)        |
   |     跨 provider 稳: {"type":"tool","name":..}|
   +--------------------------------------------+
        | (允许调工具)
        v
   +--------------------------------------------+
   | args_schema 闸门  = @Valid + DTO(Pydantic) |
   |  校验失败 -> ValidationError                |
   |    (框架接住,转错误信息回模型,工具不执行)   |
   |  校验通过 -> 进工具函数                     |
   +--------------------------------------------+
        |
        v
   +-------------------+
   |  工具执行(可能失败)|
   +-------------------+
      /            \
  抛异常(错!)      返回错误信息(对! 生产做法)
     |                |
     v                v
  中断 agent       ToolMessage 回模型
  循环,用户收500   模型自己决定下一步:
                   重试 / 换工具 / 问用户
                   (循环不中断,用户无感)
                   万物云统一返:
                   {error, hint, retryable}
                   retryable 防对不可重试
                   错误无限重试(配 recursion_limit 兜底)
```

#### 各部分作用

- **工具描述(三要素:使用场景+参数说明+返回内容)**：给模型看的API文档,直接决定召回(选不选)/精确(选对没)/准确(参数对没)三个指标;跟写Swagger一样认真,但占token要精简不滥写
- **args_schema(Pydantic Model)**：给工具加@Valid,在工具执行前门口校验参数格式/范围/枚举/字段间依赖,校验失败抛ValidationError被框架接住转错误信息回模型,防模型编的假参数溜进工具查库造幻觉
- **tool_choice(auto/required/none/指定工具名)**：控制模型这一轮调不调工具,bind_tools时绑死;required防'不查就编',指定具体工具跨provider用{"type":"tool","name":...}字典更稳
- **工具失败处理(返回错误信息不抛异常)**：工具内try/except把异常转成错误信息返回,不让异常冒泡中断agent循环;模型看到错误自己决定重试/换工具/问用户,跟DAO抛异常被Service catch返错误码一个理
- **retryable字段**：标记错误是否值得重试(true如数据库超时/false如参数错),防模型对不可重试错误无限重试,配合recursion_limit兜底硬停

#### 后端类比

工具系统整套就是 Spring MVC 那套的翻版。① @tool = @Component + @RequestMapping + @ApiOperation 三合一(注册 Bean + 定义访问路径 + 生成 Swagger 文档)，区别是这文档给 AI 模型看不是给开发看。② args_schema = Controller 方法参数上的 @Valid；Pydantic Model = 带 @NotBlank/@Pattern 注解的 DTO 类；校验失败抛 ValidationError 被框架接住 = MethodArgumentNotValidException 被全局 @RestControllerAdvice 接住，工具/Controller 都不执行。别在 Service 里手写 if 判断参数，统一在 DTO + @Valid 层收口。③ tool_choice = 给 Service 注入"操作权限配置"：auto=全权委托、required=强制动手(不能拍脑袋瞎答)、none=只读模式禁手。不同 model 实例 = 不同配置的 Service Bean，万物云分类路由到不同 agent = 前置 Controller 按请求类型转发到不同 Service。指定具体工具用 {"type":"tool","name":...} 字典形式更跨 provider 稳，像写死路由 path。④ 工具失败抛异常 vs 返回错误信息 = DAO 抛异常不接冒泡到用户 500，vs DAO 抛异常被 Service catch、Controller 返错误码 JSON 用户拿友好提示。万物云统一 try/except 装饰器套在所有 @tool 外 = Spring 全局 @RestControllerAdvice 统一异常处理，retryable 字段 = 错误码里带"是否可重试"标记，防调用方无脑重试。

---

### 第六部分：上下文工程（CE vs PE / 上下文5部分 / 裁剪-摘要-外移三解法 / SummarizationMiddleware 累积摘要机制）

#### 核心总结

上下文工程解决Agent多轮循环下上下文膨胀。核心：把Prompt Engineering(调一句静态prompt措辞)升级成Context Engineering(管模型每轮看到的全量动态上下文)。因为循环每轮加2条消息，窗口有限必然爆。

模型每轮看5部分：System prompt、历史messages、工具定义、检索结果、长期记忆。最大坑是工具定义也占token--LLM无状态像stateless REST服务，每轮必须把全部工具JSON重发一遍，12个Skill就2000token/轮，常被漏算。

三解法：裁剪(像LRU删旧留近N条)、摘要(像日志滚动归档，小模型把旧对话压成一段替换旧消息)、外移(像冷热分离存Store留指针用时检索)。裁剪单独用会丢关键事实，必须配合。万物云配方=System+工具定义+[摘要+最近N轮(含当前query)]。

SummarizationMiddleware在before_model钩子跑：按token阈值触发(不按轮数，一轮可能50也可能5000token)，保留最近messages_to_keep条，其余连同上次摘要重新压成1条累积摘要替换，始终只1条不拼接不增长，用独立小模型省成本。新信息只摘一次全保真，只有最老尾巴多次摘。

#### 流程图

```
                  上下文工程 (第14-16步)
   Agent循环(第1步): 每轮 +2条 (AIMessage + ToolMessage)
        |
        v   上下文不断膨胀, 窗口有限
   +----------------------------------------------+
   | 第15步: 模型每轮看到的上下文 = 5部分           |
   |   [1]System prompt    [2]历史 messages       |
   |   [3]工具定义 JSON    [4]检索结果(RAG)        |
   |   [5]长期记忆(Store)                          |
   |   * LLM无状态 -> 工具定义每轮重发(常被漏算)    |
   +----------------------------------------------+
        |  爆窗口 / 成本爆炸 / lost-in-the-middle
        v
   +--- 第16步: 三种解法 (组合用, 非单选) ---+
   | 裁剪 Trimming  | 摘要 Summarization | 外移 Offloading |
   | 删旧留近N条    | 小模型压成1段       | 存Store留指针    |
   | LRU淘汰类比    | 日志滚动归档类比     | 冷热分离类比     |
   +----------------+--------------------+------------------+
        | 优先级: System永远留 > 最近N轮/关键事实 > 工具结果 > 旧寒暄
        v
   万物云配方: 每轮发 = System + 工具定义 + [摘要 + 最近N轮(含当前query)]

   ===== SummarizationMiddleware (before_model 钩子, 洋葱模型落地) =====

   每轮主模型调用前 -->
   messages = [S, m1, m2, ... m_n]
        |
   count_tokens > max_tokens_before_summary ?   (按 token 不按轮数)
        |-- 否 --> 原样发给主模型
        |-- 是 -->
              分割: keep = messages[-messages_to_keep:]   # 保留最近N条
                    old  = messages[:-messages_to_keep]    # 含上次摘要
              summary_new = 小模型.invoke(摘要提示 + old)   # 累积摘要
              messages = [S, summary_new] + keep           # 始终1条, 不拼接不增长
        v
   主模型看到压缩后的 messages
        |
   累积摘要: summary_new = summarize(summary_old + 新原始消息)
             新信息只摘一次(全保真), 只有最老尾巴多次摘(失真更慢)
```

#### 各部分作用

- **第14步 CE vs PE**：把'调一句静态prompt措辞'升级为'管模型每轮看到的全量动态上下文'，立住Agent循环每轮+2条消息导致膨胀这一必须管的根因
- **第14步 核心矛盾**：窗口有限 vs 上下文膨胀，不管会爆窗口/成本爆炸/lost-in-the-middle质量下降
- **第15步 5部分拆解**：明确模型每轮看到的是 System prompt + 历史messages + 工具定义 + 检索结果 + 长期记忆 的总和，算token要全算进去
- **第15步 工具定义占token坑**：揭示LLM无状态(像stateless REST服务)导致每轮必须重发全部工具JSON schema，是常被漏算的每轮固定开销(12个Skill≈2000token/轮)
- **第16步 裁剪 Trimming**：直接删旧消息留最近N条，最简单但有损(类比LRU缓存淘汰)
- **第16步 摘要 Summarization**：调小模型把旧对话压成一段摘要替换旧消息，保留信息省token(类比日志滚动压缩归档)
- **第16步 外移 Offloading**：信息存外部Store/向量库，上下文只留指针用时检索回来，最彻底最复杂(类比冷热分离)
- **第16步 优先级策略**：System永远留 > 最近N轮/关键事实 > 工具结果 > 旧寒暄，关键事实外移不靠摘要(类比缓存pin关键数据+LRU淘汰)
- **第16步 万物云配方**：每轮发 = System + 工具定义 + [摘要 + 最近N轮(含当前query)]，检索结果用完即丢，三解法组合非单选
- **SummarizationMiddleware before_model钩子**：每轮主模型调用前检查token阈值，超了就分割保留最近messages_to_keep条、其余重摘替换
- **累积摘要机制**：summary_new=summarize(summary_old+新原始消息)始终1条不拼接不增长，新信息只摘一次全保真，只有最老尾巴多次摘失真更慢
- **4个设计点**：累积摘要/保留近N条不摘/用独立小模型省成本/放before_model钩子每轮压缩；**4个坑**：阈值太低频触发/累积丢早期事实/ToolMessage丢结构/摘要模型太弱

#### 后端类比

整套类比到后端Java生态：CE vs PE = 管一个事务全程所有读写数据+会话缓存+用户画像 vs 优化一条SQL的写法（PE是CE的子集，那句静态prompt只是CE管的5部分里的第1部分）。模型每轮5部分上下文里，工具定义每轮重发 = LLM像 stateless REST 服务（如无状态Spring Controller），每次请求都得把全部上下文塞进请求体，服务器不记得你上次带了什么--所以全公司Swagger接口文档每轮都得带一遍。三种解法逐个对应：裁剪 = LRU缓存淘汰（超容量踢最老）；摘要 = 日志滚动压缩归档（旧日志不删，压成摘要省空间留线索）；外移 = 冷热分离（热数据Redis、冷数据DB，用到再查，上下文是热区、Store是冷区）。优先级策略 = 缓存pin住关键数据不淘汰 + LRU保最近。SummarizationMiddleware 的 before_model 钩子 = Servlet Filter 链 / Spring HandlerInterceptor 的 preHandle（第6步洋葱模型：注册顺序[A,B,C]进入A->B->C->模型，before_*外到内、after_*内到外，跟 addInterceptor 顺序一致），每轮主模型调用前先跑这个拦截器压缩，主模型看到的已是压缩后状态。万物云 ContextInjectionMiddleware（before_model 注入动态信息+裁剪）也是同一个钩子位的活，类比 HandlerInterceptor.preHandle 每次请求前加公共参数。

---

### 第七部分：记忆系统 - 短期 / 长期 / 任务状态 三者正交

#### 核心总结

Agent 记忆系统三种，正交不替代。短期=这次会话的对话历史 messages，两层：messages 在进程内存 + checkpointer 每个 super-step 把整张 State 快照按 thread_id 存外部，重启同 thread_id 拉回恢复，类比 HttpSession(内存+session 持久化到 Redis)，thread_id=JSESSIONID。长期=跨会话的用户画像/偏好，存 Store(KV 库，namespace 元组分组)，不自动进上下文，由 before_model middleware 每轮用 user_id 主动 store.get() 检索拼 SystemMessage 注入 messages，类比用户画像表按 userId 查；不全量塞是为省 token + 防 lost-in-the-middle。任务状态=这次任务进度(intent/risk_level/current_step)，存 State 自定义字段，给流程看、控制条件边路由，类比 Activiti execution.setVariable 流程变量，任务结束清。三者一次执行同时存在：State 里 messages 给模型看 + intent 给流程看，before_model 从 Store 注入画像。万物云长期记忆实际用 pgvector + 相似合并 + TTL(非 RedisStore，类名待查官方包)。

#### 流程图

```
   一次 Agent 执行   (configurable.thread_id = 会话钥匙 = JSESSIONID)
   =================================================================

   [短期记忆]              [任务状态]                [长期记忆]
   messages[]              intent / risk_level       Store (跨所有会话)
   进程内存                 current_step             namespace=(\"user\",uid)
   给模型看                 给流程/代码看             你主动 put/get
       |                        |                          |
       |                        | 每轮 before_model        |
       |                        v                          v
       |                   条件边读               store.get((\"user\",uid))
       |              (risk=高 -> 人工)                    |
       |                                              拼 SystemMessage
       |                                                  |
       +<----------------- 注入 messages 最前 -------------+
       |
       v
   [LLM 调用]  无状态: f(messages) -> response
       |
   每个 super-step 结束:
       v
   checkpointer 存【整张 State 快照】(thread_id + 版本号)
       |           含 messages + 任务状态字段
       v
   [外部存储 DB/Redis]
   进程重启 -> 同 thread_id 拉回 = 短期 + 任务状态一起恢复

   --- 三记忆正交(各管一摊, 一次执行同时跑, 不能合并) ---
   生命周期: 短期=会话  长期=跨会话  任务状态=任务
   作用域:   短期=本thread  长期=跨所有thread  任务状态=本次任务
   给谁看:   短期/长期=模型(自然语言)  任务状态=流程(结构化字段)
```

#### 各部分作用

- **messages（短期-内存层）**：当前会话累积的对话历史，进程内存，给模型看，进程重启就没
- **checkpointer（短期-持久层）**：每个 super-step 后把整张 State 快照（含 messages 和任务状态字段）按 thread_id 存外部，跨运行恢复，支持 time-travel 回放
- **thread_id**：定位会话线程的钥匙（=JSESSIONID），同 id 复跑即拉回历史，是短期记忆的检索主键
- **Store（长期记忆库）**：跨所有会话的 KV 存储（BaseStore），按 namespace+key 存用户画像，你主动 put/get/delete，框架不自动管（跟 checkpointer 相反）
- **namespace 元组**：Store 的第一个参数，给数据分组隔离（=表名+主键/Redis key前缀），支持层级路径和多租户（个人空间/团队空间/项目空间）
- **before_model middleware**：每轮调模型前用 user_id 主动 store.get() 检索画像，拼 SystemMessage 注入 messages 最前；不全量塞为省 token + 防 lost-in-the-middle 注意力分散
- **State 自定义字段（任务状态）**：intent/risk_level/current_step/refund_amount 等结构化业务进度，给流程看、控制条件边路由，任务结束清
- **三者正交**：三个独立维度，生命周期/作用域/给谁看都不同，一次执行同时存在但不能合并（混存会越界串台、格式乱、不知道啥时候清）

#### 后端类比

短期记忆整体=HttpSession：messages=session在内存的会话数据，checkpointer=session持久化到Redis(重启不丢)，thread_id=JSESSIONID。长期记忆=用户画像表/Redis：跨会话一直存，按userId查，每次请求只查需要的字段不全表读；before_model主动检索=Controller里按userId查画像注入Service层。任务状态=Activiti/Camunda工作流流程变量：execution.setVariable("risk_level","低")，跟流程实例走、流程结束就清、给流程引擎看控制流转(条件网关)。三者一次执行同时存在=一次HTTP请求里同时用HttpSession(取会话数据)+查user表(取用户信息)+读写Activiti流程变量(任务进度)，三套存储三套生命周期谁也替不了谁。Store的namespace多租户隔离=SaaS的tenant_id，忘带WHERE=跨租户数据泄露(多租户最经典安全bug)，防法=ORM拦截器自动注入tenant_id(对应从state取user_id拼namespace不硬编码)。checkpointer vs Store=会话状态(框架自动存取,绑thread) vs 业务数据(你主动读写,跨所有会话)。⚠️万物云长期记忆实际用pgvector(Postgres+向量扩展)+相似合并+TTL淘汰(非RedisStore)；InMemoryStore确证存在，RedisStore/pgvector系Store的确切类名与所在包需查当前langgraph包确认。

---

## 【7 模块速查表】

| 模块 | 核心一句话 | 后端类比 | 对应辅导文档步数 |
|------|-----------|---------|----------------|
| 一、Agent 本质 | while(true) 受控循环，模型运行时决定调不调工具/何时停，4 种终止 + 3 层防死循环 | Activiti 工作流(模型实时生成流程定义) + 审计日志(只增不减) + N+1 设 maxDepth=3 | 第 1-3 步 |
| 二、框架层级 | LangGraph/create_agent/create_deep_agent 三层封装，万物云因非标准拓扑+时间点选手动建图 | Spring Framework/Boot/Cloud 三层；定制拓扑退回手动配 Bean | 第 4-5 步 |
| 三、Middleware | Agent 的 AOP，洋葱套循环外；wrap_*=@Around 能重试，before_*=@Before 管不了次数 | Spring AOP + HandlerInterceptor + Servlet Filter 链三合一 | 第 6-9 步 |
| 四、消息模型 | 四类消息(System/Human/AI/Tool) + tool_call_id 配对 + @tool 装饰器 import 时转 BaseTool | HTTP 请求处理链；tool_call_id=MQ correlationId；@tool=@Component+@RequestMapping+Swagger | 第 10-11 步 |
| 五、工具系统 | 工具描述给模型看 + args_schema 校验 + tool_choice 控调不调 + 失败返错误信息不抛异常 | @Valid+DTO+@RestControllerAdvice；tool_choice=给 Service 注入操作权限 | 第 11-13 步 |
| 六、上下文工程 | CE 管每轮全量动态上下文，裁剪/摘要/外移三解法组合，工具定义每轮重发常被漏算 | LRU 淘汰 + 日志滚动归档 + 冷热分离；LLM=stateless REST | 第 14-16 步 |
| 七、记忆系统 | 短期 messages+checkpointer / 长期 Store 主动注入 / 任务 State 字段，三者正交同时存在 | HttpSession + 用户画像表 + Activiti 流程变量 | 第 17-20 步 |

> **编号说明**：原路线图共 35 步，实际讲解中「第 11 步 tool_call_id」和「第 12 步 @tool」合并进了第 10 步，所以从「工具描述」起实际步数比原图少 2 步。上表步数按实际编号标注，内容一点没少。详见《Agent工程逐步辅导记录.md》开头编号说明。
