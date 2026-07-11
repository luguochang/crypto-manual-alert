"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createEvalRun } from "@/lib/api/eval";
import { safeDisplayError } from "@/app/shared/safe-error";

const EVAL_RUN_SAFE_ERROR = "复盘请求暂时无法完成，请稍后重试。";

export function RunEvalForm() {
  const router = useRouter();
  const [datasetName, setDatasetName] = useState("failure_cases");
  const [badcaseIds, setBadcaseIds] = useState("");
  const [mode, setMode] = useState("cheap");
  const [confirmedRealJudge, setConfirmedRealJudge] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function parseBadcaseIds(): number[] | undefined {
    const raw = badcaseIds.trim();
    if (!raw) {
      return undefined;
    }
    const tokens = raw.split(",").map((item) => item.trim());
    const parsed = tokens.map((item) => Number(item));
    const invalid = tokens.some((item, index) => item === "" || !Number.isInteger(parsed[index]) || parsed[index] <= 0);
    if (invalid) {
      throw new Error("Badcase IDs 只能填写英文逗号分隔的正整数，例如 12, 18, 23。");
    }
    return parsed;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsRunning(true);
    setMessage(null);
    setError(null);

    try {
      if (mode === "judge_openai" && !confirmedRealJudge) {
        throw new Error("选择 judge_openai 前，需要确认真实外部 judge 调用与可能成本。");
      }
      const parsedBadcaseIds = parseBadcaseIds();
      const result = await createEvalRun({
        dataset_name: datasetName.trim() || undefined,
        badcase_ids: parsedBadcaseIds,
        mode
      });
      if (!result.ok) {
        throw new Error(safeDisplayError(result.error, EVAL_RUN_SAFE_ERROR));
      }
      setMessage("Eval 已完成；生产配置、提醒发送和自动下单状态未被修改，页面已刷新到最新结果。");
      router.refresh();
    } catch (err) {
      setError(safeDisplayError(err, EVAL_RUN_SAFE_ERROR));
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
      <div className="field">
        <label htmlFor="eval-badcase-ids">Badcase IDs</label>
        <input
          id="eval-badcase-ids"
          name="badcase_ids"
          value={badcaseIds}
          onChange={(event) => setBadcaseIds(event.target.value)}
          placeholder="12, 18, 23"
        />
      </div>
      <div className="field">
        <label htmlFor="eval-mode">Mode</label>
        <select
          id="eval-mode"
          value={mode}
          onChange={(event) => {
            setMode(event.target.value);
            setConfirmedRealJudge(false);
          }}
        >
          <option value="cheap">cheap</option>
          <option value="judge_only_fixture">judge_only_fixture</option>
          <option value="judge_openai">judge_openai</option>
        </select>
      </div>
      {mode === "judge_openai" ? (
        <label className="eval-confirm-real-judge">
          <input
            type="checkbox"
            checked={confirmedRealJudge}
            onChange={(event) => setConfirmedRealJudge(event.target.checked)}
          />
          <span>
            我确认将调用真实 OpenAI-compatible judge，可能产生成本并向外部模型发送 eval 输入；这是旁路测评，不会修改生产提醒或自动下单。
          </span>
        </label>
      ) : null}
      <button className="button" disabled={isRunning || (mode === "judge_openai" && !confirmedRealJudge)} type="submit">
        {isRunning ? "运行中..." : mode === "judge_openai" ? "确认调用真实 judge" : mode === "judge_only_fixture" ? "运行本地替身 judge" : "运行规则 eval"}
      </button>
      {isRunning ? (
        <p className="async-progress" role="status" aria-label="复盘运行进度">
          正在运行复盘，请不要重复提交；这是旁路测评，不会修改生产提醒或自动下单。
        </p>
      ) : null}
      {message ? <p className="muted">{message}</p> : null}
      {error ? <p className="error-inline" role="alert">{error}</p> : null}
    </form>
  );
}
