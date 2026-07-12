"use client";

import { useStream } from "@langchain/react";
import { useState, type FormEvent } from "react";
import type { AnalysisState, InterruptInfo } from "@/types";

/**
 * Phase 0 骨架验证页面
 *
 * 验证目标：
 * 1. useStream 能连接 Agent Server (localhost:2024)
 * 2. stream.messages 展示 Agent 消息流
 * 3. stream.values 展示 Graph State 快照
 * 4. stream.interrupts 检测 HITL 中断
 * 5. stream.respond 恢复中断
 * 6. stream.isLoading 加载状态
 * 7. stream.error 错误状态
 *
 * useStream 是唯一状态源，不引入 Redux/Zustand
 */
export default function TestPage() {
  // 输入框内容
  const [input, setInput] = useState("");
  // 中断恢复输入内容
  const [resumeInput, setResumeInput] = useState("");
  // Thread ID（由 Agent Server 分配）
  const [threadId, setThreadId] = useState<string | undefined>();

  // useStream - 唯一状态源，连接 Agent Server
  const stream = useStream<AnalysisState>({
    apiUrl: "http://localhost:2024",
    assistantId: "agent",
    threadId: threadId,
    onThreadId: (id: string) => setThreadId(id),
    // 断线重连：页面刷新后自动恢复
    reconnectOnMount: true,
  } as any);

  // 提交输入 - 触发 Agent 执行
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    stream.submit({ messages: [{ role: "user", content: input.trim() }] } as any);
    setInput("");
  };

  // 恢复中断 - 从 HITL interrupt 中恢复执行
  const handleResume = (e: FormEvent) => {
    e.preventDefault();
    const response = resumeInput.trim() || '{"action": "approve"}';
    stream.respond({ action: "approve", raw: response });
    setResumeInput("");
  };

  // 解析中断信息
  const interrupts: InterruptInfo[] = stream.interrupts ?? [];
  const hasInterrupt = interrupts.length > 0;
  const currentInterrupt = interrupts[0];

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--color-bg-primary)",
        color: "var(--color-text-primary)",
      }}
    >
      {/* 页面容器 - 单栏布局，响应式 */}
      <div
        style={{
          maxWidth: "800px",
          margin: "0 auto",
          padding: "2rem 1.5rem",
        }}
      >
        {/* 标题 */}
        <header style={{ marginBottom: "2rem" }}>
          <h1
            style={{
              fontSize: "1.75rem",
              fontWeight: 700,
              color: "var(--color-brand)",
              marginBottom: "0.5rem",
            }}
          >
            Crypto Alert V2 - Phase 0 骨架验证
          </h1>
          <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem" }}>
            验证 Agent Server 连接、useStream 状态流和 HITL 中断恢复
          </p>
        </header>

        {/* 状态栏 - Thread ID、连接状态、加载状态 */}
        <StatusBar
          threadId={threadId}
          isLoading={stream.isLoading}
          error={stream.error}
        />

        {/* 错误状态展示 */}
        {!!stream.error && (
          <ErrorBanner error={stream.error} />
        )}

        {/* HITL 中断检测和恢复 */}
        {hasInterrupt && (
          <InterruptPanel
            interrupt={currentInterrupt}
            resumeInput={resumeInput}
            setResumeInput={setResumeInput}
            onResume={handleResume}
          />
        )}

        {/* 消息列表展示 - stream.messages */}
        <MessageList messages={stream.messages} />

        {/* 输入框和提交按钮 - stream.submit */}
        <InputBar
          input={input}
          setInput={setInput}
          onSubmit={handleSubmit}
          isLoading={stream.isLoading}
          onStop={() => stream.stop()}
        />

        {/* Graph State 快照展示 - stream.values */}
        <StateSnapshot values={stream.values} />
      </div>
    </div>
  );
}

/* ============================================================
 * 子组件：状态栏（Thread ID、加载状态、停止按钮）
 * ============================================================ */
