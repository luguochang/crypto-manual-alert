"use client";

import { CircleCheck, CircleOff, LoaderCircle, TriangleAlert } from "lucide-react";

import type { ObservabilityCompletionStatus } from "@/lib/schemas/product-api";

type CompletionScopeStatusProps = {
  status: ObservabilityCompletionStatus;
  message?: string | null;
};

type CompletionScopeStatusView = {
  title: string;
  description: string;
  tone: "neutral" | "pending" | "warning" | "success";
};

const statusViews: Record<ObservabilityCompletionStatus, CompletionScopeStatusView> = {
  not_enabled: {
    title: "运行记录未启用",
    description: "本次运行未启用诊断记录。",
    tone: "neutral",
  },
  pending: {
    title: "运行记录同步中",
    description: "分析仍在继续，运行记录将在完成后补齐。",
    tone: "pending",
  },
  degraded: {
    title: "运行记录不完整",
    description: "分析结果已保存，但部分诊断记录未能同步；不影响本次分析结果。",
    tone: "warning",
  },
  complete: {
    title: "运行记录已保存",
    description: "本次运行的诊断记录已同步，可用于回看和排查。",
    tone: "success",
  },
};

export function completionScopeStatusView(
  status: ObservabilityCompletionStatus,
): CompletionScopeStatusView {
  return statusViews[status];
}

export function CompletionScopeStatus({
  status,
  message = null,
}: CompletionScopeStatusProps) {
  const view = completionScopeStatusView(status);

  return (
    <section
      className={`observability-status tone-${view.tone}`}
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-testid="observability-status"
      data-status={status}
    >
      <span className="observability-status-icon" aria-hidden="true">
        {statusIcon(status)}
      </span>
      <div>
        <h2 {...(message !== null ? { "data-testid": "completion-warning" } : {})}>
          {message !== null ? "交付未完成" : view.title}
        </h2>
        <p>{message ?? view.description}</p>
      </div>
    </section>
  );
}

function statusIcon(status: ObservabilityCompletionStatus) {
  const common = { size: 20, strokeWidth: 1.8 };

  switch (status) {
    case "pending":
      return <LoaderCircle {...common} className="spinning-icon" />;
    case "degraded":
      return <TriangleAlert {...common} />;
    case "complete":
      return <CircleCheck {...common} />;
    case "not_enabled":
      return <CircleOff {...common} />;
  }
}
