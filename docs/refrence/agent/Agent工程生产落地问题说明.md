# Agent 工程生产落地问题说明

> 配合《Agent工程逐步辅导记录.md》第 21 步补充用。
> **来源**：已抓取核对 LangGraph 官方文档四页（docs.langchain.com）：
> - `/oss/python/langgraph/persistence`（persistence）
> - `/oss/python/langgraph/checkpointers`（checkpointers）
> - `/oss/python/langgraph/fault-tolerance`（fault tolerance）
> - `/oss/python/langchain/human-in-the-loop`（HITL）
>
> 面向：后端 Java 转 Agent 方向，**C 端生产多实例部署**场景。
> 风格：后端类比（Spring Session Redis / Redis 分布式锁 / K8s 优雅下线 / @Retryable）+ 官方原话引用。

---

## 问题根源：C 端必然多实例，Agent 又是有状态的

普通 Spring Boot 无状态服务多实例很简单：前面负载均衡，请求打哪个实例都行，因为服务不记状态（状态在 Redis/DB）。

**Agent 不一样，它有状态**：
- 短期记忆 messages + checkpointer 存的 graph state（第 17 步）
- 长期记忆 Store（第 18 步）
- 进行中的 run（HITL 暂停等人工，第 21 步）
- middleware 里的上下文（第 6-9 步）

如果状态在进程内存（`InMemorySaver` / `InMemoryStore`），多实例下：

```
用户请求1 (invoke)  -> 负载均衡 -> 实例A   (state 存 A 内存)
用户请求2 (resume)  -> 负载均衡 -> 实例B   (B 没有 state, 拉不回, 失败!)
```

这就是**分布式 session 问题**的 Agent 版。下面 10 个问题都围绕"多实例 + 有状态"展开。

---

## 问题 1：状态共享 = 分布式 session 问题

### 现象

HITL 第 21 步讲过：第一个 invoke 暂停后 state 存 checkpointer，第二个 resume 用同 thread_id 拉回。**但如果两次请求打到不同实例**，而 checkpointer 是 `InMemorySaver`（进程内存），实例 B 根本没有实例 A 存的 state，resume 直接失败。

官方原话（persistence 文档）：
> "MemorySaver and InMemorySaver store checkpoints in RAM. When the process restarts, all checkpoints are lost. **Fix: Use a persistent checkpointer for production**: PostgresSaver / SqliteSaver"

### 后端类比

= **Spring Boot 用内存 HttpSession 部署多实例**：session 在实例内存，负载均衡打到别的实例就找不到 session。
- 解法 1（Java）：Spring Session + Redis，session 统一存 Redis，所有实例共享
- 解法 2（Agent）：checkpointer 用 `PostgresSaver` / `AsyncPostgresSaver`，state 统一存 Postgres，所有实例共享

`thread_id` = JSESSIONID，checkpointer 后端（Postgres）= Spring Session Redis。Store 同理：`InMemoryStore` 也不能多实例，生产用共享后端（万物云用 pgvector）。

### 解法（官方代码）

```python
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver.from_conn_string("postgresql://user:pwd@host:5432/db")
checkpointer.setup()   # 官方原话: "Creates tables with indexes"

agent = create_agent(
    model=..., tools=..., middleware=[...],
    checkpointer=checkpointer,   # 共享 Postgres, 所有实例连同一个库
)
```

**关键**：所有实例连**同一个 Postgres**，state 在 DB 不在进程内存。请求打哪个实例都能用 thread_id 拉回。

### 生产坑

- `PostgresSaver` 连接池要配好：N 实例 × M 并发 × K 连接，别打爆 Postgres（用 PgBouncer 池化）
- 官方提醒 `thread_id` 存在 Postgres 列里**有 255 字符限制**，超了报错，用 UUID：
  ```python
  config = {"configurable": {"thread_id": str(uuid.uuid4())[:255]}}
  ```

---

## 问题 2：并发写同一会话 = 分布式锁问题

### 现象

HITL 暂停后，如果用户**双击"批准"**，或前端因网络超时**重发了 resume 请求**，两个请求同时 resume 同一个 thread_id：

```
请求A resume(thread_id=abc123, approve) -> 实例A 跑工具
请求B resume(thread_id=abc123, approve) -> 实例B 跑工具
```