function StatusBar({
  threadId,
  isLoading,
  error,
}: {
  threadId: string | undefined;
  isLoading: boolean;
  error: unknown;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "1rem",
        flexWrap: "wrap",
        padding: "0.75rem 1rem",
        backgroundColor: "var(--color-bg-secondary)",
        border: "1px solid var(--color-border)",
        borderRadius: "8px",
        marginBottom: "1rem",
        fontSize: "0.875rem",
      }}
    >
      {/* Thread ID */}
      <div>
        <span style={{ color: "var(--color-text-muted)" }}>Thread ID: </span>
        <code
          style={{
            color: "var(--color-brand-light)",
            fontFamily: "monospace",
          }}
        >
          {threadId ?? "(未创建)"}
        </code>
      </div>

      {/* 加载状态指示器 */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
        <span
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            backgroundColor: isLoading
              ? "var(--color-brand)"
              : error
                ? "var(--color-error)"
                : "var(--color-success)",
            animation: isLoading ? "pulse 1.5s infinite" : "none",
          }}
        />
        <span style={{ color: "var(--color-text-secondary)" }}>
          {isLoading ? "执行中..." : error ? "连接错误" : "已就绪"}
        </span>
      </div>

      {/* Agent Server 地址 */}
      <div style={{ marginLeft: "auto" }}>
        <span style={{ color: "var(--color-text-muted)" }}>Agent Server: </span>
        <code style={{ color: "var(--color-text-secondary)" }}>
          localhost:2024
        </code>
      </div>

      {/* 内联 pulse 动画 */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}

/* ============================================================
 * 子组件：错误横幅
 * ============================================================ */
function ErrorBanner({ error }: { error: unknown }) {
  const errorMsg =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : JSON.stringify(error, null, 2);

  return (
    <div
      style={{
        backgroundColor: "rgba(239, 68, 68, 0.1)",
        border: "1px solid var(--color-error)",
        borderRadius: "8px",
        padding: "1rem",
        marginBottom: "1rem",
      }}
    >
      <div
        style={{
          color: "var(--color-error)",
          fontWeight: 600,
          marginBottom: "0.5rem",
          fontSize: "0.875rem",
        }}
      >
        连接错误
      </div>
      <pre
        className="json-block"
        style={{
          color: "var(--color-text-secondary)",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          margin: 0,
        }}
      >
        {errorMsg}
      </pre>
      <p
        style={{
          color: "var(--color-text-muted)",
          fontSize: "0.75rem",
          marginTop: "0.5rem",
        }}
      >
        请确认 Agent Server 已启动：langgraph dev（端口 2024）
      </p>
    </div>
  );
}

/* ============================================================
 * 子组件：HITL 中断面板（中断检测 + 恢复按钮）
 * ============================================================ */
