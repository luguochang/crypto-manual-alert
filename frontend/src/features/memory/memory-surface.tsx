"use client";

import { Brain, CircleAlert, RefreshCw, ToggleLeft, ToggleRight, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { deleteMemory, listMemory, ProductApiError, updateMemory } from "@/lib/api/product-client";
import type { Memory } from "@/lib/schemas/product-api";

const purposeLabels: Record<Memory["purpose"], string> = {
  session_clarification: "会话澄清",
  profile: "用户偏好",
  strategy_config: "策略配置",
  process_lesson: "流程经验",
  event: "时效事件",
  badcase: "问题样本",
};

export function MemorySurface() {
  const [items, setItems] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      setItems((await listMemory(true)).items);
    } catch (reason) {
      setError(reason instanceof ProductApiError ? reason.message : "无法读取记忆记录。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    void listMemory(true)
      .then((response) => { if (active) setItems(response.items); })
      .catch((reason: unknown) => {
        if (active) setError(
          reason instanceof ProductApiError ? reason.message : "无法读取记忆记录。",
        );
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function toggle(item: Memory) {
    setBusyId(item.id);
    try {
      const updated = await updateMemory(item.id, { enabled: !item.enabled });
      setItems((current) => current.map((entry) => entry.id === updated.id ? updated : entry));
    } catch (reason) {
      setError(reason instanceof ProductApiError ? reason.message : "无法更新记忆状态。");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(item: Memory) {
    if (!window.confirm(`删除记忆“${item.key}”？该操作会进入持久删除队列。`)) return;
    setBusyId(item.id);
    try {
      await deleteMemory(item.id);
      await reload();
    } catch (reason) {
      setError(reason instanceof ProductApiError ? reason.message : "无法提交删除请求。");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="work-page memory-page">
      <header className="work-header">
        <div><p className="section-kicker">Memory / Controls</p><h1>记忆管理</h1><p>管理可注入的会话与工作区记忆；已删除内容只保留审计状态。</p></div>
        <span className="boundary-label list-meta-label"><Brain size={17} aria-hidden="true" />{items.length} 条记录</span>
      </header>

      {error ? <section className="request-error" role="alert"><CircleAlert size={20} aria-hidden="true" /><div><h2>记忆操作失败</h2><p>{error}</p></div><button className="submit-button" type="button" onClick={() => void reload()}><RefreshCw size={17} aria-hidden="true" />重新读取</button></section> : null}
      {loading ? <section className="empty-work-state" aria-live="polite"><span className="empty-state-line" aria-hidden="true" /><div><h2>正在读取记忆</h2><p>同步 Product 数据库中的权限隔离记录。</p></div></section> : null}
      {!loading && items.length === 0 ? <section className="empty-work-state"><span className="empty-state-line" aria-hidden="true" /><div><h2>暂无记忆</h2><p>Agent 产生的可复用偏好和流程经验会显示在这里。</p></div></section> : null}

      {!loading && items.length > 0 ? <section className="memory-list" aria-label="记忆记录">
        {items.map((item) => <article className="memory-row" key={item.id} data-disabled={!item.enabled || undefined}>
          <div><span className="memory-purpose">{purposeLabels[item.purpose]}</span><h2>{item.key}</h2><p>{item.deleted_at ? "内容已删除" : summarize(item.content)}</p></div>
          <dl><div><dt>范围</dt><dd>{item.scope === "session" ? "会话" : "工作区"}</dd></div><div><dt>有效期</dt><dd>{item.expires_at ? formatDate(item.expires_at) : "长期"}</dd></div><div><dt>状态</dt><dd>{item.deleted_at ? "已删除" : item.enabled ? "启用" : "停用"}</dd></div></dl>
          <div className="memory-actions">
            {!item.deleted_at ? <button className="icon-action" type="button" disabled={busyId === item.id} onClick={() => void toggle(item)} title={item.enabled ? "停用记忆" : "启用记忆"}>{item.enabled ? <ToggleRight aria-hidden="true" /> : <ToggleLeft aria-hidden="true" />}</button> : null}
            {!item.deleted_at ? <button className="icon-action danger" type="button" disabled={busyId === item.id} onClick={() => void remove(item)} title="删除记忆"><Trash2 aria-hidden="true" /></button> : null}
          </div>
        </article>)}
      </section> : null}
    </div>
  );
}

function summarize(content: Record<string, unknown>): string {
  const entries = Object.entries(content);
  if (entries.length === 0) return "无可显示内容";

  const summary = entries
    .slice(0, 4)
    .map(([key, value]) => `${formatMemoryKey(key)}：${formatMemoryValue(value)}`)
    .join("；");
  const text = entries.length > 4 ? `${summary}；还有 ${entries.length - 4} 项` : summary;
  return text.length > 160 ? `${text.slice(0, 157)}...` : text;
}

function formatMemoryKey(key: string): string {
  return key.replaceAll("_", " ");
}

function formatMemoryValue(value: unknown): string {
  if (value === null || value === undefined) return "未设置";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.length === 0 ? "无" : `${value.length} 项`;
  if (typeof value === "object") return `${Object.keys(value).length} 个字段`;
  return "受保护内容";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
}