如果工具是"退款 100 元"，**可能执行两次**--退 200。这就是**并发写同一资源的 race condition**。

### 后端类比

= **Redis 分布式锁问题**：多个请求同时改同一资源（库存、余额、订单状态），必须串行化。
- Java 解法：Redisson 分布式锁 / `SETNX` / 数据库行锁 / 乐观锁版本号
- Agent 解法：**同一 thread_id 的写入必须串行化**

### LangGraph 的机制（部分官方核对）

LangGraph 的 checkpointer 用 `(thread_id, checkpoint_id)` 版本化每次写入，`put_writes` 写的是 per-task 的 pending writes（checkpointers 文档原话："Store node-output rows for a single task within the current superstep, linked by (thread_id, checkpoint_ns, checkpoint_id)"）。这提供了**版本顺序**，但**不等于自动分布式锁**。

> ⚠️ **待核实点**：LangGraph 是否内置"同一 thread 同时只允许一个活跃 run"的保护，我没在 persistence/checkpointers/fault-tolerance 三页找到明确说明。已知的是 LangGraph **Agent Server**（官方托管平台）会自动处理并发与持久化（persistence 文档原话："When using the Agent Server, you do not need to implement or configure checkpointers or stores manually. The server handles persistence infrastructure behind the scenes"）。
>
> **自托管（万物云这种手动 StateGraph）场景**：建议自己加一层 thread 级串行化--用 Redis 分布式锁包住 resume（锁 key = thread_id），或用 Postgres 行锁 / 唯一约束防重。**面试讲到这要说"我们自托管，并发保护是自己加的 Redis 锁"，别说是框架白送的**。具体框架内置了多少，以当前官方 docs / 源码为准。

### 解法（自托管场景的工业实践）

```python
# resume 前, 先抢 thread_id 的分布式锁
lock_key = f"agent:thread:{thread_id}"
with redis_lock(lock_key, timeout=60):   # Redisson 等价
    agent.invoke(Command(resume=decision), config={"configurable":{"thread_id": thread_id}})
```

或工具侧加**幂等键**（见问题 7），即使重放也不重复执行副作用。

---

## 问题 3：多会话同时进来 = 并发模型

### 现象

C 端 1000 个用户同时聊天，每个一个 thread_id，互不干扰。但单实例怎么扛并发？

### 后端类比 + 解法

| 层 | Java 后端 | Agent 后端 |
|---|---|---|
| 单实例并发 | Tomcat 线程池（200 线程）/ WebFlux 事件循环 | Python asyncio 事件循环（uvicorn）|
| 多实例 | N 个 Tomcat + 负载均衡 | N 个 uvicorn worker + 负载均衡 |
| 阻塞点 | DB / RPC I/O | LLM 调用 / DB I/O（都是网络等） |

关键点：
- **不同 thread_id 无竞争**：各跑各的，state 各存在 Postgres 不同行，不需要锁
- **同一 thread_id 才有竞争**（问题 2）
- **Python GIL**：CPU 密集任务串行，但 Agent 的瓶颈是 I/O（调 LLM、查 DB），asyncio 一个事件循环能扛很多并发 I/O
- **用 async API**：`ainvoke` / `astream` 不阻塞线程，一个 worker 扛多并发；用同步 `invoke` 会一个请求占一个线程，并发上不去
- **worker 数**：uvicorn `--workers N` 起多进程，绕过 GIL；N 一般 = CPU 核数

### 生产坑

- LLM 调用慢（几秒到几十秒），同步 invoke 会把线程占住，**必须用 async**（第 22 步 Streaming 讲 `astream_events`）
- Postgres 连接池大小要匹配并发数，否则请求等连接
- 限流：C 端要给单用户限流（防恶意刷），给 LLM 调用限流（防 token 成本爆炸）

---

## 问题 4：实例被杀 = graceful shutdown（SIGTERM）

### 现象

多实例部署，K8s 滚动更新 / 缩容时，Pod 收到 SIGTERM 被杀。如果这时 agent 正跑到一半（run 进行中），**直接杀会丢工作**。

### 官方机制（fault-tolerance 文档，已核对）

LangGraph 提供 **graceful shutdown**：跑到当前 superstep 完成，存一个可恢复的 checkpoint，再停。

