"use client";

import {
  BookOpenCheck,
  CircleAlert,
  CircleCheck,
  CircleOff,
  Clock3,
  ExternalLink,
  LoaderCircle,
  RotateCcw,
  SearchCheck,
  ShieldAlert,
} from "lucide-react";

import type { ProductTask } from "@/lib/schemas/product-api";

interface DeepResearchProjectionProps {
  task: ProductTask;
  onRetry?: () => void;
  retrying?: boolean;
}

const statusCopy = {
  queued: ["研究已排队", "等待后台执行资源。"],
  running: ["深度研究进行中", "后台 Agent 正在检索、核验并综合来源。"],
  waiting_human: ["等待人工确认", "研究流程已暂停，等待审核决定。"],
  succeeded: ["深度研究已完成", "报告与引用来源已保存。"],
  blocked: ["研究已阻断", "当前证据或审核门禁未允许生成报告。"],
  failed: ["深度研究失败", "系统未生成可交付报告。"],
  cancelled: ["深度研究已取消", "后台执行已停止。"],
} as const;

export function DeepResearchProjection({
  task,
  onRetry,
  retrying = false,
}: DeepResearchProjectionProps) {
  const artifact = task.deep_research_artifact;
  const [statusLabel, statusDescription] = statusCopy[task.status];

  return (
    <div className="projection-stack" data-testid="deep-research-projection">
      <section className={`status-panel tone-${statusTone(task.status)}`} data-testid="task-status" aria-live="polite">
        <span className="status-icon" aria-hidden="true">{statusIcon(task.status)}</span>
        <div>
          <div className="status-title-row">
            <h2>{statusLabel}</h2>
            <span>{task.symbol.replace("-USDT-SWAP", "")} · {task.horizon}</span>
          </div>
          <p>{statusDescription}</p>
        </div>
      </section>

      {task.errors.length > 0 ? (
        <section className="failure-panel" role="alert">
          <div className="failure-heading">
            <CircleAlert size={21} aria-hidden="true" />
            <div><h2>研究报告未生成</h2></div>
          </div>
          <p>{task.errors[0]?.message}</p>
          <details className="failure-diagnostics-disclosure">
            <summary>查看失败诊断</summary>
            <dl className="failure-diagnostics" aria-label="失败诊断">
              <div><dt>关联 ID</dt><dd>{task.correlation_id}</dd></div>
              <div><dt>错误代码</dt><dd>{task.errors[0]?.code}</dd></div>
              {task.errors[0]?.provider ? (
                <div><dt>Provider</dt><dd>{task.errors[0].provider}</dd></div>
              ) : null}
              {task.errors[0]?.error_type ? (
                <div><dt>错误类型</dt><dd>{task.errors[0].error_type}</dd></div>
              ) : null}
            </dl>
          </details>
          {task.errors[0]?.retryable && onRetry ? (
            <button className="retry-button" type="button" onClick={onRetry} disabled={retrying}>
              <RotateCcw size={17} aria-hidden="true" />
              {retrying ? "正在重新提交" : "重新研究"}
            </button>
          ) : null}
        </section>
      ) : null}

      {artifact ? (
        <article className="deep-research-report" aria-labelledby="deep-research-report-title">
          <header className="deep-research-report-header">
            <span aria-hidden="true"><BookOpenCheck size={22} /></span>
            <div>
              <p className="section-kicker">Deep Research Report</p>
              <h2 id="deep-research-report-title">研究结论</h2>
            </div>
            <span className="research-harness-label">
              {artifact.harness_mode === "deepagents" ? "Deep Agents" : "LangChain"}
            </span>
          </header>

          <section
            className="deep-research-coverage"
            data-status={artifact.search_coverage.status}
            aria-labelledby="deep-research-coverage-title"
          >
            <span aria-hidden="true">
              {artifact.search_coverage.status === "complete"
                ? <SearchCheck size={19} />
                : <CircleAlert size={19} />}
            </span>
            <div>
              <h3 id="deep-research-coverage-title">检索覆盖</h3>
              <p>
                {artifact.search_coverage.successful_queries} / {artifact.search_coverage.attempted_queries}
                {" "}条查询返回了可验证来源
              </p>
              {artifact.search_coverage.failed_queries.length > 0 ? (
                <details>
                  <summary>查看未完成查询</summary>
                  <ul>
                    {artifact.search_coverage.failed_queries.map((failure) => (
                      <li key={failure.query_index}>
                        查询 {failure.query_index}：{formatSearchErrorKind(failure.error_kind)}
                        {failure.attempt ? `（第 ${failure.attempt} 次）` : ""}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
            <strong>{artifact.search_coverage.status === "complete" ? "完整" : "部分"}</strong>
          </section>

          <p className="deep-research-summary">{artifact.report.executive_summary}</p>

          <div className="deep-research-sections">
            {artifact.report.sections.map((section, sectionIndex) => (
              <section key={`${section.title}:${sectionIndex}`}>
                <div className="deep-research-section-heading">
                  <span>{String(sectionIndex + 1).padStart(2, "0")}</span>
                  <div>
                    <h3>{section.title}</h3>
                    <p>{section.summary}</p>
                  </div>
                </div>
                <ul className="deep-research-findings">
                  {section.findings.map((finding, findingIndex) => (
                    <li key={`${finding.claim}:${findingIndex}`}>
                      <p>{finding.claim}</p>
                      <span className="research-citations" aria-label="引用来源">
                        {finding.source_indexes.map((sourceIndex) => {
                          const source = artifact.sources[sourceIndex - 1];
                          return source ? (
                            <a
                              key={sourceIndex}
                              href={source.evidence.final_url}
                              target="_blank"
                              rel="noreferrer"
                              aria-label={`来源 ${sourceIndex}：${source.evidence.title}`}
                            >
                              [{sourceIndex}]
                            </a>
                          ) : null;
                        })}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>

          {artifact.report.risk_notes.length > 0 || artifact.report.evidence_gaps.length > 0 ? (
            <div className="deep-research-caveats">
              {artifact.report.risk_notes.length > 0 ? (
                <section>
                  <h3><ShieldAlert size={17} aria-hidden="true" />风险提示</h3>
                  <ul>{artifact.report.risk_notes.map((note) => <li key={note}>{note}</li>)}</ul>
                </section>
              ) : null}
              {artifact.report.evidence_gaps.length > 0 ? (
                <section>
                  <h3><CircleAlert size={17} aria-hidden="true" />证据缺口</h3>
                  <ul>{artifact.report.evidence_gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
                </section>
              ) : null}
            </div>
          ) : null}

          <section className="deep-research-sources" aria-labelledby="deep-research-sources-title">
            <div className="deep-research-sources-heading">
              <SearchCheck size={20} aria-hidden="true" />
              <div>
                <h3 id="deep-research-sources-title">可验证来源</h3>
                <p>{artifact.sources.length} 条来源已绑定到本报告。</p>
              </div>
            </div>
            <ol>
              {artifact.sources.map((source) => (
                <li key={source.index}>
                  <span>{source.index}</span>
                  <div>
                    <a href={source.evidence.final_url} target="_blank" rel="noreferrer">
                      {source.evidence.title}<ExternalLink size={14} aria-hidden="true" />
                    </a>
                    <p>{source.evidence.excerpt}</p>
                    <small>{source.evidence.source} · {formatSourceTime(source.evidence.published_at ?? source.evidence.fetched_at)}</small>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </article>
      ) : null}
    </div>
  );
}

function statusTone(status: ProductTask["status"]) {
  if (status === "succeeded") return "positive";
  if (status === "queued" || status === "running") return "active";
  if (status === "blocked") return "blocked";
  if (status === "waiting_human") return "warning";
  return "danger";
}

function statusIcon(status: ProductTask["status"]) {
  const common = { size: 22, strokeWidth: 1.8 };
  if (status === "queued") return <Clock3 {...common} />;
  if (status === "running") return <LoaderCircle {...common} className="spinning-icon" />;
  if (status === "waiting_human" || status === "blocked") return <ShieldAlert {...common} />;
  if (status === "succeeded") return <CircleCheck {...common} />;
  if (status === "cancelled") return <CircleOff {...common} />;
  return <CircleAlert {...common} />;
}

function formatSourceTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatSearchErrorKind(
  errorKind: NonNullable<ProductTask["deep_research_artifact"]>["search_coverage"]["failed_queries"][number]["error_kind"],
) {
  const labels = {
    timeout: "检索超时",
    server_error: "Provider 服务异常",
    rate_limited: "Provider 请求受限",
    connection_error: "Provider 连接失败",
    unverified_server_tool_call: "未获得可验证工具结果",
    missing_provider_citation: "Provider 未返回引用",
    missing_verified_evidence: "未获得可验证来源",
    invalid_provider_response: "Provider 响应无效",
    provider_error: "Provider 检索失败",
  } as const;
  return labels[errorKind];
}
