"use client";

import { AlertTriangle, CheckCircle2, Gauge, RefreshCw, Scale } from "lucide-react";
import { useEffect, useState } from "react";

import {
  getUsageGovernance,
  ProductApiError,
  reconcileUsage,
} from "@/lib/api/product-client";
import type { UsageGovernance, UsageTotals } from "@/lib/schemas/product-api";

const units: Array<{
  key: keyof UsageTotals;
  label: string;
  format: (value: number) => string;
}> = [
  { key: "agent_admission", label: "Agent admissions", format: compact },
  { key: "trigger", label: "Scheduled triggers", format: compact },
  { key: "model_token", label: "Model tokens", format: compact },
  { key: "search_request", label: "Search requests", format: compact },
  { key: "runtime_millisecond", label: "Runtime", format: duration },
  { key: "storage_byte", label: "Stored output", format: bytes },
];

export function UsageSurface() {
  const [view, setView] = useState<UsageGovernance | null>(null);
  const [loading, setLoading] = useState(true);
  const [reconciling, setReconciling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      setView(await getUsageGovernance());
    } catch (reason) {
      setError(messageFor(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    void getUsageGovernance()
      .then((result) => {
        if (active) setView(result);
      })
      .catch((reason: unknown) => {
        if (active) setError(messageFor(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function reconcile() {
    setReconciling(true);
    setError(null);
    try {
      await reconcileUsage();
      await load();
    } catch (reason) {
      setError(messageFor(reason));
    } finally {
      setReconciling(false);
    }
  }

  return (
    <div className="work-page usage-page">
      <header className="work-header">
        <div>
          <p className="section-kicker">Workspace governance</p>
          <h1>Usage and quotas</h1>
          <p>Current entitlement, immutable resource receipts, and reconciliation state.</p>
        </div>
        <button
          className="usage-reconcile-button"
          type="button"
          onClick={() => void reconcile()}
          disabled={loading || reconciling}
        >
          <Scale size={17} aria-hidden="true" />
          {reconciling ? "Reconciling" : "Reconcile"}
        </button>
      </header>

      {error ? (
        <section className="request-error" role="alert">
          <AlertTriangle size={20} aria-hidden="true" />
          <div><h2>Usage data unavailable</h2><p>{error}</p></div>
          <button className="submit-button" type="button" onClick={() => void load()}>
            <RefreshCw size={17} aria-hidden="true" /> Retry
          </button>
        </section>
      ) : null}

      {loading ? (
        <section className="empty-work-state" aria-live="polite">
          <span className="empty-state-line" aria-hidden="true" />
          <div><h2>Loading usage receipts</h2></div>
        </section>
      ) : null}

      {view ? (
        <>
          <section className="usage-summary" aria-labelledby="usage-summary-heading">
            <div className="usage-section-heading">
              <div>
                <p className="section-kicker">{formatMonth(view.period_start)}</p>
                <h2 id="usage-summary-heading">Resource totals</h2>
              </div>
              <span className={`usage-reconciliation-state is-${view.latest_reconciliation?.status ?? "pending"}`}>
                {view.latest_reconciliation?.status === "reconciled" ? (
                  <CheckCircle2 size={16} aria-hidden="true" />
                ) : (
                  <Gauge size={16} aria-hidden="true" />
                )}
                {view.latest_reconciliation?.status ?? "not reconciled"}
              </span>
            </div>
            <div className="usage-meter-list">
              {units.map((unit) => (
                <UsageMeter
                  key={unit.key}
                  label={unit.label}
                  value={view.totals[unit.key]}
                  limit={view.entitlement.limits[unit.key]}
                  format={unit.format}
                />
              ))}
            </div>
          </section>

          <section className="usage-policy" aria-labelledby="usage-policy-heading">
            <div className="usage-section-heading">
              <div><p className="section-kicker">Policy</p><h2 id="usage-policy-heading">Admission boundary</h2></div>
            </div>
            <dl>
              <div><dt>Task modes</dt><dd>{view.entitlement.allowed_task_types.join(", ")}</dd></div>
              <div><dt>Concurrent operations</dt><dd>{view.entitlement.max_concurrent_tasks}</dd></div>
              <div><dt>Active monitors</dt><dd>{view.entitlement.active_monitor_limit}</dd></div>
              <div><dt>Minimum interval</dt><dd>{duration(view.entitlement.min_interval_seconds * 1000)}</dd></div>
              <div><dt>Maximum retention</dt><dd>{view.entitlement.max_retention_days} days</dd></div>
            </dl>
          </section>

          {view.latest_reconciliation ? (
            <section className="usage-receipt" aria-labelledby="usage-receipt-heading">
              <div className="usage-section-heading">
                <div><p className="section-kicker">Immutable receipt</p><h2 id="usage-receipt-heading">Latest reconciliation</h2></div>
                <time dateTime={view.latest_reconciliation.created_at}>
                  {formatTime(view.latest_reconciliation.created_at)}
                </time>
              </div>
              <dl>
                <div><dt>Status</dt><dd>{view.latest_reconciliation.status}</dd></div>
                <div><dt>Source hash</dt><dd>{shortHash(view.latest_reconciliation.source_hash)}</dd></div>
                <div><dt>Ledger hash</dt><dd>{shortHash(view.latest_reconciliation.ledger_hash)}</dd></div>
                <div><dt>Repair</dt><dd>{view.latest_reconciliation.repair_applied ? "applied" : "audit only"}</dd></div>
              </dl>
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function UsageMeter({
  label,
  value,
  limit,
  format,
}: {
  label: string;
  value: number;
  limit: number;
  format: (value: number) => string;
}) {
  const ratio = limit > 0 ? Math.min(value / limit, 1) : value > 0 ? 1 : 0;
  return (
    <div className="usage-meter-row">
      <div><strong>{label}</strong><span>{format(value)} / {format(limit)}</span></div>
      <div className="usage-meter-track" aria-hidden="true">
        <span style={{ width: `${Math.max(ratio * 100, value > 0 ? 1 : 0)}%` }} />
      </div>
    </div>
  );
}

function compact(value: number) {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function duration(value: number) {
  const seconds = value / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${minutes.toFixed(1)}m`;
  return `${(minutes / 60).toFixed(1)}h`;
}

function bytes(value: number) {
  if (value < 1024) return `${value} B`;
  const labels = ["KB", "MB", "GB", "TB"];
  let amount = value;
  let index = -1;
  do {
    amount /= 1024;
    index += 1;
  } while (amount >= 1024 && index < labels.length - 1);
  return `${amount.toFixed(amount >= 10 ? 1 : 2)} ${labels[index]}`;
}

function formatMonth(value: string) {
  return new Intl.DateTimeFormat("en", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function shortHash(value: string) {
  return `${value.slice(0, 10)}...${value.slice(-8)}`;
}

function messageFor(reason: unknown) {
  return reason instanceof ProductApiError ? reason.message : "Unable to load workspace usage.";
}