官方原话：
> "Cooperative shutdown lets you stop an in-flight graph run after the current superstep completes and save a resumable checkpoint. This is useful for handling SIGTERM signals or any external supervisor that needs to reclaim resources without losing work."

机制：`RunControl` + `control.request_drain()` 信号"该停了"，graph 在下一个 superstep 边界停，抛 `GraphDrained(reason)`，checkpoint 已存好。

drain 是**协作式**的，**不会抢占正在跑的节点**（官方表格）：

| 场景 | 行为 |
|---|---|
| 节点正在执行 | 跑完，下个 superstep 才 drain |
| 节点正在重试 | 重试循环跑完（成功或耗尽），再 drain |
| graph 正好自然结束 | 正常返回 |
| 还有 superstep 没跑 | 抛 GraphDrained，checkpoint 已存可恢复 |
| 子图请求 drain | 往上冒泡，父图在自己下个 superstep 边界停 |

### resume after drain

```python
# SIGTERM 触发 drain 后, run 停了但 checkpoint 存了
# 请求重打到别的实例(或本实例重启后), 用同 thread_id 续:
result = graph.invoke(None, config)   # config 里同 thread_id
```
官方原话："Resume a drained run with `invoke(None, config)` using the same thread_id"。

### 后端类比

= **K8s 优雅下线 + Spring 的 PreDestroy**：
- K8s 给 Pod 发 SIGTERM，给 grace period（如 30s），应用在这段时间处理完在途请求再退出
- LangGraph 的 drain = 应用收到 SIGTERM 后，把在跑的 graph 跑到 superstep 边界存档再退
- = Tomcat 收到 SIGTERM 后不再接新请求、处理完在途请求再关

### 生产坑

- K8s `terminationGracePeriodSeconds` 要 > 最长 superstep 耗时，否则 grace period 到了 K8s 发 SIGKILL 强杀，drain 没跑完
- SIGTERM 钩子要接上 `request_drain()`（官方有 "SIGTERM hook pattern" 章节）
- drain 期间的新请求要路由到别的实例（负载均衡摘流量）

---

## 问题 5：节点失败 = retries + resume-safe + pending writes

### 现象

agent 跑某节点时，调的外部 API 超时 / 网络抖动 / 抛异常。怎么办？

### 官方三件套（fault-tolerance 文档，已核对）

**1. Retries（重试）**--`RetryPolicy`：

```python
from langgraph.types import RetryPolicy
builder.add_node("call_api", call_api, retry_policy=RetryPolicy(max_attempts=3))
```

参数（官方默认值）：
- `max_attempts=3`（含首次）
- `initial_interval=0.5` 秒
- `backoff_factor=2.0`（指数退避）
- `max_interval=128.0` 秒
- `jitter=True`（加随机抖动防雪崩）
- `retry_on`：默认 `default_retry_on`，**不重试** ValueError/TypeError/ArithmeticError 等编程错误，**重试** 5xx HTTP、`NodeTimeoutError`

**2. pending writes（节点级容错）**--`put_writes`：

官方原话："if another node in the same super-step fails, the successful nodes' writes are already durable and don't need to be re-run on resume. The full state snapshot is then committed once the super-step completes."

= 一个 superstep 里多个节点并行，成功的节点写入已持久化（pending writes），失败的节点 resume 时**不用重跑成功的那些**。

**3. resume-safe failures（失败上下文也存）**：

官方原话："Failure provenance is checkpointed. If the graph is interrupted or the process crashes after a node fails but before the handler completes, the handler sees the same NodeError context when the graph resumes from its checkpoint."

= 节点失败的信息也 checkpoint 了，进程崩了重启 resume，错误处理器看到的还是同样的 NodeError 上下文。

### 后端类比

= **Spring `@Retryable` + 幂等消费 + 消息队列重投**：
- RetryPolicy = `@Retryable(maxAttempts=3, backoff=@Backoff(delay=500, multiplier=2))`
- pending writes = MQ 消费者处理一批消息，处理到第 3 条失败，前 2 条已 ack 不会重投
- resume-safe = 死信队列里带着完整失败上下文，重处理时看得到当时为啥失败

### 生产坑

