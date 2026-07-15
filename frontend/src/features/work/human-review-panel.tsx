"use client";

import {
  ArrowLeft,
  Check,
  CheckCircle2,
  CircleAlert,
  CircleX,
  Clock3,
  ExternalLink,
  FilePenLine,
  LoaderCircle,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import {
  FormEvent,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

import { ProductApiError } from "@/lib/api/product-client";
import {
  interruptResponseSchema,
  type InterruptResponse,
  type OfficialReviewPayload,
  type PendingInterrupt,
  type ProductTask,
} from "@/lib/schemas/product-api";

export type ReviewAction = "approve" | "reject" | "edit";
type ReviewMode = ReviewAction | null;
export type ReviewSubmissionPhase =
  | "idle"
  | "submitting"
  | "accepted"
  | "conflict"
  | "expired"
  | "network_error";
export type ReviewInteractionState =
  | "pending"
  | "responding"
  | "submitting"
  | "accepted"
  | "conflict"
  | "expired"
  | "network_error";

export type ReviewEditFormValues = {
  mainAction: string;
  probability: string;
  positionSizeClass: string;
  maxLeverage: string;
  riskPct: string;
  rootCauseChain: string;
  whyNotOpposite: string;
  invalidation: string;
};

type HumanReviewPanelProps = {
  interrupt: PendingInterrupt;
  disabled?: boolean;
  onRespond: (
    response: InterruptResponse,
    idempotencyKey: string,
  ) => Promise<ProductTask>;
  onConflict: () => void;
};

export type ReviewRequestIdentity = {
  fingerprint: string;
  idempotencyKey: string;
};

export type ReviewSourceReference = {
  text: string;
  href: string | null;
  issue: "invalid" | "unsupported" | null;
};

export type ReviewDeadlineHint = {
  countdown: string | null;
  locallyElapsed: boolean;
};

const decimalPattern = /^(?:0|[1-9]\d*)(?:\.\d+)?$/;
const integerPattern = /^(?:0|[1-9]\d*)$/;

const actionLabels: Record<string, string> = {
  open_long: "开多",
  open_short: "开空",
  hold_long: "持有多单",
  hold_short: "持有空单",
  close_long: "平多",
  close_short: "平空",
  flip_long_to_short: "多转空",
  flip_short_to_long: "空转多",
  trigger_long: "条件触发多单",
  trigger_short: "条件触发空单",
  no_trade: "不交易",
};

const positionLabels: Record<string, string> = {
  light: "轻仓",
  standard: "标准仓位",
  heavy: "重仓",
  none: "不建仓",
};

export function resolveReviewInteractionState(
  interrupt: Pick<PendingInterrupt, "status">,
  phase: ReviewSubmissionPhase,
): ReviewInteractionState {
  if (interrupt.status === "responding") return "responding";
  if (phase === "accepted") return "accepted";
  if (phase === "expired") return "expired";
  if (phase === "conflict") return "conflict";
  if (phase === "submitting") return "submitting";
  if (phase === "network_error") return "network_error";
  return "pending";
}

export function resolveReviewStateAnnouncement(state: ReviewInteractionState): {
  role: "status" | undefined;
  ariaLive: "off" | "polite";
} {
  return state === "pending"
    ? { role: undefined, ariaLive: "off" }
    : { role: "status", ariaLive: "polite" };
}

export function resolveAvailableReviewActions(
  allowedActions: readonly ReviewAction[],
  riskAllowed: boolean,
): ReviewAction[] {
  return allowedActions.filter((action) => action !== "approve" || riskAllowed);
}

export function isReviewActionAvailable(
  allowedActions: readonly ReviewAction[],
  riskAllowed: boolean,
  action: ReviewAction,
) {
  return resolveAvailableReviewActions(allowedActions, riskAllowed).includes(action);
}

export function resolveReviewSourceReference(reference: string): ReviewSourceReference {
  const text = reference.trim();
  if (!text) return { text: "（空来源）", href: null, issue: "invalid" };

  try {
    const url = new URL(text);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return { text, href: null, issue: "unsupported" };
    }
    if (url.username || url.password) {
      return { text, href: null, issue: "invalid" };
    }
    return { text, href: url.toString(), issue: null };
  } catch {
    return { text, href: null, issue: "invalid" };
  }
}

export function resolveReviewDeadlineHint(
  expiresAt: string | null,
  now: number | null,
): ReviewDeadlineHint {
  if (expiresAt === null || now === null) {
    return { countdown: null, locallyElapsed: false };
  }
  const expiresAtMilliseconds = Date.parse(expiresAt);
  if (!Number.isFinite(expiresAtMilliseconds)) {
    return { countdown: null, locallyElapsed: false };
  }

  const remainingSeconds = Math.ceil((expiresAtMilliseconds - now) / 1_000);
  if (remainingSeconds <= 0) {
    return { countdown: "00:00", locallyElapsed: true };
  }
  const hours = Math.floor(remainingSeconds / 3_600);
  const minutes = Math.floor((remainingSeconds % 3_600) / 60);
  const seconds = remainingSeconds % 60;
  return {
    countdown: hours > 0
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
      : `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`,
    locallyElapsed: false,
  };
}

export function isServerExpiredReviewConflict(status: number, message: string) {
  return status === 409 && /(?:expir|过期)/i.test(message);
}

export function resolveReviewRequestIdentity(
  response: InterruptResponse,
  previous: ReviewRequestIdentity | null,
  createIdempotencyKey: () => string = () => crypto.randomUUID(),
): ReviewRequestIdentity {
  const fingerprint = JSON.stringify(interruptResponseSchema.parse(response));
  return previous?.fingerprint === fingerprint
    ? previous
    : { fingerprint, idempotencyKey: createIdempotencyKey() };
}

export function buildEditResponse(
  values: ReviewEditFormValues,
  payload: OfficialReviewPayload,
  responseVersion: number,
  comment: string,
): InterruptResponse {
  const rootCauseChain = values.rootCauseChain
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
  const edits = {
    main_action: values.mainAction,
    probability: parseBoundedDecimal(values.probability, "概率", 0, 1),
    position_size_class: values.positionSizeClass,
    max_leverage: parsePositiveInteger(values.maxLeverage, "最大杠杆"),
    risk_pct: parseBoundedDecimal(values.riskPct, "风险比例", 0, 1),
    root_cause_chain: rootCauseChain,
    why_not_opposite: values.whyNotOpposite.trim(),
    invalidation: values.invalidation.trim(),
  };
  const response = interruptResponseSchema.parse({
    response_version: responseVersion,
    action: "edit",
    comment: normalizedComment(comment),
    edits,
  });
  const analysis = payload.artifact.analysis;
  const original = {
    main_action: analysis.main_action,
    probability: analysis.probability,
    position_size_class: analysis.position_size_class,
    max_leverage: analysis.max_leverage,
    risk_pct: analysis.risk_pct,
    root_cause_chain: analysis.root_cause_chain,
    why_not_opposite: analysis.why_not_opposite,
    invalidation: analysis.invalidation,
  };
  if (JSON.stringify(response.edits) === JSON.stringify(original)) {
    throw new Error("请至少修改一个审核字段后再提交。 ");
  }
  return response;
}

export function HumanReviewPanel({
  interrupt,
  disabled = false,
  onRespond,
  onConflict,
}: HumanReviewPanelProps) {
  const analysis = interrupt.payload.artifact.analysis;
  const evidence = interrupt.payload.artifact.evidence_verdict;
  const risk = interrupt.payload.artifact.risk_verdict;
  const generatedId = useId().replace(/:/g, "");
  const reviewTitleId = `hitl-review-${generatedId}`;
  const rationaleId = `hitl-rationale-${generatedId}`;
  const gateId = `hitl-gate-${generatedId}`;
  const sourcesId = `hitl-sources-${generatedId}`;
  const confirmationId = `hitl-confirmation-${generatedId}`;
  const confirmationTitleId = `hitl-confirmation-title-${generatedId}`;
  const editFormId = `hitl-edit-${generatedId}`;
  const editTitleId = `hitl-edit-title-${generatedId}`;
  const [mode, setMode] = useState<ReviewMode>(null);
  const [comment, setComment] = useState("");
  const [phase, setPhase] = useState<ReviewSubmissionPhase>("idle");
  const [failureMessage, setFailureMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [now, setNow] = useState<number | null>(null);
  const [editValues, setEditValues] = useState<ReviewEditFormValues>(() =>
    editValuesFromPayload(interrupt.payload)
  );
  const submissionLock = useRef(false);
  const retryRequest = useRef<ReviewRequestIdentity | null>(null);
  const returnFocusTarget = useRef<HTMLButtonElement | null>(null);
  const returnFocusRequested = useRef(false);
  const confirmationHeading = useRef<HTMLHeadingElement | null>(null);
  const editHeading = useRef<HTMLHeadingElement | null>(null);

  const availableActions = useMemo(
    () => resolveAvailableReviewActions(interrupt.payload.allowed_actions, risk.allowed),
    [interrupt.payload.allowed_actions, risk.allowed],
  );
  const approveAvailable = availableActions.includes("approve");
  const rejectAvailable = availableActions.includes("reject");
  const editAvailable = availableActions.includes("edit");

  useEffect(() => {
    const initialTick = window.setTimeout(() => setNow(Date.now()), 0);
    if (interrupt.expires_at === null || interrupt.status === "responding") {
      return () => window.clearTimeout(initialTick);
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      window.clearTimeout(initialTick);
      window.clearInterval(timer);
    };
  }, [interrupt.expires_at, interrupt.status]);

  const interactionState = resolveReviewInteractionState(interrupt, phase);
  const actionDisabled = disabled
    || (interactionState !== "pending" && interactionState !== "network_error");
  const interactive = interactionState === "pending" || interactionState === "network_error";
  const deadline = useMemo(
    () => resolveReviewDeadlineHint(interrupt.expires_at, now),
    [interrupt.expires_at, now],
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

  async function submitResponse(response: InterruptResponse) {
    if (submissionLock.current || actionDisabled) return;
    const validated = interruptResponseSchema.parse(response);
    if (!isReviewActionAvailable(
      interrupt.payload.allowed_actions,
      risk.allowed,
      validated.action,
    )) return;
    const request = resolveReviewRequestIdentity(validated, retryRequest.current);
    retryRequest.current = request;
    submissionLock.current = true;
    setPhase("submitting");
    setFailureMessage(null);
    setFormError(null);
    try {
      await onRespond(validated, request.idempotencyKey);
      retryRequest.current = null;
      setPhase("accepted");
      setMode(null);
    } catch (error) {
      if (error instanceof ProductApiError && error.status === 409) {
        const expired = isServerExpiredReviewConflict(error.status, error.message);
        setPhase(expired ? "expired" : "conflict");
        setFailureMessage(expired
          ? "服务端已关闭本次审核窗口，正在读取任务的最终状态。"
          : "该审核请求已被处理或版本已更新，正在重新读取服务端状态。");
        onConflict();
      } else {
        setPhase("network_error");
        setFailureMessage(
          error instanceof ProductApiError
            ? error.message
            : "网络连接中断，本次响应尚未得到服务端确认。",
        );
      }
    } finally {
      submissionLock.current = false;
    }
  }

  function submitDecision(action: "approve" | "reject") {
    if (!isReviewActionAvailable(
      interrupt.payload.allowed_actions,
      risk.allowed,
      action,
    )) return;
    const response = interruptResponseSchema.parse({
      response_version: interrupt.response_version,
      action,
      comment: normalizedComment(comment),
      edits: null,
    });
    void submitResponse(response);
  }

  function submitEdits(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editAvailable) return;
    try {
      const response = buildEditResponse(
        editValues,
        interrupt.payload,
        interrupt.response_version,
        comment,
      );
      void submitResponse(response);
    } catch (error) {
      setFormError(error instanceof Error ? error.message.trim() : "请检查修改内容。");
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
          <span className="hitl-review-icon" aria-hidden="true"><ShieldCheck size={20} /></span>
          <div>
            <p className="section-kicker">Human review</p>
            <h2 id={reviewTitleId}>分析草稿待人工确认</h2>
          </div>
        </div>
        <ReviewStateBadge state={interactionState} deadline={deadline} />
      </header>

      <div className="hitl-review-summary" aria-label="待审核决策摘要">
        <ReviewMetric label="建议动作" value={actionLabels[analysis.main_action] ?? analysis.main_action} />
        <ReviewMetric label="主观概率" value={`${Math.round(analysis.probability * 100)}%`} />
        <ReviewMetric label="仓位等级" value={positionLabels[analysis.position_size_class] ?? analysis.position_size_class} />
        <ReviewMetric label="最大杠杆" value={`${analysis.max_leverage}x`} />
        <ReviewMetric label="风险比例" value={`${formatPercent(analysis.risk_pct)}%`} />
      </div>

      <div className="hitl-review-detail-grid">
        <section className="hitl-review-detail" aria-labelledby={rationaleId}>
          <h3 id={rationaleId}>判断依据</h3>
          <ol className="hitl-cause-list">
            {analysis.root_cause_chain.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}
          </ol>
          <dl className="hitl-review-notes">
            <div><dt>不选择反向的原因</dt><dd>{analysis.why_not_opposite}</dd></div>
            <div><dt>失效条件</dt><dd>{analysis.invalidation || "未提供"}</dd></div>
          </dl>
        </section>

        <section className="hitl-review-detail" aria-labelledby={gateId}>
          <h3 id={gateId}>证据与风险门禁</h3>
          <div className="hitl-gate-row" data-tone={evidence.sufficient ? "positive" : "danger"}>
            {evidence.sufficient ? <CheckCircle2 size={17} /> : <CircleAlert size={17} />}
            <div>
              <strong>{evidence.sufficient ? "证据满足门禁" : "证据仍有缺口"}</strong>
              <span>置信上限 {formatPercent(evidence.confidence_cap)}%</span>
            </div>
          </div>
          <div className="hitl-gate-row" data-tone={risk.allowed ? "positive" : "danger"}>
            {risk.allowed ? <ShieldCheck size={17} /> : <ShieldAlert size={17} />}
            <div>
              <strong>{risk.allowed ? "风险策略允许" : "风险策略阻断"}</strong>
              <span>置信上限 {formatPercent(risk.confidence_cap)}%</span>
            </div>
          </div>
          <ReviewNotices
            missing={[...evidence.missing_required, ...evidence.missing_optional]}
            warnings={[...evidence.warnings, ...risk.warnings, ...risk.blocked_reasons]}
          />
        </section>
      </div>

      <ReviewSources
        headingId={sourcesId}
        references={interrupt.payload.artifact.source_references}
      />

      {interactive && deadline.locallyElapsed ? (
        <p className="hitl-local-deadline-notice" role="status">
          <Clock3 size={16} aria-hidden="true" />
          本地倒计时已到，审核决定仍可提交；是否过期以 Product 服务响应为准。
        </p>
      ) : null}

      <ReviewStateNotice state={interactionState} message={failureMessage} />

      {interactive && !risk.allowed ? (
        <p className="hitl-approval-blocked" role="note">
          <ShieldAlert size={16} aria-hidden="true" />
          风险门禁未通过，不能批准；请拒绝或修改后重新审核。
        </p>
      ) : null}

      {interactive ? (
        <div className="hitl-review-actions" role="group" aria-label="审核决定">
          {approveAvailable ? (
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
          {rejectAvailable ? (
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
          {editAvailable ? (
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

      {interactive
      && (activeMode === "approve" || activeMode === "reject") ? (
        <div
          id={confirmationId}
          className="hitl-confirmation"
          data-tone={activeMode === "approve" ? "positive" : "danger"}
          role="region"
          aria-labelledby={confirmationTitleId}
        >
          <div>
            <h3 id={confirmationTitleId} ref={confirmationHeading} tabIndex={-1}>
              {activeMode === "approve" ? "确认批准这份分析？" : "确认拒绝这份分析？"}
            </h3>
            <p>{activeMode === "approve"
              ? "批准后，Agent 将恢复运行并提交最终报告。"
              : "拒绝后，本次分析将进入明确的阻断终态。"}</p>
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
              {activeMode === "approve" ? "确认批准" : "确认拒绝"}
            </button>
          </div>
        </div>
      ) : null}

      {interactive && activeMode === "edit" ? (
        <form
          id={editFormId}
          className="hitl-edit-form"
          aria-labelledby={editTitleId}
          onSubmit={submitEdits}
        >
          <div className="hitl-edit-heading">
            <div>
              <h3 id={editTitleId} ref={editHeading} tabIndex={-1}>修改分析草稿</h3>
              <p>提交后将重新执行证据、风险与人工审核门禁。</p>
            </div>
            <button type="button" className="hitl-secondary-button" onClick={returnToReviewActions}>
              <ArrowLeft size={16} aria-hidden="true" />返回
            </button>
          </div>
          <div className="hitl-edit-grid">
            <label><span>建议动作</span><select value={editValues.mainAction} onChange={(event) => updateEdit("mainAction", event.target.value)} required>
              {Object.entries(actionLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select></label>
            <label><span>仓位等级</span><select value={editValues.positionSizeClass} onChange={(event) => updateEdit("positionSizeClass", event.target.value)} required>
              {Object.entries(positionLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select></label>
            <label><span>主观概率（0-1）</span><input type="number" min="0" max="1" step="0.01" value={editValues.probability} onChange={(event) => updateEdit("probability", event.target.value)} required /></label>
            <label><span>最大杠杆</span><input type="number" min="1" step="1" value={editValues.maxLeverage} onChange={(event) => updateEdit("maxLeverage", event.target.value)} required /></label>
            <label><span>风险比例（0-1）</span><input type="number" min="0" max="1" step="0.001" value={editValues.riskPct} onChange={(event) => updateEdit("riskPct", event.target.value)} required /></label>
            <label className="is-wide"><span>根因链（每行一项）</span><textarea rows={4} maxLength={3600} value={editValues.rootCauseChain} onChange={(event) => updateEdit("rootCauseChain", event.target.value)} required /></label>
            <label className="is-wide"><span>不选择反向的原因</span><textarea rows={3} minLength={1} maxLength={1000} value={editValues.whyNotOpposite} onChange={(event) => updateEdit("whyNotOpposite", event.target.value)} required /></label>
            <label className="is-wide"><span>失效条件</span><textarea rows={3} minLength={1} maxLength={1000} value={editValues.invalidation} onChange={(event) => updateEdit("invalidation", event.target.value)} required /></label>
            <label className="is-wide"><span>修改说明（可选）</span><textarea rows={2} maxLength={1000} value={comment} onChange={(event) => setComment(event.target.value)} /></label>
          </div>
          {formError ? <p className="hitl-form-error" role="alert"><CircleAlert size={16} />{formError}</p> : null}
          <div className="hitl-edit-submit">
            <button type="button" className="hitl-secondary-button" onClick={() => setEditValues(editValuesFromPayload(interrupt.payload))}>
              <RotateCcw size={16} aria-hidden="true" />恢复草稿值
            </button>
            <button type="submit" className="hitl-action-button is-edit">
              <FilePenLine size={17} aria-hidden="true" />提交修改并重审
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );

  function updateEdit(field: keyof ReviewEditFormValues, value: string) {
    setFormError(null);
    setEditValues((current) => ({ ...current, [field]: value }));
  }
}

function ReviewMetric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function ReviewNotices({ missing, warnings }: { missing: string[]; warnings: string[] }) {
  if (missing.length === 0 && warnings.length === 0) return null;
  return (
    <ul className="hitl-review-notices">
      {missing.map((item, index) => <li key={`missing-${index}-${item}`}>待补充：{item}</li>)}
      {warnings.map((item, index) => <li key={`warning-${index}-${item}`}>{item}</li>)}
    </ul>
  );
}

function ReviewSources({
  headingId,
  references,
}: {
  headingId: string;
  references: readonly string[];
}) {
  const sources = references.map(resolveReviewSourceReference);
  return (
    <section className="hitl-review-sources" aria-labelledby={headingId}>
      <div className="hitl-review-sources-heading">
        <h3 id={headingId}>分析来源</h3>
        <span>{sources.length} 条</span>
      </div>
      {sources.length > 0 ? (
        <ul>
          {sources.map((source, index) => (
            <li key={`${index}-${source.text}`}>
              {source.href !== null ? (
                <a
                  href={source.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  referrerPolicy="no-referrer"
                >
                  <span>{source.text}</span>
                  <ExternalLink size={16} aria-hidden="true" />
                </a>
              ) : (
                <span className="hitl-review-source-text">
                  <CircleAlert size={16} aria-hidden="true" />
                  <span>{source.text}</span>
                  <small>{source.issue === "unsupported" ? "非 HTTP(S) 来源" : "无法解析的来源"}</small>
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : <p className="hitl-review-sources-empty">当前草稿未提供来源链接。</p>}
    </section>
  );
}

function ReviewStateBadge({
  state,
  deadline,
}: {
  state: ReviewInteractionState;
  deadline: ReviewDeadlineHint;
}) {
  const content: Record<ReviewInteractionState, { icon: typeof Clock3; label: string; tone: string }> = {
    pending: {
      icon: Clock3,
      label: deadline.locallyElapsed
        ? "本地计时已到"
        : deadline.countdown
          ? `剩余 ${deadline.countdown}`
          : "等待决定",
      tone: "warning",
    },
    responding: { icon: LoaderCircle, label: "正在恢复", tone: "active" },
    submitting: { icon: LoaderCircle, label: "正在提交", tone: "active" },
    accepted: { icon: CheckCircle2, label: "响应已保存", tone: "positive" },
    conflict: { icon: CircleAlert, label: "状态已更新", tone: "danger" },
    expired: { icon: Clock3, label: "操作已过期", tone: "danger" },
    network_error: { icon: CircleAlert, label: "响应未确认", tone: "danger" },
  };
  const current = content[state];
  const announcement = resolveReviewStateAnnouncement(state);
  const Icon = current.icon;
  return (
    <span
      className="hitl-review-state"
      data-tone={current.tone}
      role={announcement.role}
      aria-live={announcement.ariaLive}
      aria-atomic={announcement.role === "status" ? true : undefined}
    >
      <Icon
        className={state === "submitting" || state === "responding" ? "spinning-icon" : undefined}
        size={16}
      />
      {current.label}
    </span>
  );
}

function ReviewStateNotice({ state, message }: { state: ReviewInteractionState; message: string | null }) {
  if (state === "pending") return null;
  const copy: Record<Exclude<ReviewInteractionState, "pending">, string> = {
    responding: "决定已持久化，Product 服务正在恢复 Agent 执行并同步新的运行状态。",
    submitting: "正在提交本次审核决定，请勿重复操作。",
    accepted: "审核响应已保存，正在恢复 Product 状态轮询。",
    conflict: message ?? "该审核请求已经被其他响应处理。",
    expired: "已到达服务端给出的截止时间，客户端操作已禁用；最终状态仍以服务端确认为准。",
    network_error: message ?? "本次响应尚未得到服务端确认，可以重试相同决定。",
  };
  return <p className="hitl-state-notice" data-state={state} role={state === "conflict" || state === "network_error" ? "alert" : "status"}>{copy[state]}</p>;
}

function editValuesFromPayload(payload: OfficialReviewPayload): ReviewEditFormValues {
  const analysis = payload.artifact.analysis;
  return {
    mainAction: analysis.main_action,
    probability: String(analysis.probability),
    positionSizeClass: analysis.position_size_class,
    maxLeverage: String(analysis.max_leverage),
    riskPct: String(analysis.risk_pct),
    rootCauseChain: analysis.root_cause_chain.join("\n"),
    whyNotOpposite: analysis.why_not_opposite,
    invalidation: analysis.invalidation,
  };
}

function parseBoundedDecimal(value: string, label: string, minimum: number, maximum: number): number {
  const normalized = value.trim();
  if (!decimalPattern.test(normalized)) throw new Error(`${label}必须是普通十进制数字。`);
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${label}必须在 ${minimum} 到 ${maximum} 之间。`);
  }
  return parsed;
}

function parsePositiveInteger(value: string, label: string): number {
  const normalized = value.trim();
  if (!integerPattern.test(normalized)) throw new Error(`${label}必须是整数。`);
  const parsed = Number(normalized);
  if (!Number.isSafeInteger(parsed) || parsed < 1) {
    throw new Error(`${label}必须是大于或等于 1 的安全整数。`);
  }
  return parsed;
}

function normalizedComment(comment: string): string | null {
  const normalized = comment.trim();
  return normalized || null;
}

function formatPercent(value: number): string {
  return (value * 100).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}
