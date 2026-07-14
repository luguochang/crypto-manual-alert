"use client";

import { CircleAlert, RotateCcw } from "lucide-react";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <section className="route-state" role="alert">
      <CircleAlert size={28} aria-hidden="true" />
      <h1>页面暂时无法加载</h1>
      <p>当前工作区遇到错误，请重试。</p>
      <button type="button" onClick={reset}>
        <RotateCcw size={18} aria-hidden="true" />
        重试
      </button>
    </section>
  );
}