- 只重试可重试的（网络/5xx），别重试业务错误（参数错、权限拒绝）--官方默认就是这样
- 重试要配超时（`NodeTimeoutError`），否则一个慢节点重试 3 次把资源占死
- 工具副作用不能纯靠重试（退款重试 3 次 = 退 3 倍），必须配幂等键（问题 7）

---

## 问题 6：超时

### 官方机制（fault-tolerance 文档）

- **run timeout**：整个 run 最长时间
- **idle timeout**：空闲超时（没有进展）
- **progress signals / heartbeat mode**：长节点定期发心跳证明还活着，否则判定卡死
- **NodeTimeoutError**：节点超时抛的异常，默认可重试

### 后端类比

= **HTTP 请求超时 + 心跳检测**：
- run timeout = 接口整体超时
- idle timeout = 读超时（socket 一直没数据）
- heartbeat = 长任务心跳保活（像 Eureka 心跳、K8s liveness probe）

### 生产坑

- LLM 调用可能卡几十秒，必须设节点超时 + 心跳，否则一个卡住的 LLM 调用占着 run 不放
- 超时值要分层：节点超时 < run 超时 < HTTP 网关超时，避免网关先断了 agent 还在跑

---

## 问题 7：幂等性

### 现象

网络不稳，前端 resume 请求超时，**自动重试**了同一个 resume。如果工具是退款，重试 = 重复退款。

### 后端类比

= **支付接口幂等**：支付回调可能重发，订单接口必须靠幂等键（order_id）防重复扣款。

### 解法

- **工具侧幂等键**：工具执行带业务幂等键（如 `refund_id`），工具内先查"这个 refund_id 处理过没"，处理过直接返回上次结果
- **resume 侧锁**（问题 2 的 Redis 锁）：同 thread_id 串行化，第二个 resume 等第一个跑完或直接拒
- **checkpointer 版本**：`checkpoint_id` 版本化，重放的 resume 如果版本已过会被识别（部分保护）

```python
@tool
def refund(refund_id: str, amount: float) -> str:
    # 幂等: refund_id 处理过就直接返回
    if redis.exists(f"refund:done:{refund_id}"):
        return "已处理过, 跳过"
    do_refund(amount)
    redis.set(f"refund:done:{refund_id}", "1", ex=86400)
    return "退款成功"
```

---

## 问题 8：状态膨胀与清理

### 现象

官方原话（persistence 文档）："Over long conversations, checkpoints accumulate. This can increase latency and storage costs."

每个 superstep 存一个 checkpoint，长对话 + 多用户，Postgres 里 checkpoint 表无限增长。

### 解法（官方）

官方原话："Prune old checkpoints periodically or set a retention policy" + "Consider adding a cron job to delete checkpoints older than N days"。

### 生产坑

- 定时任务清老 checkpoint（保留最近 N 天 / 每个线程保留最近 K 个）
- **GDPR / 用户删号**：用户要求删除数据时，必须按 user_id 清掉他所有 thread 的 checkpoint + Store 里的画像（namespace 按用户隔离正好方便清，第 18 步讲过）
- checkpointer 表要索引（thread_id, checkpoint_id），`setup()` 会建

---

## 问题 9：长任务与 HTTP 超时

### 现象

复杂 agent run 可能跑几分钟（多轮工具调用）。HTTP 网关通常 30-60s 超时，**不可能一次 invoke 挂着连接等完**。

### 后端类比 + 解法

= **异步作业模式**（Java 提交任务返回 jobId，轮询/Webhook 取结果）：
- 第一次请求触发 run，返回 job_id（= thread_id），不等完
- 前端轮询 `/status?thread_id=xxx`，或用 **SSE/WebSocket** 流式拿进度
- run 跑完结果存 checkpointer，前端用 thread_id 取

这正是第 22-23 步要讲的 **Streaming + SSE 全链路**：`astream_events` 边生成边推前端，不用等全部跑完。

---

## 问题 10：可观测性

### 现象

多实例下，一个请求可能 invoke 在实例 A、resume 在实例 B、工具调用的子服务在别处。排查问题要跨实例串起来。

### 后端类比 + 解法

