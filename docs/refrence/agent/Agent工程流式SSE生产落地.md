# Agent 工程流式 SSE 生产落地

> 这份文档专讲第 22-23 步的**流式输出 + SSE 全链路生产落地**，用**完整生产伪代码**讲透。
> 主辅导文档 `Agent工程逐步辅导记录.md` 第 22-23 步留摘要指向这里。

## 真实性约束（先看这个，不乱说）

写技术内容前先标来源，三类不混：

| 标记 | 含义 | 例子 |
|---|---|---|
| 🟢 | 官方文档明确（已 grep 确认） | stream/stream_events API、stream_mode、checkpointer 存 super-step 边界 state、thread_id 是 key、Command(resume) 是 HITL 恢复方式 |
| 🟡 | 通用 web 规范（非 LangGraph，MDN/W3C 确认） | SSE 协议（data:/event:/id:/retry:）、EventSource 自动重连、Last-Event-ID 头、nginx proxy_buffering、会话亲和 |
| 🔴 | 推理的合理做法（官方未明确，标"待核"） | checkpointer 不保 token 序号 -> token 级续传非开箱即用、重连用同 thread_id 续流、token event 带 id 精确补发 |

**面试口径**：🟢 照实说、🟡 说"这是通用 web 规范"、🔴 说"这是我们的做法/推理，官方没明说"。

---

## 第 0 层：基础 SSE 完整链路（先把主干跑通）

### 场景

前端聊天框，用户输入"你好"，后端调 LangGraph agent，LLM 流式生成回复，前端逐字显示（打字机效果）。

### 完整伪代码（后端 FastAPI + 前端 EventSource）

**后端（Python / FastAPI）**：

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langgraph.prebuilt import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import HumanMessage

app = FastAPI()

# 建一个带 checkpointer 的 agent（🟢 第21步讲过 checkpointer 配置）
agent = create_agent(
    model=...,
    tools=[...],
    checkpointer=InMemorySaver(),   # 🟢 生产换 AsyncPostgresSaver
)

@app.get("/chat")
def chat(thread_id: str, message: str):
    def event_stream():
        # 🟢 stream_events 拿到 typed projection 迭代器
        stream = agent.stream_events(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": thread_id}},
            version="v3",
        )
        # 🟢 stream.messages 是 token 级独立迭代器
        for msg in stream.messages:
            for token in msg.text:
                # 🟡 SSE 格式: 每个事件 = "data: 内容\n\n"（一对换行终止）
                yield f"data: {token}\n\n"
        # 结束标记，告诉前端流完了
        yield "data: [DONE]\n\n"

    # 🟡 SSE 响应: Content-Type = text/event-stream
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )
```

**前端（JavaScript / EventSource）**：

```javascript
const es = new EventSource("/chat?thread_id=abc123&message=你好");

es.onmessage = (e) => {
    if (e.data === "[DONE]") {
        es.close();          // 流结束，关连接
        return;
    }
    // 逐 token append = 打字机效果
    document.getElementById("output").textContent += e.data;
};

