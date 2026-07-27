"use client";

import {
  Check,
  CircleAlert,
  Database,
  GitCompareArrows,
  Play,
  RefreshCw,
  Rocket,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  decideImprovementReview,
  listImprovementCandidates,
  listImprovementDatasets,
  ProductApiError,
  promoteImprovementCandidate,
  requestImprovementReview,
  rollbackImprovementCandidate,
  runImprovementShadow,
} from "@/lib/api/product-client";
import type {
  ImprovementCandidate,
  ImprovementDatasetList,
} from "@/lib/schemas/product-api";

const statusLabels: Record<ImprovementCandidate["status"], string> = {
  draft: "草稿",
  evaluated: "已评估",
  pending_review: "待人工审批",
  approved: "已批准",
  rejected: "已拒绝",
  shadow: "影子验证",
  active: "已发布",
  rolled_back: "已回滚",
};

export function ImprovementSurface() {
  const [datasets, setDatasets] = useState<ImprovementDatasetList["items"]>([]);
  const [candidates, setCandidates] = useState<ImprovementCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      const [datasetView, candidateView] = await Promise.all([
        listImprovementDatasets(),
        listImprovementCandidates(),
      ]);
      setDatasets(datasetView.items);
      setCandidates(candidateView.items);
    } catch (reason) {
      setError(reason instanceof ProductApiError ? reason.message : "无法读取改进治理记录。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    void Promise.all([listImprovementDatasets(), listImprovementCandidates()])
      .then(([datasetView, candidateView]) => {
        if (!active) return;
        setDatasets(datasetView.items);
        setCandidates(candidateView.items);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof ProductApiError ? reason.message : "无法读取改进治理记录。");
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function act(
    candidate: ImprovementCandidate,
    operation: () => Promise<ImprovementCandidate>,
  ) {
    setBusyId(candidate.id);
    setError(null);
    try {
      const updated = await operation();
      setCandidates((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (reason) {
      setError(reason instanceof ProductApiError ? reason.message : "治理操作失败。");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="work-page improvement-page">
      <header className="work-header">
        <div>
          <p className="section-kicker">Evaluation / Governance</p>
          <h1>受控改进</h1>
          <p>从问题样本到冻结回放、人工审批、影子验证、发布与回滚的持久记录。</p>
        </div>
        <span className="boundary-label list-meta-label">
          <GitCompareArrows size={17} aria-hidden="true" />
          {candidates.length} 个候选
        </span>
      </header>

      <section className="quality-boundary improvement-boundary" aria-live="polite">
        <ShieldCheck aria-hidden="true" />
        <div>
          <h2>当前 Shadow 仅使用冻结回放</h2>
          <p>不抓取实时数据，不产生外部副作用；本地 QA 结果不等于生产流量验证。</p>
        </div>
      </section>

      {error ? (
        <section className="request-error" role="alert">
          <CircleAlert size={20} aria-hidden="true" />
          <div><h2>治理操作失败</h2><p>{error}</p></div>
          <button className="submit-button" type="button" onClick={() => void reload()}>
            <RefreshCw size={17} aria-hidden="true" />重新读取
          </button>
        </section>
      ) : null}

      {loading ? (
        <section className="empty-work-state" aria-live="polite">
          <span className="empty-state-line" aria-hidden="true" />
          <div><h2>正在读取治理记录</h2><p>同步冻结 Dataset、候选状态和发布事件。</p></div>
        </section>
      ) : null}

      {!loading ? (
        <>
          <section className="improvement-section" aria-labelledby="dataset-heading">
            <div className="improvement-section-heading">
              <div><p className="section-kicker">Frozen inputs</p><h2 id="dataset-heading">冻结 Dataset</h2></div>
              <span><Database size={16} aria-hidden="true" />{datasets.length} 组</span>
            </div>
            {datasets.length === 0 ? <p className="improvement-empty">尚无冻结 Dataset。</p> : (
              <div className="improvement-dataset-list">
                {datasets.map((dataset) => (
                  <article className="improvement-dataset-row" key={dataset.id}>
                    <div><strong>{dataset.name}</strong><span>{dataset.status === "frozen" ? "已冻结" : "草稿"}</span></div>
                    <dl>
                      <div><dt>回放</dt><dd>{dataset.replay_count}</dd></div>
                      <div><dt>Case</dt><dd>{dataset.case_names.length}</dd></div>
                      <div><dt>冻结时间</dt><dd>{dataset.frozen_at ? formatDate(dataset.frozen_at) : "--"}</dd></div>
                    </dl>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="improvement-section" aria-labelledby="candidate-heading">
            <div className="improvement-section-heading">
              <div><p className="section-kicker">Candidates</p><h2 id="candidate-heading">候选与发布记录</h2></div>
            </div>
            {candidates.length === 0 ? <p className="improvement-empty">尚无规则候选。</p> : (
              <div className="improvement-candidate-list">
                {candidates.map((candidate) => (
                  <CandidateRow
                    key={candidate.id}
                    candidate={candidate}
                    busy={busyId === candidate.id}
                    onAct={(operation) => void act(candidate, operation)}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}

function CandidateRow({
  candidate,
  busy,
  onAct,
}: {
  candidate: ImprovementCandidate;
  busy: boolean;
  onAct: (operation: () => Promise<ImprovementCandidate>) => void;
}) {
  const gate = candidate.latest_experiment?.gate_report;
  const approved = gate?.approved === true;
  return (
    <article className="improvement-candidate-row" data-status={candidate.status}>
      <div className="improvement-candidate-main">
        <div className="improvement-candidate-title">
          <span>{statusLabels[candidate.status]}</span>
          <h3>{candidate.name}</h3>
          <p>{candidate.base_version} → {candidate.candidate_version}</p>
        </div>
        <p className="improvement-rationale">{candidate.rationale}</p>
        <dl className="improvement-metrics">
          <Metric label="Release Gate" value={approved ? "通过" : candidate.latest_experiment ? "未通过" : "未运行"} />
          <Metric label="人工审批" value={candidate.latest_review ? reviewLabel(candidate.latest_review.status) : "未发起"} />
          <Metric label="Shadow" value={candidate.latest_shadow ? shadowLabel(candidate.latest_shadow.status) : "未运行"} />
          <Metric label="回滚目标" value={candidate.rollback_target_version} />
        </dl>
      </div>

      <div className="improvement-actions" aria-label={`${candidate.name} 操作`}>
        {candidate.status === "evaluated" && approved ? (
          <button type="button" disabled={busy} onClick={() => onAct(() => requestImprovementReview(candidate.id))}>
            <Play aria-hidden="true" />发起审批
          </button>
        ) : null}
        {candidate.status === "pending_review" ? (
          <>
            <button type="button" disabled={busy} onClick={() => onAct(() => decideImprovementReview(candidate.id, "approve"))}>
              <Check aria-hidden="true" />批准
            </button>
            <button className="danger" type="button" disabled={busy} onClick={() => onAct(() => decideImprovementReview(candidate.id, "reject"))}>
              <X aria-hidden="true" />拒绝
            </button>
          </>
        ) : null}
        {candidate.status === "approved" ? (
          <button type="button" disabled={busy} onClick={() => onAct(() => runImprovementShadow(candidate.id))}>
            <GitCompareArrows aria-hidden="true" />运行 Shadow
          </button>
        ) : null}
        {candidate.status === "shadow" && candidate.latest_shadow?.status === "passed" ? (
          <button type="button" disabled={busy} onClick={() => onAct(() => promoteImprovementCandidate(candidate.id))}>
            <Rocket aria-hidden="true" />发布候选
          </button>
        ) : null}
        {candidate.status === "active" ? (
          <button className="danger" type="button" disabled={busy} onClick={() => onAct(() => rollbackImprovementCandidate(candidate.id))}>
            <RotateCcw aria-hidden="true" />回滚
          </button>
        ) : null}
      </div>

      {candidate.release_events.length > 0 ? (
        <ol className="improvement-release-list" aria-label="不可变发布事件">
          {candidate.release_events.map((event) => (
            <li key={event.id}>
              <span>{event.action === "promoted" ? "发布" : "回滚"}</span>
              <strong>{event.from_version} → {event.to_version}</strong>
              <time dateTime={event.created_at}>{formatDate(event.created_at)}</time>
            </li>
          ))}
        </ol>
      ) : null}
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function reviewLabel(status: "pending" | "approved" | "rejected") {
  return status === "pending" ? "待审批" : status === "approved" ? "已批准" : "已拒绝";
}

function shadowLabel(status: "running" | "passed" | "failed") {
  return status === "running" ? "运行中" : status === "passed" ? "通过" : "失败";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
