"use client";

import { LogIn, LogOut, Plus, ShieldAlert, ShieldCheck } from "lucide-react";
import { signIn, signOut, useSession, SessionProvider } from "next-auth/react";
import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { BrandLockup } from "@/components/brand-lockup";
import { PrimaryNavigation } from "@/components/primary-navigation";
import { ShellTopbar } from "@/components/shell-topbar";
import {
  authContextListSchema,
  type AuthContext,
} from "@/lib/schemas/auth-context";


export function AuthenticatedAppShell({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <SessionProvider refetchInterval={5 * 60} refetchOnWindowFocus>
      <AuthenticatedShellContent>{children}</AuthenticatedShellContent>
    </SessionProvider>
  );
}

function AuthenticatedShellContent({ children }: Readonly<{ children: ReactNode }>) {
  const { data: session, status, update } = useSession();
  const [contexts, setContexts] = useState<AuthContext[] | null>(null);
  const [selectedContextId, setSelectedContextId] = useState("");
  const [contextError, setContextError] = useState("");
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    if (status !== "authenticated") return;
    const controller = new AbortController();
    const load = async () => {
      try {
        const response = await fetch("/api/product/api/v2/auth/contexts", {
          cache: "no-store",
          credentials: "same-origin",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("context discovery failed");
        const next = authContextListSchema.parse(await response.json()).items;
        setContexts(next);
        setContextError("");
        setSelectedContextId((current) => current || session.contextId || next[0]?.context_id || "");
      } catch (error) {
        if (!controller.signal.aborted) {
          setContexts((current) => current ?? []);
          setContextError(error instanceof Error ? "工作区暂时不可用" : "无法读取工作区");
        }
      }
    };
    void load();
    const interval = window.setInterval(load, 30_000);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [session?.contextId, status]);

  const currentContext = useMemo(
    () => contexts?.find((context) => context.context_id === session?.contextId) ?? null,
    [contexts, session?.contextId],
  );
  const hasActiveContext = status === "authenticated"
    && Boolean(session?.contextId)
    && (contexts === null || currentContext !== null);

  const switchContext = async () => {
    if (!selectedContextId || switching) return;
    setSwitching(true);
    setContextError("");
    try {
      const updated = await update({ contextId: selectedContextId });
      if (updated?.contextId !== selectedContextId) {
        throw new Error("context selection rejected");
      }
      window.location.assign("/work");
    } catch {
      setContextError("无法切换到该工作区");
      setSwitching(false);
    }
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside className="sidebar">
        <BrandLockup />
        <Link className="sidebar-primary-action" href="/work" prefetch={false}>
          <Plus size={17} aria-hidden="true" />
          新建分析
        </Link>
        <PrimaryNavigation />
        {status === "authenticated" ? (
          <div className="workspace-account">
            <label htmlFor="workspace-context">工作区</label>
            <select
              id="workspace-context"
              value={selectedContextId}
              onChange={(event) => setSelectedContextId(event.target.value)}
              disabled={!contexts?.length || switching}
            >
              {!contexts?.length ? <option value="">无可用工作区</option> : null}
              {contexts?.map((context) => (
                <option value={context.context_id} key={context.context_id}>
                  {context.tenant_name} / {context.workspace_name}
                </option>
              ))}
            </select>
            {selectedContextId && selectedContextId !== session.contextId ? (
              <button type="button" onClick={switchContext} disabled={switching}>
                {switching ? "切换中" : "切换"}
              </button>
            ) : null}
            <button
              className="account-signout"
              type="button"
              onClick={() => signOut({ callbackUrl: "/work" })}
              title="退出登录"
              aria-label="退出登录"
            >
              <LogOut size={16} aria-hidden="true" />
            </button>
            {contextError && hasActiveContext ? (
              <p className="workspace-account-error" role="alert">{contextError}</p>
            ) : null}
          </div>
        ) : null}
        <div className="environment-note">
          <ShieldCheck size={17} aria-hidden="true" />
          <span>
            <strong>{currentContext?.workspace_name ?? "Authenticated workspace"}</strong>
            {session?.user?.name ?? "受保护会话"}
          </span>
        </div>
      </aside>
      <div className="app-frame">
        <ShellTopbar />
        <main className="main-content" id="main-content" tabIndex={-1}>
          {status === "loading" ? <AccessState title="正在验证会话" /> : null}
          {status === "unauthenticated" ? (
            <AccessState
              title="登录 Signal Desk"
              action={(
                <button type="button" onClick={() => signIn("oidc")}>
                  <LogIn size={17} aria-hidden="true" />
                  登录
                </button>
              )}
            />
          ) : null}
          {status === "authenticated" && !hasActiveContext ? (
            <AccessState
              title={contexts?.length ? "选择工作区" : "没有可用工作区"}
              error={contextError || session.authContextError}
              action={contexts?.length ? (
                <button type="button" onClick={switchContext} disabled={!selectedContextId || switching}>
                  <ShieldCheck size={17} aria-hidden="true" />
                  {switching ? "正在进入" : "进入工作区"}
                </button>
              ) : undefined}
            />
          ) : null}
          {hasActiveContext ? <div key={session?.contextVersion}>{children}</div> : null}
        </main>
      </div>
    </div>
  );
}

function AccessState({
  title,
  error,
  action,
}: Readonly<{ title: string; error?: string; action?: ReactNode }>) {
  return (
    <section className="access-state" role="status">
      <ShieldAlert size={24} aria-hidden="true" />
      <h1>{title}</h1>
      {error ? <p>{error}</p> : null}
      {action}
    </section>
  );
}