function InterruptPanel({
  interrupt,
  resumeInput,
  setResumeInput,
  onResume,
}: {
  interrupt: InterruptInfo;
  resumeInput: string;
  setResumeInput: (v: string) => void;
  onResume: (e: FormEvent) => void;
}) {
  return (
    <div
      style={{
        backgroundColor: "rgba(245, 158, 11, 0.1)",
        border: "1px solid var(--color-brand)",
        borderRadius: "8px",
        padding: "1.25rem",
        marginBottom: "1rem",
      }}
    >
      {/* 中断标题 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          marginBottom: "0.75rem",
        }}
      >
        <span
          style={{
            fontSize: "1.125rem",
          }}
        >
          ⏸
        </span>
        <h3
          style={{
            fontSize: "1rem",
            fontWeight: 600,
            color: "var(--color-brand)",
            margin: 0,
          }}
        >
          HITL 中断 - 等待人工确认
        </h3>
      </div>

      {/* 中断数据展示 */}
      <div
        style={{
          backgroundColor: "var(--color-bg-primary)",
          borderRadius: "6px",
          padding: "0.75rem",
          marginBottom: "1rem",
        }}
      >
        <div
          style={{
            color: "var(--color-text-muted)",
            fontSize: "0.75rem",
            marginBottom: "0.375rem",
          }}
        >
          中断类型: {interrupt.type ?? "unknown"}
        </div>
        <pre
          className="json-block"
          style={{
            color: "var(--color-text-secondary)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
            maxHeight: "200px",
            overflowY: "auto",
          }}
        >
          {JSON.stringify(interrupt.value ?? interrupt, null, 2)}
        </pre>
      </div>

      {/* 恢复输入和按钮 - stream.respond */}
      <form onSubmit={onResume} style={{ display: "flex", gap: "0.5rem" }}>
        <input
          type="text"
          value={resumeInput}
          onChange={(e) => setResumeInput(e.target.value)}
          placeholder='恢复响应（默认 {"action": "approve"}）'
          style={{
            flex: 1,
            padding: "0.5rem 0.75rem",
            backgroundColor: "var(--color-bg-primary)",
            border: "1px solid var(--color-border-light)",
            borderRadius: "6px",
            color: "var(--color-text-primary)",
            fontSize: "0.875rem",
            outline: "none",
          }}
        />
        <button
          type="submit"
          style={{
            padding: "0.5rem 1.25rem",
            backgroundColor: "var(--color-brand)",
            color: "#0f172a",
            border: "none",
            borderRadius: "6px",
            fontWeight: 600,
            fontSize: "0.875rem",
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          恢复执行
        </button>
      </form>
    </div>
  );
}

/* ============================================================
 * 子组件：消息列表（stream.messages）
 * ============================================================ */
function MessageList({ messages }: { messages: any[] }) {
  return (
    <section style={{ marginBottom: "1rem" }}>
      <h2
        style={{
          fontSize: "0.875rem",
          fontWeight: 600,
          color: "var(--color-text-muted)",
          marginBottom: "0.5rem",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        消息流 ({messages.length})
      </h2>

      {messages.length === 0 ? (
        <div
          style={{
            padding: "2rem",
            textAlign: "center",
            color: "var(--color-text-muted)",
            backgroundColor: "var(--color-bg-secondary)",
            border: "1px solid var(--color-border)",
            borderRadius: "8px",
            fontSize: "0.875rem",
          }}
        >
          暂无消息。输入内容并提交以开始与 Agent 交互。
        </div>
      ) : (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
            maxHeight: "400px",
            overflowY: "auto",
          }}
        >
          {messages.map((msg, idx) => (
            <MessageItem key={msg.id ?? idx} message={msg} />
          ))}
        </div>
      )}
    </section>
  );
}

/* ============================================================
 * 子组件：单条消息
 * ============================================================ */
function MessageItem({ message }: { message: any }) {
  // 提取角色和内容
  const role = message.role ?? message.type ?? "unknown";
  const content =
    typeof message.content === "string"
      ? message.content
      : Array.isArray(message.content)
        ? message.content
            .map((c: any) =>
              typeof c === "string" ? c : c.text ?? JSON.stringify(c)
            )
            .join("")
        : JSON.stringify(message.content);

  // 角色对应的样式
  const isHuman = role === "human" || role === "user";
  const isAI = role === "ai" || role === "assistant";
  const isTool = role === "tool";
  const isSystem = role === "system";

  const roleLabel = isHuman
    ? "用户"
    : isAI
      ? "Agent"
      : isTool
        ? "工具"
        : isSystem
          ? "系统"
          : role;

  const roleColor = isHuman
    ? "var(--color-info)"
    : isAI
      ? "var(--color-brand)"
      : isTool
        ? "var(--color-success)"
        : "var(--color-text-muted)";

  return (
    <div
      style={{
        padding: "0.625rem 0.875rem",
        backgroundColor: "var(--color-bg-secondary)",
        border: "1px solid var(--color-border)",
        borderRadius: "8px",
        borderLeft: `3px solid ${roleColor}`,
      }}
    >
      {/* 角色标签 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          marginBottom: content ? "0.375rem" : 0,
        }}
      >
        <span
          style={{
            fontSize: "0.75rem",
            fontWeight: 600,
            color: roleColor,
          }}
        >
          {roleLabel}
        </span>
        {/* 工具调用标记 */}
        {message.tool_calls && message.tool_calls.length > 0 && (
          <span
            style={{
              fontSize: "0.7rem",
              color: "var(--color-text-muted)",
              backgroundColor: "var(--color-bg-tertiary)",
              padding: "0.125rem 0.375rem",
              borderRadius: "4px",
            }}
          >
            {message.tool_calls.length} 个工具调用
          </span>
        )}
      </div>
      {/* 消息内容 */}
      {content && (
        <div
          style={{
            fontSize: "0.875rem",
            color: "var(--color-text-primary)",
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {content}
        </div>
      )}
      {/* 工具调用详情 */}
      {message.tool_calls && message.tool_calls.length > 0 && (
        <div style={{ marginTop: "0.375rem" }}>
          {message.tool_calls.map((tc: any, i: number) => (
            <div
              key={tc.id ?? i}
              style={{
                fontSize: "0.75rem",
                color: "var(--color-text-secondary)",
                fontFamily: "monospace",
                marginTop: "0.25rem",
              }}
            >
              {"-> "}{tc.name}({JSON.stringify(tc.args)})
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ============================================================
 * 子组件：输入栏（提交按钮 + 停止按钮）
 * ============================================================ */
function InputBar({
  input,
  setInput,
  onSubmit,
  isLoading,
  onStop,
}: {
  input: string;
  setInput: (v: string) => void;
  onSubmit: (e: FormEvent) => void;
  isLoading: boolean;
  onStop: () => void;
}) {
  return (
    <form
      onSubmit={onSubmit}
      style={{
        display: "flex",
        gap: "0.5rem",
        marginBottom: "1.5rem",
      }}
    >
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="输入消息内容..."
        disabled={isLoading}
        style={{
          flex: 1,
          padding: "0.625rem 0.875rem",
          backgroundColor: "var(--color-bg-secondary)",
          border: "1px solid var(--color-border-light)",
          borderRadius: "8px",
          color: "var(--color-text-primary)",
          fontSize: "0.875rem",
          outline: "none",
          opacity: isLoading ? 0.6 : 1,
        }}
      />
      <button
        type="submit"
        disabled={isLoading || !input.trim()}
        style={{
          padding: "0.625rem 1.5rem",
          backgroundColor: "var(--color-brand)",
          color: "#0f172a",
          border: "none",
          borderRadius: "8px",
          fontWeight: 600,
          fontSize: "0.875rem",
          cursor: isLoading || !input.trim() ? "not-allowed" : "pointer",
          opacity: isLoading || !input.trim() ? 0.5 : 1,
          whiteSpace: "nowrap",
        }}
      >
        提交
      </button>
      {isLoading && (
        <button
          type="button"
          onClick={onStop}
          style={{
            padding: "0.625rem 1rem",
            backgroundColor: "var(--color-bg-tertiary)",
            color: "var(--color-text-primary)",
            border: "1px solid var(--color-border-light)",
            borderRadius: "8px",
            fontWeight: 500,
            fontSize: "0.875rem",
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          停止
        </button>
      )}
    </form>
  );
}

/* ============================================================
 * 子组件：Graph State 快照（stream.values 的 JSON）
 * ============================================================ */
function StateSnapshot({ values }: { values: AnalysisState | undefined }) {
  const hasValues = values && Object.keys(values).length > 0;

  return (
    <section>
      <h2
        style={{
          fontSize: "0.875rem",
          fontWeight: 600,
          color: "var(--color-text-muted)",
          marginBottom: "0.5rem",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        Graph State 快照
      </h2>
      <div
        style={{
          backgroundColor: "var(--color-bg-secondary)",
          border: "1px solid var(--color-border)",
          borderRadius: "8px",
          padding: "1rem",
          maxHeight: "300px",
          overflowY: "auto",
        }}
      >
        {hasValues ? (
          <pre
            className="json-block"
            style={{
              color: "var(--color-text-secondary)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              margin: 0,
            }}
          >
            {JSON.stringify(values, null, 2)}
          </pre>
        ) : (
          <p
            style={{
              color: "var(--color-text-muted)",
              fontSize: "0.875rem",
              margin: 0,
              textAlign: "center",
              padding: "1rem",
            }}
          >
            尚无 Graph State 数据。提交消息后此处将显示最新状态快照。
          </p>
        )}
      </div>
    </section>
  );
}