es.onerror = (e) => {
    // 🟡 EventSource 连接断了会自动重连（retry 字段可调，未设置用浏览器默认值）
    console.log("连接断了，浏览器自动重连中...");
};
```

### 这段代码在干什么（一行一行对）

1. 前端 `new EventSource("/chat?...")` 发 GET 请求，建立 SSE 连接（🟡 EventSource 规范）
2. 后端 `agent.stream_events(...)` 返回迭代器，`stream.messages` 逐 token 产（🟢 LangGraph API）
3. 后端 `for token in msg.text: yield f"data: {token}\n\n"` 把每个 token 包成 SSE event 推出去（🟡 SSE 格式：data: 字段 + 一对换行终止）
4. FastAPI `StreamingResponse(media_type="text/event-stream")` 用 HTTP chunked 把 yield 的内容流式推给前端（🟡 SSE MIME）
5. 前端 `es.onmessage` 每收到一个 event 就 `+= e.data`，逐字显示 = 打字机
6. 流完发 `data: [DONE]\n\n`，前端收到关连接

### 后端类比（你 Java 熟的）

| LangGraph / SSE 这边 | 你 Java 里对应的 |
|---|---|
| `agent.stream_events().stream.messages` | 一个 `Iterator<String>`，LLM 逐 token 吐 |
| `yield f"data: {token}\n\n"` | `SseEmitter.send(token)`，每个 token 包成 SSE event |
| `StreamingResponse(media_type="text/event-stream")` | Spring `SseEmitter` 设的 `Content-Type: text/event-stream` |
| 前端 `EventSource` | 浏览器内置 SSE 客户端（不用自己写 WebSocket 客户端） |
| 整条链路 | Java 用 `SseEmitter` 往前端推消息，数据源换成 LangGraph agent 迭代器 |

### SSE 协议速查（🟡 MDN 确认）

SSE event 格式：每行一个字段，`字段名: 值`，事件之间用**一对换行**（空行）分隔。

| 字段 | 作用 | 例子 |
|---|---|---|
| `data:` | 消息内容（多行 data: 会拼接，中间插换行） | `data: 你好\n\n` |
| `event:` | 事件类型名（前端 addEventListener 监听命名事件） | `event: token\ndata: 你\n\n` |
| `id:` | 事件 ID（设置 last event ID，重连续传用） | `id: 7\ndata: 你\n\n` |
| `retry:` | 重连等待时间（毫秒，连接断了浏览器等多久重连） | `retry: 3000\n\n` |
| `:` 开头 | 注释行（keep-alive 心跳用，防连接超时） | `: keepalive\n\n` |

MIME 类型：`text/event-stream`

---

## 第 1 层：断线重连

### 问题

用户聊天时网络抖动 / 刷新页面，SSE 连接断了。LLM 生成到一半，前端只收到一半 token。怎么办？

### SSE 自带的重连机制（🟡 MDN 确认）

1. **自动重连**：EventSource 连接断了，浏览器自动重连（`retry:` 字段可调等待时间，未设置用浏览器默认值）
2. **Last-Event-ID 头**：后端发 event 时带 `id: 序号`，浏览器记住最后收到的 id；重连时自动带 `Last-Event-ID: 序号` 请求头，后端读这个头从序号之后续发

### 伪代码（后端加 id + 读 Last-Event-ID）

```python
@app.get("/chat")
def chat(thread_id: str, message: str, last_event_id: str = None):
    def event_stream():
        # 🟡 读 Last-Event-ID 头，从断点续序号
        start_seq = int(last_event_id) + 1 if last_event_id else 0
        stream = agent.stream_events(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": thread_id}},
            version="v3",
        )
        seq = start_seq
        for msg in stream.messages:
            for token in msg.text:
                # 🟡 SSE: 带 id 字段，浏览器记住，重连时回传 Last-Event-ID
                yield f"id: {seq}\ndata: {token}\n\n"
                seq += 1
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

（FastAPI 把 `Last-Event-ID` 请求头映射成参数 `last_event_id`，🟡 通用 HTTP 头处理）

### 🔴 LangGraph 的坑（面试区分点，标"待核"）

**问题**：上面只续了"序号"，但 LangGraph 的 `stream.messages` 迭代器断了之后**没法从中间接着迭代**。重连重新调 `agent.stream_events`，agent 会从头跑：

- 🟢 官方机制（grep 确认 doc-graph-api.txt）：节点失败/中断后 resume，**受影响的节点从头重跑**（原文："the affected node runs again from the start of its function"）
- 🔴 推理：所以流式断在 LLM 生成中间，重连后 LLM 节点重跑 = 重新生成。之前发的 token 前端已有，重新生成的内容可能跟之前不一样（LLM 非确定性），会重复/错乱
- 🟢 checkpointer 保的是 **super-step 边界 state**（节点完成后的快照），**不保 token 流式进度**

