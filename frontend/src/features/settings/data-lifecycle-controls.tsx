"use client";

import {
  Archive,
  CircleAlert,
  CircleCheck,
  Download,
  FileClock,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import {
  createDataDeletion,
  createDataExport,
  getDataExport,
  getDataExportBundle,
  getDataExportManifest,
  getDataDeletion,
  getDataLifecyclePolicy,
  ProductApiError,
  updateDataLifecyclePolicy,
} from "@/lib/api/product-client";
import {
  clearPersistedExportId,
  persistExportId,
  readPersistedExportId,
} from "@/features/settings/data-lifecycle-state";
import type {
  DataDeletion,
  DataExport,
  DataExportBundle,
  DataExportManifest,
  DataLifecyclePolicy,
} from "@/lib/schemas/product-api";

const DELETE_CONFIRMATION = "DELETE MY DATA" as const;
const terminalExportStatuses = new Set<DataExport["status"]>(["succeeded", "failed"]);
const terminalDeletionStatuses = new Set<DataDeletion["status"]>([
  "pending_external",
  "succeeded",
  "blocked_legal_hold",
  "failed",
]);

const retentionRows: Array<{
  key: keyof DataLifecyclePolicy;
  label: string;
  suffix: string;
}> = [
  { key: "product_retention_days", label: "任务、运行、决策与用量", suffix: "天" },
  { key: "artifact_retention_days", label: "报告与证据", suffix: "天" },
  { key: "completed_checkpoint_retention_days", label: "完成后的技术检查点", suffix: "天" },
  { key: "technical_projection_retention_days", label: "技术投影", suffix: "天" },
  { key: "log_retention_days", label: "应用日志", suffix: "天" },
  { key: "backup_retention_days", label: "在线备份轮换", suffix: "天" },
];

const systemLabels: Record<string, string> = {
  product_db: "Product 数据库",
  object_storage: "对象存储",
  checkpoint: "Agent 检查点",
  store: "Agent Store",
  search: "搜索索引",
  langsmith: "LangSmith",
  langfuse: "Langfuse",
  logs: "应用日志",
  backups: "备份轮换",
};

export function DataLifecycleControls() {
  const [policy, setPolicy] = useState<DataLifecyclePolicy | null>(null);
  const [exportJob, setExportJob] = useState<DataExport | null>(null);
  const [manifest, setManifest] = useState<DataExportManifest | null>(null);
  const [bundle, setBundle] = useState<DataExportBundle | null>(null);
  const [deletion, setDeletion] = useState<DataDeletion | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [legalHoldActive, setLegalHoldActive] = useState(false);
  const [legalHoldReason, setLegalHoldReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const restorePersistedExport = useCallback(async (
    nextPolicy: DataLifecyclePolicy,
    isActive: () => boolean,
  ) => {
    const exportId = readPersistedExportId(
      nextPolicy.owner_user_id,
      window.localStorage,
    );
    if (exportId === null) return;
    try {
      let current = await getDataExport(exportId);
      if (
        current.tenant_id !== nextPolicy.tenant_id
        || current.workspace_id !== nextPolicy.workspace_id
        || current.owner_user_id !== nextPolicy.owner_user_id
      ) {
        clearPersistedExportId(nextPolicy.owner_user_id, window.localStorage);
        return;
      }
      if (!isActive()) return;
      setExportJob(current);
      for (let attempt = 0; attempt < 30 && !terminalExportStatuses.has(current.status); attempt += 1) {
        await pause(1_000);
        current = await getDataExport(current.id);
        if (!isActive()) return;
        setExportJob(current);
      }
      if (current.status !== "succeeded") return;
      const [nextManifest, nextBundle] = await Promise.all([
        getDataExportManifest(current.id),
        getDataExportBundle(current.id),
      ]);
      if (!isActive()) return;
      setManifest(nextManifest);
      setBundle(nextBundle);
    } catch (reason) {
      if (reason instanceof ProductApiError && reason.status === 404) {
        clearPersistedExportId(nextPolicy.owner_user_id, window.localStorage);
        return;
      }
      if (isActive()) {
        setError(lifecycleErrorMessage(reason, "无法恢复最近的数据导出。"));
      }
    }
  }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const nextPolicy = await getDataLifecyclePolicy();
      setPolicy(nextPolicy);
      setLegalHoldActive(nextPolicy.legal_hold_active);
      setLegalHoldReason(nextPolicy.legal_hold_reason ?? "");
      void restorePersistedExport(nextPolicy, () => true);
    } catch (reason) {
      setError(lifecycleErrorMessage(reason, "无法读取数据与隐私策略，请稍后重试。"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    void getDataLifecyclePolicy()
      .then((nextPolicy) => {
        if (!active) return;
        setPolicy(nextPolicy);
        setLegalHoldActive(nextPolicy.legal_hold_active);
        setLegalHoldReason(nextPolicy.legal_hold_reason ?? "");
        void restorePersistedExport(nextPolicy, () => active);
      })
      .catch((reason: unknown) => {
        if (active) setError(lifecycleErrorMessage(reason, "无法读取数据与隐私策略，请稍后重试。"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [restorePersistedExport]);

  async function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!policy || savingPolicy) return;
    if (legalHoldActive && legalHoldReason.trim().length < 1) {
      setError("启用合法保留时必须填写原因。");
      return;
    }
    setSavingPolicy(true);
    setError(null);
    setNotice(null);
    try {
      const nextPolicy = await updateDataLifecyclePolicy({
        legal_hold_active: legalHoldActive,
        legal_hold_reason: legalHoldActive ? legalHoldReason.trim() : null,
      });
      setPolicy(nextPolicy);
      setLegalHoldActive(nextPolicy.legal_hold_active);
      setLegalHoldReason(nextPolicy.legal_hold_reason ?? "");
      setNotice("数据保留策略已保存。");
    } catch (reason) {
      setError(lifecycleErrorMessage(reason, "无法保存数据保留策略。"));
    } finally {
      setSavingPolicy(false);
    }
  }

  async function startExport() {
    if (!policy || exporting) return;
    setExporting(true);
    setError(null);
    setNotice(null);
    setManifest(null);
    setBundle(null);
    try {
      let current = await createDataExport();
      persistExportId(policy.owner_user_id, current.id, window.localStorage);
      setExportJob(current);
      for (let attempt = 0; attempt < 30 && !terminalExportStatuses.has(current.status); attempt += 1) {
        await pause(1_000);
        current = await getDataExport(current.id);
        setExportJob(current);
      }
      if (current.status !== "succeeded") {
        throw new Error(current.last_error ?? "导出任务未能完成。");
      }
      const [nextManifest, nextBundle] = await Promise.all([
        getDataExportManifest(current.id),
        getDataExportBundle(current.id),
      ]);
      setManifest(nextManifest);
      setBundle(nextBundle);
      setNotice("导出清单已生成，并通过哈希校验。");
    } catch (reason) {
      setError(lifecycleErrorMessage(reason, "导出任务失败，请查看状态后重试。"));
    } finally {
      setExporting(false);
    }
  }

  async function startDeletion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (deleting || confirmation !== DELETE_CONFIRMATION) return;
    setDeleting(true);
    setError(null);
    setNotice(null);
    try {
      let current = await createDataDeletion(DELETE_CONFIRMATION);
      setDeletion(current);
      for (let attempt = 0; attempt < 30 && !terminalDeletionStatuses.has(current.status); attempt += 1) {
        await pause(1_000);
        current = await getDataDeletion(current.id);
        setDeletion(current);
      }
      setNotice(
        current.status === "pending_external"
          ? "Product 数据已进入删除流程，外部系统仍等待可验证的删除回执。"
          : "删除任务状态已更新。",
      );
      setConfirmation("");
    } catch (reason) {
      setError(lifecycleErrorMessage(reason, "删除请求失败，未确认删除结果。"));
    } finally {
      setDeleting(false);
    }
  }

  const canDownload = bundle?.status === "succeeded" && bundle.bundle !== null;
  const holdChanged = policy !== null
    && (policy.legal_hold_active !== legalHoldActive
      || (policy.legal_hold_reason ?? "") !== legalHoldReason.trim());

  return (
    <div className="work-page settings-page">
      <header className="work-header">
        <div>
          <p className="section-kicker">Settings / Data lifecycle</p>
          <h1>数据与隐私</h1>
          <p>查看保留策略、导出当前用户数据，并提交可审计的删除请求。</p>
          <Link className="settings-section-link" href="/settings" prefetch={false}>
            通知设置
          </Link>
        </div>
        <span className="boundary-label list-meta-label">
          <ShieldCheck size={17} aria-hidden="true" />
          Product 数据边界
        </span>
      </header>

      {loading ? (
        <section className="empty-work-state" aria-live="polite" aria-busy="true">
          <LoaderCircle className="spinning-icon" size={22} aria-hidden="true" />
          <div><h2>正在读取数据策略</h2><p>正在同步当前用户和工作区的保留配置。</p></div>
        </section>
      ) : null}

      {error ? (
        <section className="request-error settings-load-error" role="alert">
          <CircleAlert size={20} aria-hidden="true" />
          <div><h2>数据生命周期操作失败</h2><p>{error}</p></div>
          <button className="retry-button" type="button" onClick={() => void load()}>
            <RefreshCw size={17} aria-hidden="true" />重新读取
          </button>
        </section>
      ) : null}

      {notice ? <p className="settings-save-toast" role="status" aria-live="polite"><CircleCheck size={16} aria-hidden="true" />{notice}</p> : null}

      {!loading && policy ? (
        <>
          <section className="settings-panel" aria-labelledby="retention-heading">
            <header className="settings-panel-header">
              <span className="settings-channel-icon" aria-hidden="true"><FileClock size={20} /></span>
              <div><h2 id="retention-heading">保留策略</h2><p>默认关闭原始 Prompt 和 Response 保存；外部系统策略不会被本地页面冒充修改。</p></div>
            </header>
            <dl className="settings-facts lifecycle-facts">
              {retentionRows.map(({ key, label, suffix }) => <div key={key}><dt>{label}</dt><dd>{String(policy[key])}{suffix}</dd></div>)}
              <div><dt>原始 Prompt</dt><dd>{policy.retain_raw_prompt ? "已启用" : "未保存"}</dd></div>
              <div><dt>原始 Response</dt><dd>{policy.retain_raw_response ? "已启用" : "未保存"}</dd></div>
            </dl>
            <form className="settings-form" onSubmit={savePolicy}>
              <div className="settings-switch-row">
                <div><strong>合法保留</strong><p>启用后删除请求会被阻断，并保留明确原因。</p></div>
                <label className="settings-switch">
                  <input type="checkbox" role="switch" checked={legalHoldActive} disabled={savingPolicy} onChange={(event) => setLegalHoldActive(event.target.checked)} />
                  <span className="settings-switch-track" aria-hidden="true"><span /></span>
                  <span className="settings-switch-label">{legalHoldActive ? "已启用" : "未启用"}</span>
                </label>
              </div>
              {legalHoldActive ? <label className="settings-key-field"><span>保留原因</span><textarea className="lifecycle-textarea" value={legalHoldReason} maxLength={500} onChange={(event) => setLegalHoldReason(event.target.value)} /></label> : null}
              <div className="settings-actions"><button className="submit-button" type="submit" disabled={!holdChanged || savingPolicy}>{savingPolicy ? <LoaderCircle className="spinning-icon" size={17} aria-hidden="true" /> : <Save size={17} aria-hidden="true" />}{savingPolicy ? "正在保存" : "保存策略"}</button></div>
            </form>
          </section>

          <section className="settings-panel" aria-labelledby="export-heading">
            <header className="settings-panel-header"><span className="settings-channel-icon" aria-hidden="true"><Archive size={20} /></span><div><h2 id="export-heading">数据导出</h2><p>生成带版本和 SHA-256 清单的用户数据包，敏感凭据和原始模型 I/O 不会进入导出。</p></div></header>
            <div className="lifecycle-action-row"><button className="submit-button" type="button" onClick={() => void startExport()} disabled={exporting}>{exporting ? <LoaderCircle className="spinning-icon" size={17} aria-hidden="true" /> : <Archive size={17} aria-hidden="true" />}{exporting ? "正在生成清单" : "生成新的导出"}</button>{exportJob ? <span className="lifecycle-status" data-state={exportJob.status}>导出：{exportStatusLabel(exportJob.status)}</span> : null}</div>
            {manifest?.manifest ? <div className="lifecycle-receipt" role="status"><CircleCheck size={17} aria-hidden="true" /><div><strong>清单已校验</strong><span>版本 {manifest.manifest_version} · SHA-256 {manifest.manifest_hash}</span></div>{canDownload ? <button className="icon-text-button" type="button" onClick={() => downloadBundle(bundle.bundle)}><Download size={16} aria-hidden="true" />下载数据包</button> : null}</div> : null}
          </section>

          <section className="settings-panel lifecycle-danger-panel" aria-labelledby="deletion-heading">
            <header className="settings-panel-header"><span className="settings-channel-icon" aria-hidden="true"><Trash2 size={20} /></span><div><h2 id="deletion-heading">删除我的数据</h2><p>只删除当前用户在当前工作区的 Product 数据。外部系统必须返回真实回执后才会从 pending_external 继续。</p></div></header>
            {deletion ? <div className="lifecycle-system-list" role="status"><strong>删除任务：{deletionStatusLabel(deletion.status)}</strong>{Object.entries(deletion.system_status).map(([system, state]) => <div key={system}><span>{systemLabels[system] ?? system}</span><span data-state={state}>{state}</span></div>)}</div> : null}
            <form className="settings-form" onSubmit={startDeletion}>
              <label className="settings-key-field"><span>输入 DELETE MY DATA 以确认</span><input value={confirmation} autoComplete="off" spellCheck={false} onChange={(event) => setConfirmation(event.target.value)} disabled={deleting || policy.legal_hold_active} /></label>
              <div className="settings-actions"><button className="danger-button" type="submit" disabled={deleting || policy.legal_hold_active || confirmation !== DELETE_CONFIRMATION}>{deleting ? <LoaderCircle className="spinning-icon" size={17} aria-hidden="true" /> : <LockKeyhole size={17} aria-hidden="true" />}{deleting ? "正在提交" : "提交删除请求"}</button></div>
            </form>
          </section>
        </>
      ) : null}
    </div>
  );
}

function exportStatusLabel(status: DataExport["status"]): string {
  return { queued: "排队中", running: "处理中", succeeded: "已完成", failed: "失败" }[status];
}

function deletionStatusLabel(status: DataDeletion["status"]): string {
  return { queued: "排队中", running: "处理中", pending_external: "等待外部回执", succeeded: "已完成", blocked_legal_hold: "被合法保留阻断", failed: "失败" }[status];
}

function lifecycleErrorMessage(reason: unknown, fallback: string): string {
  if (reason instanceof ProductApiError) return reason.message;
  if (reason instanceof Error && reason.message.trim()) return reason.message;
  return fallback;
}

function pause(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function downloadBundle(value: Record<string, unknown> | null): void {
  if (value === null) return;
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "crypto-alert-data-export.json";
  anchor.click();
  URL.revokeObjectURL(url);
}
