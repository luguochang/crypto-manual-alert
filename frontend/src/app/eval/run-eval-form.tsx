"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

type ApiEnvelope = {
  ok: boolean;
  data?: unknown;
  error?: {
    code?: string;
    message: string;
  } | null;
};

function getApiBaseUrl() {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    throw new Error("缺少 NEXT_PUBLIC_API_BASE_URL");
  }
  return baseUrl.replace(/\/$/, "");
}

export function RunEvalForm() {
  const router = useRouter();
  const [datasetName, setDatasetName] = useState("failure_cases");
  const [isRunning, setIsRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsRunning(true);
    setMessage(null);
    setError(null);

    try {
      const response = await fetch(`${getApiBaseUrl()}/api/eval/runs`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          dataset_name: datasetName.trim() || undefined,
          mode: "judge_only_fixture"
        })
      });
      const body = (await response.json()) as ApiEnvelope;
      if (!response.ok || !body.ok) {
        throw new Error(body.error?.message ?? `请求失败：HTTP ${response.status}`);
      }
      setMessage("Eval 已完成，页面已刷新到最新结果。");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Eval 触发失败");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <form className="eval-run-form" onSubmit={handleSubmit}>
      <div className="field">
        <label htmlFor="eval-dataset">Dataset</label>
        <input
          id="eval-dataset"
          name="dataset"
          value={datasetName}
          onChange={(event) => setDatasetName(event.target.value)}
          placeholder="failure_cases"
        />
      </div>
      <button className="button" disabled={isRunning} type="submit">
        {isRunning ? "运行中..." : "运行 fixture eval"}
      </button>
      {message ? <p className="muted">{message}</p> : null}
      {error ? <p className="error-inline">{error}</p> : null}
    </form>
  );
}
