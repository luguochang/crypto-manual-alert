"use client";

import {
  ArrowLeft,
  BookOpenCheck,
  Check,
  CircleAlert,
  CirclePlus,
  CircleX,
  ExternalLink,
  FilePenLine,
  RotateCcw,
  Trash2,
} from "lucide-react";
import {
  FormEvent,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  ReviewStateBadge,
  ReviewStateNotice,
  resolveReviewDeadlineHint,
  resolveReviewInteractionState,
  resolveReviewSourceReference,
  reviewActionLabel,
  type ReviewAction,
  type ReviewSubmissionPhase,
} from "@/features/work/human-review-panel";
import {
  deepResearchReportSchema,
  interruptResponseSchema,
  validateInterruptResponseForPayload,
  type DeepResearchPendingInterrupt,
  type DeepResearchReport,
  type DeepResearchReviewPayload,
  type InterruptResponse,
} from "@/lib/schemas/product-api";

import styles from "./deep-research-review-panel.module.css";

type ReviewMode = ReviewAction | null;

export type DeepResearchReportFormValues = {
  executiveSummary: string;
  sections: DeepResearchReport["sections"];
  riskNotes: string;
  evidenceGaps: string;
};

type DeepResearchReviewPanelProps = {
  interrupt: Pick<DeepResearchPendingInterrupt, "payload" | "status">;
  expiresAt: string | null;
  disabled?: boolean;
  phase?: ReviewSubmissionPhase;
  failureMessage?: string | null;
  decision?: InterruptResponse | null;
  deferSubmission?: boolean;
  announceSubmissionState?: boolean;
  showSubmissionNotice?: boolean;
  reviewPosition?: { index: number; total: number };
  onDecide: (response: InterruptResponse) => void;
};

export function deepResearchReviewItemIdentity(
  interrupt: Pick<DeepResearchPendingInterrupt, "payload">,
  position: { index: number; total: number },
): string {
  return [
    `审核项 ${position.index}/${position.total}`,
    interrupt.payload.symbol,
    interrupt.payload.horizon,
    `第 ${interrupt.payload.review_iteration} 轮`,
  ].join("，");
}

export function deepResearchEditValuesFromPayload(
  payload: DeepResearchReviewPayload,
): DeepResearchReportFormValues {
  return {
    executiveSummary: payload.artifact.report.executive_summary,
    sections: payload.artifact.report.sections.map((section) => ({
      ...section,
      findings: section.findings.map((finding) => ({
        ...finding,
        source_indexes: [...finding.source_indexes],
      })),
    })),
    riskNotes: payload.artifact.report.risk_notes.join("\n"),
    evidenceGaps: payload.artifact.report.evidence_gaps.join("\n"),
  };
}

export function buildDeepResearchEditResponse(
  values: DeepResearchReportFormValues,
  payload: DeepResearchReviewPayload,
  comment: string,
): InterruptResponse {
  const report = deepResearchReportSchema.parse({
    executive_summary: values.executiveSummary,
    sections: values.sections,
    risk_notes: splitList(values.riskNotes),
    evidence_gaps: splitList(values.evidenceGaps),
  });
  return validateInterruptResponseForPayload(payload, {
    action: "edit",
    comment: normalizedComment(comment),
    edits: { report },
  });
}