### 生产常见做法（🔴 推理，非官方明确）

1. **简单方案**：断了就重新生成。重连时前端清空已显示内容，后端重新 stream。费 token 但简单。Last-Event-ID 在这场景没用（重新生成内容不一样）
2. **靠 checkpointer**：重连用同一个 thread_id，agent 状态从 checkpointer 拉回。如果断点正好在节点边界（上一个节点跑完、下一个没开始），重连能从 checkpoint 续，不重跑。断在节点中间还是会重跑该节点
3. **严谨方案**：每个 token event 带 id + 后端记"id->token"映射，重连按 Last-Event-ID 精确补发。但 token 量大、存储成本高，且 LLM 重生成内容不一定一致，一般不做

**面试口径**："SSE 自带自动重连 + Last-Event-ID（🟡 通用规范）；但 LangGraph 的 checkpointer 只保节点边界 state 不保 token 进度（🟢），所以 token 级断点续传要自己处理，生产上一般断了重新生成或靠 thread_id 从 checkpoint 续（🔴 我们的做法）"

### 后端类比

| SSE 重连 | 你 Java 里的 |
|---|---|
| EventSource 自动重连 | 浏览器帮你挂了 retry（Java HTTP 客户端得自己写） |
| Last-Event-ID 头 | 断点续传/分页带的 offset/cursor |
| checkpointer 保节点边界不保 token | 事务日志保的是事务提交点，不是事务中间状态 |

---

## 第 2 层：多实例会话亲和

### 问题

生产多实例部署（agent 服务跑 3 个实例 A/B/C）。用户第一次聊天打到实例 A，SSE 连接在 A 上。网络断了重连，负载均衡把请求打到实例 B。B 没有这个 SSE 连接的上下文，怎么办？

### 两个层次的问题

**层次 1：agent 状态（🟢 checkpointer 解决）**
- 用 PostgresSaver（🟢 生产推荐，生产文档讲过），state 存 Postgres 共享
- 重连打到 B，B 用同一个 thread_id 从 Postgres 拉回 state，能继续
- ⚠️ InMemorySaver 不行（state 在实例内存，多实例不共享）-- 🟢 生产文档问题 1 讲过

**层次 2：SSE 长连接本身（🟡 sticky session）**
- SSE 是长连接，断了重连是**新连接**，打到哪个实例是负载均衡决定的
- 即使 state 共享（PostgresSaver），重连打到新实例也要**重新建立 stream**（新实例重新 agent.stream_events 从 checkpoint 跑）
- sticky session（会话亲和）：负载均衡把同一会话粘到同一实例，重连还打到 A

### 伪代码（nginx sticky 配置，🟡 通用）

```nginx
upstream agent_backend {
    # 🟡 sticky cookie: 同一会话粘同一实例
    sticky cookie srv_id expires=1h domain=.example.com httponly;

    server 10.0.0.1:8000;  # 实例 A
    server 10.0.0.2:8000;  # 实例 B
    server 10.0.0.3:8000;  # 实例 C
}

server {
    location /chat {
        proxy_pass http://agent_backend;
        # 🟡 SSE 长连接: 关缓冲（第 4 层讲）、调长超时
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_set_header Connection "";
        proxy_http_version 1.1;
    }
}
```

### 🔴 sticky 能解决什么、不能解决什么（推理，标待核）

- ✅ sticky 让重连打到原实例，**如果原实例的 stream 迭代器还活着**（没超时没被回收），理论上能接着流。但 SSE 断了原实例的迭代器通常也断了（yield 被 GeneratorExit）
- 🔴 推理：sticky **主要价值是"会话一致性"**（同一会话同一实例，实例内存级缓存/连接池命中率高），**不是"避免重生成"**。避免重生成靠 checkpointer（节点边界续）
- 实际：PostgresSaver + sticky 是常见组合。sticky 优化性能/一致性，PostgresSaver 保状态不丢

