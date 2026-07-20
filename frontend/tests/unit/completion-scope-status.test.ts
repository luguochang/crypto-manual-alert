import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  CompletionScopeStatus,
  completionScopeStatusView,
} from "../../src/features/status/completion-scope-status";

describe("Product observability completion status", () => {
  it.each([
    ["not_enabled", "运行记录未启用", "本次运行未启用诊断记录。"],
    ["pending", "运行记录同步中", "分析仍在继续，运行记录将在完成后补齐。"],
    ["degraded", "运行记录不完整", "不影响本次分析结果。"],
    ["complete", "运行记录已保存", "本次运行的诊断记录已同步，可用于回看和排查。"],
  ] as const)("maps %s to product-safe copy", (status, title, description) => {
    const view = completionScopeStatusView(status);

    expect(view.title).toBe(title);
    expect(view.description).toContain(description);
    expect(view.description).not.toMatch(/LangSmith|Langfuse|SDK|trace|correlation|raw error/i);
  });

  it("renders one accessible status region with the typed API status", () => {
    const html = renderToStaticMarkup(createElement(CompletionScopeStatus, {
      status: "degraded",
    }));

    expect(html).toContain('role="status"');
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain('aria-atomic="true"');
    expect(html).toContain('data-testid="observability-status"');
    expect(html).toContain('data-status="degraded"');
    expect(html).toContain("不影响本次分析结果");
    expect(html).not.toMatch(/LangSmith|Langfuse|SDK|trace_id|correlation_id|raw error/i);
  });

  it("renders delivery warnings as visible product text", () => {
    const html = renderToStaticMarkup(createElement(CompletionScopeStatus, {
      status: "degraded",
      message: "分析结果已保存，但部分诊断记录未能同步。",
    }));

    expect(html).toContain('data-testid="completion-warning"');
    expect(html).toContain("交付未完成");
    expect(html).toContain("部分诊断记录未能同步");
    expect(html).not.toContain("completion-warning-compat");
  });
});