= **分布式链路追踪**（SkyWalking / Zipkin / Jaeger）：
- 每个请求生成 `trace_id`，跨实例传递（HTTP header / MDC）
- Agent 版：LangSmith / Langfuse 做 trace，每步（调模型、调工具、checkpoint）都记，按 thread_id 串
- 万物云：LangSmith/Langfuse 仅"了解"未用（诚实底线），自研 trace 或日志聚合（ELK）按 trace_id 串

### 生产坑

- `trace_id` 要从 HTTP 入口注入，贯穿 middleware（第 6-9 步的 Audit middleware 记 trace_id）到工具调用
- LLM 调用的 input/output token、耗时、成本要记（成本监控，防 token 爆炸）

---

## 万物云现实（按真实讲，别翻车）

- **多实例**：C 端必然多实例，万物云客服 agent 多实例部署
- **checkpointer 后端**：源文档 08 说用 PostgresSaver（**按真实讲**，若实际是别的如自研封装，说真实的，别被表结构追问翻车）。InMemorySaver 只在本地测
- **状态共享**：所有实例连同一个 Postgres，state 共享
- **并发保护**：自托管（手动 StateGraph），thread 级串行化是自己加的（Redis 锁或 DB 行锁），**不说框架白送**
- **优雅下线**：K8s 滚动更新接 SIGTERM + drain（若实际没接 drain 说真实的）
- **重试**：节点级 RetryPolicy，LLM/DB 抖动重试，业务错误不重试
- **幂等**：退款等副作用工具带 refund_id 幂等键
- **清理**：定时任务清老 checkpoint
- **可观测**：trace_id 跨实例，LangSmith/Langfuse 仅了解未用（诚实底线）

---

## 速查表

| 问题 | 后端类比 | 解法 | 官方核对 |
|---|---|---|---|
| 1 状态共享 | Spring Session Redis | PostgresSaver 共享，所有实例连同一库 | ✅ persistence |
| 2 并发写同会话 | Redis 分布式锁 | thread 级串行化（Redis 锁/DB 行锁）+ 幂等键 | ⚠️ 部分核对（Agent Server 自动，自托管自己加） |
| 3 多会话并发 | Tomcat 线程池/WebFlux | async（ainvoke）+ uvicorn workers + 连接池 | ✅ 通用 |
| 4 实例被杀 | K8s 优雅下线 + PreDestroy | RunControl + request_drain，resume 用 invoke(None, thread_id) | ✅ fault-tolerance |
| 5 节点失败 | @Retryable + MQ 重投 | RetryPolicy + pending writes + resume-safe | ✅ fault-tolerance + checkpointers |
| 6 超时 | HTTP 超时 + 心跳 | run/idle timeout + heartbeat | ✅ fault-tolerance |
| 7 幂等 | 支付幂等键 | 工具带业务幂等键 + resume 锁 | ✅ 通用模式 |
| 8 状态膨胀 | 日志清理/GDPR | cron 清老 checkpoint，按 user_id 清 | ✅ persistence |
| 9 长任务 | 异步作业模式 | 返回 thread_id，SSE 流式取结果 | ✅（第22-23步展开） |
| 10 可观测 | 分布式链路追踪 | trace_id 跨实例 + LangSmith/自研 | ✅ 通用 |

---

## 核实说明（诚实边界）

**已抓取官方文档核对**（docs.langchain.com）：
- persistence：InMemorySaver 重启丢、PostgresSaver 生产用、thread_id 255 字符、checkpoint 无限增长要 cron 清、Agent Server 自动处理持久化
- checkpointers：`put_writes` pending writes 机制、per-task 容错
- fault-tolerance：RetryPolicy 参数与默认值、graceful shutdown（RunControl/request_drain/drain 语义表/resume after drain）、resume-safe failures、timeouts/heartbeat
- human-in-the-loop：checkpointer 必须、AsyncPostgresSaver 生产、Command(resume) 同 thread_id、四种决策

**未在上述文档找到明确说明，需进一步核对**：
- LangGraph 是否内置"同一 thread 同时只允许一个活跃 run"的硬保护（问题 2）。已知 Agent Server 自动处理，自托管场景建议自己加锁，**别说框架白送**。以当前官方 docs / 源码为准。

**万物云具体实现**：按真实讲（PostgresSaver/自研、是否接 drain、自研 trace 等），不编造未用技术。