export function DeepResearchReviewPanel({
  interrupt,
  expiresAt,
  disabled = false,
  phase = "idle",
  failureMessage = null,
  decision = null,
  deferSubmission = false,
  announceSubmissionState = true,
  showSubmissionNotice = true,
  reviewPosition,
  onDecide,
}: DeepResearchReviewPanelProps) {
  const payload = interrupt.payload;
  const artifact = payload.artifact;
  const report = artifact.report;
  const generatedId = useId().replace(/:/g, "");
  const reviewTitleId = `research-hitl-review-${generatedId}`;
  const summaryId = `research-hitl-summary-${generatedId}`;
  const sectionsId = `research-hitl-sections-${generatedId}`;
  const sourcesId = `research-hitl-sources-${generatedId}`;
  const confirmationId = `research-hitl-confirmation-${generatedId}`;
  const confirmationTitleId = `research-hitl-confirmation-title-${generatedId}`;
  const editFormId = `research-hitl-edit-${generatedId}`;
  const editTitleId = `research-hitl-edit-title-${generatedId}`;
  const [mode, setMode] = useState<ReviewMode>(null);
  const [comment, setComment] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [now, setNow] = useState<number | null>(null);
  const [editValues, setEditValues] = useState<DeepResearchReportFormValues>(() =>
    deepResearchEditValuesFromPayload(payload)
  );
  const returnFocusTarget = useRef<HTMLButtonElement | null>(null);
  const returnFocusRequested = useRef(false);
  const confirmationHeading = useRef<HTMLHeadingElement | null>(null);
  const editHeading = useRef<HTMLHeadingElement | null>(null);
  const reviewIdentity = reviewPosition === undefined
    ? null
    : deepResearchReviewItemIdentity(interrupt, reviewPosition);
  const availableActions = useMemo(
    () => [...payload.allowed_actions],
    [payload.allowed_actions],
  );

  useEffect(() => {
    const initialTick = window.setTimeout(() => setNow(Date.now()), 0);
    if (expiresAt === null || interrupt.status === "responding") {
      return () => window.clearTimeout(initialTick);
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      window.clearTimeout(initialTick);
      window.clearInterval(timer);
    };
  }, [expiresAt, interrupt.status]);

  const interactionState = resolveReviewInteractionState(interrupt, phase);
  const actionDisabled = disabled
    || (interactionState !== "pending" && interactionState !== "network_error");
  const interactive = interactionState === "pending" || interactionState === "network_error";
  const deadline = useMemo(
    () => resolveReviewDeadlineHint(expiresAt, now),
    [expiresAt, now],
  );
  const activeMode = mode !== null && availableActions.includes(mode) ? mode : null;

  useEffect(() => {
    if (activeMode === "approve" || activeMode === "reject") {
      confirmationHeading.current?.focus();
      return;
    }
    if (activeMode === "edit") {
      editHeading.current?.focus();
      return;
    }
    if (returnFocusRequested.current) {
      returnFocusRequested.current = false;
      const target = returnFocusTarget.current;
      if (target?.isConnected && !target.disabled) target.focus();
    }
  }, [activeMode]);

  function saveResponse(response: InterruptResponse) {
    if (actionDisabled || !availableActions.includes(response.action)) return;
    const validated = validateInterruptResponseForPayload(payload, response);
    setFormError(null);
    onDecide(validated);
    if (deferSubmission) {
      returnFocusRequested.current = true;
      setMode(null);
    }
  }

  function submitDecision(action: "approve" | "reject") {
    if (!availableActions.includes(action)) return;
    saveResponse(interruptResponseSchema.parse({
      action,
      comment: normalizedComment(comment),
      edits: null,
    }));
  }

  function submitEdits(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!availableActions.includes("edit")) return;
    try {
      saveResponse(buildDeepResearchEditResponse(editValues, payload, comment));
    } catch (error) {
      setFormError(readableResearchEditError(error));
    }
  }

  function openReviewMode(nextMode: ReviewAction, trigger: HTMLButtonElement) {
    if (actionDisabled || !availableActions.includes(nextMode)) return;
    returnFocusTarget.current = trigger;
    returnFocusRequested.current = false;
    setMode(nextMode);
  }

  function returnToReviewActions() {
    returnFocusRequested.current = true;
    setMode(null);
  }

  return (
    <section className="hitl-review-panel" aria-labelledby={reviewTitleId}>
      <header className="hitl-review-header">
        <div className="hitl-review-heading">
          <span className="hitl-review-icon" aria-hidden="true"><BookOpenCheck size={20} /></span>
          <div>
            <p className="section-kicker">Deep Research review</p>
            <h2 id={reviewTitleId}>
              研究报告草稿待人工确认
              {reviewIdentity ? `：${reviewIdentity}` : ""}
            </h2>
          </div>
        </div>
        <ReviewStateBadge state={interactionState} deadline={deadline} announce={announceSubmissionState} />
      </header>

      <div className="hitl-review-summary" aria-label="待审核研究报告摘要">
        <ReviewMetric label="标的" value={payload.symbol.replace("-USDT-SWAP", "")} />
        <ReviewMetric label="周期" value={payload.horizon} />
        <ReviewMetric label="章节" value={`${report.sections.length} 节`} />
        <ReviewMetric label="来源" value={`${artifact.sources.length} 条`} />
        <ReviewMetric
          label="研究框架"
          value={artifact.harness_mode === "deepagents" ? "Deep Agents" : "LangChain"}
        />
      </div>

      <div className="hitl-review-detail-grid">
        <section className="hitl-review-detail" aria-labelledby={`${reviewTitleId} ${summaryId}`}>
          <h3 id={summaryId}>执行摘要</h3>
          <p>{report.executive_summary}</p>
          <dl className="hitl-review-notes">
            <ReviewList label="风险提示" items={report.risk_notes} empty="当前没有额外风险提示" />
            <ReviewList label="证据缺口" items={report.evidence_gaps} empty="当前没有声明证据缺口" />
          </dl>
        </section>
        <section className="hitl-review-detail" aria-labelledby={`${reviewTitleId} ${sectionsId}`}>
          <h3 id={sectionsId}>研究章节与引用</h3>
          <ol className="hitl-cause-list">
            {report.sections.map((section, index) => (
              <li key={`${index}-${section.title}`}>
                <strong>{section.title}</strong>
                <p>{section.summary}</p>
                <small>{section.findings.length} 条发现</small>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <section className="hitl-review-sources" aria-labelledby={`${reviewTitleId} ${sourcesId}`}>
        <div className="hitl-review-sources-heading">
          <h3 id={sourcesId}>只读来源目录</h3>
          <span>{artifact.sources.length} 条</span>
        </div>
        <ul>
          {artifact.sources.map((source) => {
            const reference = resolveReviewSourceReference(source.evidence.final_url);
            return (
              <li key={source.index}>
                {reference.href !== null ? (
                  <a href={reference.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">
                    <span>[{source.index}] {source.evidence.title}</span>
                    <ExternalLink size={16} aria-hidden="true" />
                  </a>
                ) : (
                  <span className="hitl-review-source-text">
                    <CircleAlert size={16} aria-hidden="true" />
                    <span>[{source.index}] {source.evidence.title}</span>
                    <small>来源地址无法安全打开</small>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      {interactive && deadline.locallyElapsed ? (
        <p className="hitl-local-deadline-notice" role="status">
          <CircleAlert size={16} aria-hidden="true" />
          本地倒计时已到，是否过期以 Product 服务响应为准。
        </p>
      ) : null}

      {showSubmissionNotice ? (
        <ReviewStateNotice state={interactionState} message={failureMessage} />
      ) : null}

      {interactive && deferSubmission && decision !== null ? (
        <p className="hitl-state-notice" role="note">
          已在本页选择{reviewActionLabel(decision.action)}，尚未提交到服务端；可继续修改。
        </p>
      ) : null}

      {interactive ? (
        <div
          className="hitl-review-actions"
          role="group"
          aria-label={reviewIdentity ? `${reviewIdentity}的研究审核决定` : "研究审核决定"}
        >
          {availableActions.includes("approve") ? (
            <button
              type="button"
              className="hitl-action-button is-approve"
              onClick={(event) => openReviewMode("approve", event.currentTarget)}
              disabled={actionDisabled}
              aria-expanded={activeMode === "approve"}
              aria-controls={confirmationId}
            >
              <Check size={17} aria-hidden="true" />批准
            </button>
          ) : null}
          {availableActions.includes("reject") ? (
            <button
              type="button"
              className="hitl-action-button is-reject"
              onClick={(event) => openReviewMode("reject", event.currentTarget)}
              disabled={actionDisabled}
              aria-expanded={activeMode === "reject"}
              aria-controls={confirmationId}
            >
              <CircleX size={17} aria-hidden="true" />拒绝
            </button>
          ) : null}
          {availableActions.includes("edit") ? (
            <button
              type="button"
              className="hitl-action-button is-edit"
              onClick={(event) => openReviewMode("edit", event.currentTarget)}
              disabled={actionDisabled}
              aria-expanded={activeMode === "edit"}
              aria-controls={editFormId}
            >
              <FilePenLine size={17} aria-hidden="true" />修改后重审
            </button>
          ) : null}
        </div>
      ) : null}

      {interactive && (activeMode === "approve" || activeMode === "reject") ? (
        <div
          id={confirmationId}
          className="hitl-confirmation"
          data-tone={activeMode === "approve" ? "positive" : "danger"}
          role="region"
          aria-labelledby={confirmationTitleId}
        >
          <div>
            <h3 id={confirmationTitleId} ref={confirmationHeading} tabIndex={-1}>
              {activeMode === "approve" ? "确认批准这份研究报告？" : "确认拒绝这份研究报告？"}
            </h3>
            <p>{activeMode === "approve"
              ? "批准后，Agent 将恢复运行并提交已审核的报告版本。"
              : "拒绝后，本次研究将进入明确的阻断终态，不会提交报告版本。"}</p>
          </div>
          <label className="hitl-comment-field">
            <span>审核备注（可选）</span>
            <textarea value={comment} onChange={(event) => setComment(event.target.value)} maxLength={1000} rows={2} />
          </label>
          <div className="hitl-confirmation-actions">
            <button type="button" className="hitl-secondary-button" onClick={returnToReviewActions}>
              <ArrowLeft size={16} aria-hidden="true" />返回
            </button>
            <button
              type="button"
              className={`hitl-action-button ${activeMode === "approve" ? "is-approve" : "is-reject"}`}
              onClick={() => submitDecision(activeMode)}
            >
              {activeMode === "approve" ? <Check size={17} aria-hidden="true" /> : <CircleX size={17} aria-hidden="true" />}
              {deferSubmission
                ? activeMode === "approve" ? "在本页选择批准" : "在本页选择拒绝"
                : activeMode === "approve" ? "确认批准" : "确认拒绝"}
            </button>
          </div>
        </div>
      ) : null}

      {interactive && activeMode === "edit" ? (
        <form id={editFormId} className="hitl-edit-form" aria-labelledby={editTitleId} onSubmit={submitEdits}>
          <div className="hitl-edit-heading">
            <div>
              <h3 id={editTitleId} ref={editHeading} tabIndex={-1}>修改研究报告</h3>
              <p>只修改报告内容；提交后进入下一轮人工审核，来源与执行审计保持不变。</p>
            </div>
            <button type="button" className="hitl-secondary-button" onClick={returnToReviewActions}>
              <ArrowLeft size={16} aria-hidden="true" />返回
            </button>
          </div>

          <div className="hitl-edit-grid">
            <label className="is-wide">
              <span>执行摘要</span>
              <textarea
                rows={5}
                minLength={1}
                maxLength={6000}
                required
                value={editValues.executiveSummary}
                onChange={(event) => updateTopLevel("executiveSummary", event.target.value)}
              />
            </label>
          </div>

          {editValues.sections.map((section, sectionIndex) => (
            <section className={`hitl-review-detail ${styles.editorSection}`} aria-label={`研究章节 ${sectionIndex + 1}`} key={sectionIndex}>
              <div className="hitl-edit-heading">
                <div><h3>章节 {sectionIndex + 1}</h3></div>
                <button
                  type="button"
                  className="hitl-secondary-button"
                  title="删除章节"
                  aria-label={`删除研究章节 ${sectionIndex + 1}`}
                  disabled={editValues.sections.length === 1}
                  onClick={() => removeSection(sectionIndex)}
                >
                  <Trash2 size={16} aria-hidden="true" />删除章节
                </button>
              </div>
              <div className="hitl-edit-grid">
                <label className="is-wide"><span>章节标题</span><input required minLength={1} maxLength={200} value={section.title} onChange={(event) => updateSection(sectionIndex, { title: event.target.value })} /></label>
                <label className="is-wide"><span>章节摘要</span><textarea required rows={3} minLength={1} maxLength={4000} value={section.summary} onChange={(event) => updateSection(sectionIndex, { summary: event.target.value })} /></label>
              </div>

              {section.findings.map((finding, findingIndex) => (
                <div className={`hitl-edit-grid ${styles.findingBlock}`} key={findingIndex}>
                  <label className="is-wide">
                    <span>研究发现 {findingIndex + 1}</span>
                    <textarea required rows={3} minLength={1} maxLength={2000} value={finding.claim} onChange={(event) => updateFinding(sectionIndex, findingIndex, { claim: event.target.value })} />
                  </label>
                  <fieldset className={`is-wide ${styles.citationFieldset}`}>
                    <legend>引用来源</legend>
                    <div className={styles.citationOptions}>
                      {artifact.sources.map((source) => (
                        <label className={styles.citationOption} key={source.index}>
                          <input
                            type="checkbox"
                            checked={finding.source_indexes.includes(source.index)}
                            onChange={() => toggleFindingSource(sectionIndex, findingIndex, source.index)}
                          />
                          <span>[{source.index}] {source.evidence.title}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <button
                    type="button"
                    className={`hitl-secondary-button ${styles.findingAction}`}
                    title="删除研究发现"
                    aria-label={`删除章节 ${sectionIndex + 1} 的研究发现 ${findingIndex + 1}`}
                    disabled={section.findings.length === 1}
                    onClick={() => removeFinding(sectionIndex, findingIndex)}
                  >
                    <Trash2 size={16} aria-hidden="true" />删除发现
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="hitl-secondary-button"
                disabled={section.findings.length >= 12}
                onClick={() => addFinding(sectionIndex)}
              >
                <CirclePlus size={16} aria-hidden="true" />添加研究发现
              </button>
            </section>
          ))}

          <div className="hitl-review-actions">
            <button
              type="button"
              className="hitl-secondary-button"
              disabled={editValues.sections.length >= 8}
              onClick={addSection}
            >
              <CirclePlus size={16} aria-hidden="true" />添加研究章节
            </button>
          </div>

          <div className="hitl-edit-grid">
            <label className="is-wide"><span>风险提示（每行一项）</span><textarea rows={4} value={editValues.riskNotes} onChange={(event) => updateTopLevel("riskNotes", event.target.value)} /></label>
            <label className="is-wide"><span>证据缺口（每行一项）</span><textarea rows={4} value={editValues.evidenceGaps} onChange={(event) => updateTopLevel("evidenceGaps", event.target.value)} /></label>
            <label className="is-wide"><span>修改说明（可选）</span><textarea rows={2} maxLength={1000} value={comment} onChange={(event) => setComment(event.target.value)} /></label>
          </div>

          {formError ? <p className="hitl-form-error" role="alert"><CircleAlert size={16} />{formError}</p> : null}
          <div className="hitl-edit-submit">
            <button type="button" className="hitl-secondary-button" onClick={() => setEditValues(deepResearchEditValuesFromPayload(payload))}>
              <RotateCcw size={16} aria-hidden="true" />恢复草稿值
            </button>
            <button type="submit" className="hitl-action-button is-edit">
              <FilePenLine size={17} aria-hidden="true" />
              {deferSubmission ? "在本页选择修改后重审" : "提交修改并重审"}
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );

  function updateTopLevel(
    field: "executiveSummary" | "riskNotes" | "evidenceGaps",
    value: string,
  ) {
    setFormError(null);
    setEditValues((current) => ({ ...current, [field]: value }));
  }

  function updateSection(
    sectionIndex: number,
    update: Partial<DeepResearchReport["sections"][number]>,
  ) {
    setFormError(null);
    setEditValues((current) => ({
      ...current,
      sections: current.sections.map((section, index) =>
        index === sectionIndex ? { ...section, ...update } : section),
    }));
  }

  function updateFinding(
    sectionIndex: number,
    findingIndex: number,
    update: Partial<DeepResearchReport["sections"][number]["findings"][number]>,
  ) {
    setFormError(null);
    setEditValues((current) => ({
      ...current,
      sections: current.sections.map((section, index) => index === sectionIndex
        ? {
            ...section,
            findings: section.findings.map((finding, currentFindingIndex) =>
              currentFindingIndex === findingIndex ? { ...finding, ...update } : finding),
          }
        : section),
    }));
  }

  function toggleFindingSource(sectionIndex: number, findingIndex: number, sourceIndex: number) {
    const finding = editValues.sections[sectionIndex]?.findings[findingIndex];
    if (!finding) return;
    const sourceIndexes = finding.source_indexes.includes(sourceIndex)
      ? finding.source_indexes.filter((index) => index !== sourceIndex)
      : [...finding.source_indexes, sourceIndex].sort((left, right) => left - right);
    updateFinding(sectionIndex, findingIndex, { source_indexes: sourceIndexes });
  }

  function addSection() {
    if (editValues.sections.length >= 8) return;
    setEditValues((current) => ({
      ...current,
      sections: [...current.sections, {
        title: "",
        summary: "",
        findings: [{ claim: "", source_indexes: [artifact.sources[0]?.index ?? 1] }],
      }],
    }));
  }

  function removeSection(sectionIndex: number) {
    if (editValues.sections.length <= 1) return;
    setEditValues((current) => ({
      ...current,
      sections: current.sections.filter((_, index) => index !== sectionIndex),
    }));
  }

  function addFinding(sectionIndex: number) {
    const section = editValues.sections[sectionIndex];
    if (!section || section.findings.length >= 12) return;
    updateSection(sectionIndex, {
      findings: [...section.findings, {
        claim: "",
        source_indexes: [artifact.sources[0]?.index ?? 1],
      }],
    });
  }

  function removeFinding(sectionIndex: number, findingIndex: number) {
    const section = editValues.sections[sectionIndex];
    if (!section || section.findings.length <= 1) return;
    updateSection(sectionIndex, {
      findings: section.findings.filter((_, index) => index !== findingIndex),
    });
  }
}

function ReviewMetric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function ReviewList({ label, items, empty }: { label: string; items: string[]; empty: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{items.length > 0 ? items.join("；") : empty}</dd>
    </div>
  );
}

function splitList(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizedComment(comment: string): string | null {
  const normalized = comment.trim();
  return normalized || null;
}

function readableResearchEditError(error: unknown): string {
  if (error instanceof Error && /must change the report/i.test(error.message)) {
    return "请至少修改一个报告字段后再提交。";
  }
  return "请检查报告必填项和引用来源；每条研究发现至少需要一个有效引用。";
}