### 后端类比

| 多实例 SSE | 你 Java 里的 |
|---|---|
| PostgresSaver 共享 state | Spring Session Redis（session 跨实例共享） |
| sticky session | nginx ip_hash / 网关层会话亲和 |
| 重连打到新实例重建 stream | WebSocket 重连打到新实例要重新握手 |

---

## 第 3 层：HITL 流式中断

### 问题

第 21 步讲过 HITL：agent 调工具前暂停，人工审核。流式版怎么配合？用户要看到 LLM 边说边生成，然后 agent 要调工具时暂停弹审核框。

### 🟢 官方机制（grep 确认 doc-interrupts.txt）

用 `stream_events(version="v3")`，有四个 typed projection 配合 HITL：

- `stream.messages`：LLM token 级（流 token 给前端）
- `stream.interrupted`：bool，run 是否因等输入而暂停（原文："stream.interrupted is True when the run pauses for input"）
- `stream.interrupts`：interrupt() 传入的 payload（要审核的内容，原文："contains the payloads passed to interrupt()"）
- `stream.output`：最终 state（await 它驱动 run 完成）

官方推荐（原文）："The recommended way to drive a graph that may interrupt is event streaming — it surfaces interrupts via stream.interrupts and stream.interrupted"

### 流程（关键：不是"边流边停"，是"流完 token 再检测暂停"）

1. 后端 stream_events，消费 `stream.messages` 把 token 流给前端（LLM 说"我来查下订单 ORD-001"）
2. LLM token 流完，agent 准备调工具前 `interrupt()` 暂停
3. 后端检查 `stream.interrupted == True`，把 `stream.interrupts`（工具调用详情）发给前端
4. 前端收到中断信号，弹审核框（展示要调的工具 + 参数）
5. 人工审核后，前端发**第二次请求**用 `Command(resume=...)` 恢复（第 21 步讲过的两次 HTTP）
6. 后端 resume 后继续 stream，流后续 token

### 伪代码

**后端（第一次：流 token + 检测中断）**：

```python
@app.get("/chat")
def chat(thread_id: str, message: str):
    def event_stream():
        stream = agent.stream_events(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": thread_id}},
            version="v3",
        )
        # 🟢 1. 流 token 给前端
        for msg in stream.messages:
            for token in msg.text:
                yield f"data: {token}\n\n"
        # 🟢 2. token 流完, 检查是否暂停等审核
        if stream.interrupted:
            # 🟢 stream.interrupts = interrupt() 的 payload (要审核的工具调用)
            import json
            yield f"event: interrupt\ndata: {json.dumps(stream.interrupts)}\n\n"
        else:
            yield "data: [DONE]\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**后端（第二次：审核后 resume）**：

```python
@app.post("/resume")
def resume(thread_id: str, decision: str):
    def event_stream():
        # 🟢 Command(resume=...) 恢复, 第 21 步讲过
        from langgraph.types import Command
        stream = agent.stream_events(
            Command(resume={"decisions": [{"type": decision}]}),
            config={"configurable": {"thread_id": thread_id}},
            version="v3",
        )
        for msg in stream.messages:
            for token in msg.text:
                yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**前端**：

```javascript
const es = new EventSource("/chat?thread_id=abc123&message=查订单ORD-001");

// 1. token 流: 逐字显示
es.onmessage = (e) => {
    if (e.data === "[DONE]") { es.close(); return; }
    document.getElementById("output").textContent += e.data;
};

// 2. 收到中断信号: 弹审核框
es.addEventListener("interrupt", (e) => {
    const payload = JSON.parse(e.data);   // 要审核的工具调用
    showReviewDialog(payload);             // 弹框展示工具名+参数
});

// 3. 审核后: 发第二次请求 resume
function approve() {
    const es2 = new EventSource("/resume?thread_id=abc123&decision=approve");
    es2.onmessage = (e) => {
        if (e.data === "[DONE]") { es2.close(); return; }
        document.getElementById("output").textContent += e.data;
    };
}
```

