"use client";

import {
  ArrowLeft,
  BellRing,
  CalendarClock,
  Check,
  CircleAlert,
  Clock3,
  FileCheck2,
  LoaderCircle,
  Radar,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import {
  idempotencyKeyFor,
  monitorErrorMessage,
  mutationIdentity,
  prepareMonitorRequest,
} from "@/features/monitors/monitor-state";
import { createMonitor } from "@/lib/api/monitor-client";
import { getArtifact, ProductApiError } from "@/lib/api/product-client";
import type { ArtifactDetail } from "@/lib/schemas/product-api";
import type { MonitorSchedule } from "@/lib/schemas/monitor-api";

import styles from "./monitors.module.css";

type CreateMonitorSurfaceProps = {
  artifactId: string | null;
  artifactVersionId: string | null;
  versionNumber: number | null;
};

export function CreateMonitorSurface({
  artifactId,
  artifactVersionId,
  versionNumber,
}: CreateMonitorSurfaceProps) {
  const router = useRouter();
  const [artifact, setArtifact] = useState<ArtifactDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [runTaskType, setRunTaskType] = useState<"market_analysis" | "deep_research">("market_analysis");
  const [schedule, setSchedule] = useState<MonitorSchedule>("0 */4 * * *");
  const [timezone, setTimezone] = useState("Asia/Shanghai");
  const [expiresAtLocal, setExpiresAtLocal] = useState(defaultExpiryLocal);
  const [quietEnabled, setQuietEnabled] = useState(false);
  const [quietStart, setQuietStart] = useState("23:00");
  const [quietEnd, setQuietEnd] = useState("07:00");
  const [destinationIdsText, setDestinationIdsText] = useState("");
  const createKeyRef = useRef<{ identity: string; key: string } | null>(null);

  const loadSource = useCallback(async () => {
    await Promise.resolve();
    if (!artifactId || !artifactVersionId || !versionNumber) {
      setLoadError("缺少已提交报告的版本信息，请从报告详情页重新进入。");
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const detail = await getArtifact(artifactId, versionNumber);
      const selected = detail.selected_version;
      if (
        !selected
        || selected.artifact_version_id !== artifactVersionId
        || selected.status !== "committed"
      ) {
        setLoadError("只有当前已提交的报告版本可以创建持续监控。");
        return;
      }
      setArtifact(detail);
      setName((current) => current || `${detail.symbol.replace("-USDT-SWAP", "")} ${detail.horizon} 持续关注`);
      setRunTaskType(detail.artifact_type === "deep_research_report" ? "deep_research" : "market_analysis");
      setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai");
    } catch (reason) {
      setLoadError(sourceLoadErrorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [artifactId, artifactVersionId, versionNumber]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadSource(), 0);
    return () => window.clearTimeout(timer);
  }, [loadSource]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!artifactId || !artifactVersionId || !artifact) return;
    setSubmitError(null);
    const prepared = prepareMonitorRequest(
      { artifactId, artifactVersionId },
      {
        name,
        runTaskType,
        condition: { kind: "scheduled_review" },
        schedule,
        timezone,
        expiresAtLocal,
        quietHours: quietEnabled ? { start: quietStart, end: quietEnd } : null,
        destinationIds: parseDestinationIds(destinationIdsText),
      },
    );
    if (!prepared.success) {
      setSubmitError(prepared.message);
      return;
    }
    const identity = mutationIdentity("create", prepared.request);
    const keyState = idempotencyKeyFor(createKeyRef.current, identity);
    createKeyRef.current = keyState;
    setSubmitting(true);
    try {
      await createMonitor(prepared.request, keyState.key);
      createKeyRef.current = null;
      router.push("/monitors?status=running");
    } catch (reason) {
      setSubmitError(monitorErrorMessage(reason, "持续监控创建失败，请稍后重试。"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <Link className={styles.backLink} href={artifactId ? `/artifacts/${artifactId}?version_number=${versionNumber ?? ""}` : "/library"} prefetch={false}>
            <ArrowLeft size={16} aria-hidden="true" /> 返回报告
          </Link>
          <p className={styles.kicker}>New scheduled monitor</p>
          <h1>创建持续监控</h1>
          <p>设置该报告结论的检查条件、运行频率与通知目标。</p>
        </div>
        <div className={styles.headerMeta}><Radar size={18} aria-hidden="true" /><span>新监控</span></div>
      </header>

      {loading ? (
        <section className={styles.statePanel} aria-live="polite">
          <LoaderCircle className={styles.spinner} size={22} aria-hidden="true" />
          <div><h2>正在核对报告版本</h2><p>正在确认来源版本和可用通知目标。</p></div>
        </section>
      ) : null}

      {!loading && loadError ? (
        <section className={`${styles.statePanel} ${styles.errorPanel}`} role="alert">
          <CircleAlert size={22} aria-hidden="true" />
          <div><h2>无法创建持续监控</h2><p>{loadError}</p></div>
          {artifactId && artifactVersionId && versionNumber ? (
            <button type="button" onClick={() => void loadSource()}><RefreshCw size={17} aria-hidden="true" />重新核对</button>
          ) : <Link href="/library" prefetch={false}>前往报告资料库</Link>}
        </section>
      ) : null}

      {!loading && !loadError && artifact?.selected_version ? (
        <form className={styles.form} onSubmit={(event) => void submit(event)} noValidate>
          <section className={styles.sourceBand} aria-labelledby="monitor-source-title">
            <FileCheck2 size={21} aria-hidden="true" />
            <div>
              <span>来源报告</span>
              <h2 id="monitor-source-title">{artifact.symbol.replace("-USDT-SWAP", "")} · {artifact.horizon}</h2>
              <p>{artifact.artifact_type === "deep_research_report" ? "深度研究报告" : "分析报告"} · 已提交版本 v{artifact.selected_version.version_number}</p>
            </div>
            <span className={styles.committedLabel}><Check size={15} aria-hidden="true" />已提交</span>
          </section>

          <section className={styles.formSection} aria-labelledby="monitor-basic-title">
            <div className={styles.sectionHeading}><span>01</span><div><h2 id="monitor-basic-title">监控任务</h2><p>名称与触发后的任务类型</p></div></div>
            <div className={styles.formGrid}>
              <label className={styles.wideField}>
                <span>名称</span>
                <input value={name} maxLength={120} required onChange={(event) => setName(event.target.value)} />
              </label>
              <fieldset className={styles.wideField}>
                <legend>运行任务</legend>
                <div className={styles.segmented}>
                  <label><input type="radio" name="run-task-type" checked={runTaskType === "market_analysis"} onChange={() => setRunTaskType("market_analysis")} /><span>市场分析</span></label>
                  <label><input type="radio" name="run-task-type" checked={runTaskType === "deep_research"} onChange={() => setRunTaskType("deep_research")} /><span>深度研究</span></label>
                </div>
              </fieldset>
            </div>
          </section>

          <section className={styles.formSection} aria-labelledby="monitor-condition-title">
            <div className={styles.sectionHeading}><span>02</span><div><h2 id="monitor-condition-title">触发条件</h2><p>结构化条件</p></div></div>
            <div className={styles.formGrid}>
              <div className={`${styles.wideField} ${styles.staticField}`}>
                <span>条件类型</span>
                <output aria-label="条件类型" aria-describedby="monitor-condition-availability">定期复核</output>
              </div>
              <div id="monitor-condition-availability" className={styles.inlineNotice}><Clock3 size={18} aria-hidden="true" /><span>当前仅支持按所选频率复核来源报告。</span></div>
            </div>
          </section>

          <section className={styles.formSection} aria-labelledby="monitor-schedule-title">
            <div className={styles.sectionHeading}><span>03</span><div><h2 id="monitor-schedule-title">调度时间</h2><p>频率、时区、静默与有效期</p></div></div>
            <div className={styles.formGrid}>
              <label className={styles.wideField}><span>频率</span><select value={schedule} onChange={(event) => setSchedule(event.target.value as MonitorSchedule)}><option value="*/5 * * * *">每 5 分钟</option><option value="*/15 * * * *">每 15 分钟</option><option value="0 * * * *">每小时</option><option value="0 */4 * * *">每 4 小时</option><option value="0 0 * * *">每天 00:00</option></select></label>
              <label><span>时区</span><select value={timezone} onChange={(event) => setTimezone(event.target.value)}>{timezoneOptions(timezone).map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
              <label><span>有效期（本地时间）</span><input type="datetime-local" min={minimumExpiryLocal()} required value={expiresAtLocal} onChange={(event) => setExpiresAtLocal(event.target.value)} /></label>
              <fieldset className={styles.wideField}>
                <legend>静默时段</legend>
                <label className={styles.toggle}><input type="checkbox" checked={quietEnabled} onChange={(event) => setQuietEnabled(event.target.checked)} /><span className={styles.toggleTrack} aria-hidden="true"><span /></span><strong>{quietEnabled ? "已启用" : "未启用"}</strong></label>
              </fieldset>
              {quietEnabled ? (
                <>
                  <label><span>开始</span><input type="time" required value={quietStart} onChange={(event) => setQuietStart(event.target.value)} /></label>
                  <label><span>结束</span><input type="time" required value={quietEnd} onChange={(event) => setQuietEnd(event.target.value)} /></label>
                </>
              ) : null}
            </div>
          </section>

          <section className={styles.formSection} aria-labelledby="monitor-destinations-title">
            <div className={styles.sectionHeading}><span>04</span><div><h2 id="monitor-destinations-title">通知目标</h2><p>{parseDestinationIds(destinationIdsText).length} 个目标</p></div></div>
            <label className={styles.destinationInput}><span>Destination ID（每行一个，最多 8 个）</span><textarea rows={3} value={destinationIdsText} onChange={(event) => setDestinationIdsText(event.target.value)} placeholder="不填写则仅保留站内触发记录" /></label>
            <div className={styles.inlineNotice} role="status"><BellRing size={18} aria-hidden="true" /><span>通知目标由工作区设置管理。</span><Link href="/settings" prefetch={false}>打开通知设置</Link></div>
          </section>

          {submitError ? <div className={styles.submitError} role="alert"><CircleAlert size={18} aria-hidden="true" /><span>{submitError}</span></div> : null}

          <div className={styles.formActions}>
            <Link href={`/artifacts/${artifact.artifact_id}?version_number=${artifact.selected_version.version_number}`} prefetch={false}>取消</Link>
            <button type="submit" disabled={submitting} aria-busy={submitting}>
              {submitting ? <LoaderCircle className={styles.spinner} size={17} aria-hidden="true" /> : <CalendarClock size={17} aria-hidden="true" />}
              {submitting ? "正在创建" : "创建持续监控"}
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}

function sourceLoadErrorMessage(reason: unknown): string {
  if (reason instanceof ProductApiError) {
    if (reason.status === 401) return "登录状态已失效，请重新登录后再试。";
    if (reason.status === 403) return "当前工作区没有读取该报告的权限。";
    if (reason.status === 404) return "来源报告或版本不存在。";
    if (reason.status === 502) return "报告服务返回了无效响应，请稍后重试。";
    if (reason.status === 503) return "报告服务暂时不可用，请稍后重试。";
  }
  return monitorErrorMessage(reason, "无法核对来源报告，请稍后重试。");
}

function timezoneOptions(current: string): string[] {
  return [...new Set([current, "Asia/Shanghai", "UTC", "America/New_York", "Europe/London"])];
}

function parseDestinationIds(value: string): string[] {
  return value.split(/[\s,，]+/).map((item) => item.trim()).filter(Boolean);
}

function defaultExpiryLocal(): string {
  const expiry = new Date();
  expiry.setDate(expiry.getDate() + 30);
  expiry.setMinutes(expiry.getMinutes() - expiry.getTimezoneOffset());
  return expiry.toISOString().slice(0, 16);
}

function minimumExpiryLocal(): string {
  const minimum = new Date(Date.now() + 60 * 60 * 1000);
  minimum.setMinutes(minimum.getMinutes() - minimum.getTimezoneOffset());
  return minimum.toISOString().slice(0, 16);
}