### 后端类比

| HITL 流式 | 你 Java 里的 |
|---|---|
| stream.messages 流 token | 正常 SSE 推消息 |
| stream.interrupted 检测暂停 | 工作流引擎（Activiti）流程节点等待人工审批 |
| event: interrupt 发审核信号 | 业务事件："需审批"推前端 |
| Command(resume) 第二次请求恢复 | Activiti task complete 推进流程 |
| 两次 HTTP（流 token + resume） | 审批流的"提交申请"+"审批通过"两次请求 |

---

## 第 4 层：反向代理缓冲

### 问题

后端 SSE 流得好好的，但前端收到的字是一坨一坨来的，不是逐字实时。为啥？nginx 默认 `proxy_buffering on`，把后端响应缓冲满一块再发给前端，SSE 的实时性没了。

### 🟡 通用 nginx 配置

SSE 要关缓冲 + 调长超时：

```nginx
location /chat {
    proxy_pass http://agent_backend;

    # 🟡 关键: 关缓冲, 否则 nginx 攒一块再发, SSE 不实时
    proxy_buffering off;
    proxy_cache off;

    # 🟡 SSE 长连接: 默认 proxy_read_timeout 60s 会超时断, 调长
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    # 🟡 HTTP/1.1 长连接 + 清 Connection 头
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    # 🟡 透传客户端 IP 等（可选）
    proxy_set_header X-Real-IP $remote_addr;
}
```

### 🟡 后端侧替代方案（响应头）

不想改 nginx 配置，后端在 SSE 响应里设 `X-Accel-Buffering: no` 头，nginx 收到这个头也不缓冲这个响应：

```python
return StreamingResponse(
    event_stream(),
    media_type="text/event-stream",
    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
)
```

### 为什么必须关缓冲（后端类比）

- nginx `proxy_buffering on` = 你 Java 里把响应先写到 `ByteArrayOutputStream` 攒满再 flush，前端看不到中间过程
- `proxy_buffering off` = 直接 `OutputStream` 边写边 flush，前端实时看到
- SSE 的打字机效果**依赖每次 yield 立即到达前端**，被缓冲就废了

### 生产坑

- **不关缓冲**：前端看到一坨一坨的字，不是打字机，体验崩（最常见踩坑）
- **不调 `proxy_read_timeout`**：SSE 长连接空闲超 60s 被 nginx 断（可发心跳 `: keepalive\n\n` 保活）
- **HTTP/1.0 不支持 chunked**：`proxy_http_version 1.1` 必须设
- **云厂商 LB（ALB/CLB）**：有的默认缓冲，要在控制台关或用 NLB（四层透传）

---

## 小结：4 层叠加后的完整生产链路

```
[前端 EventSource] --SSE--> [nginx: sticky + proxy_buffering off] --http--> [FastAPI 多实例]
                                                                            |
                                                                  agent.stream_events(version="v3")
                                                                  ├─ stream.messages  → 流 token
                                                                  ├─ stream.interrupted → 检测 HITL 暂停
                                                                  ├─ stream.interrupts  → 审核 payload
                                                                  └─ stream.output      → 最终 state
                                                                            |
                                                                  checkpointer (PostgresSaver)
                                                                  ├─ thread_id 共享 state (多实例)
                                                                  └─ 节点边界存 checkpoint (断线续)
```

- 🟢 官方明确：stream_events 四个 projection、checkpointer 存节点边界、thread_id、Command(resume)
- 🟡 通用 web：SSE 协议、EventSource 自动重连/Last-Event-ID、nginx sticky/proxy_buffering、X-Accel-Buffering
- 🔴 推理待核：token 级断点续传非开箱即用、sticky 不解决重生成、断线重连生产做法
