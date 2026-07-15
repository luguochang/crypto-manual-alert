import { Suspense } from "react";

import { InboxSurface } from "@/features/inbox/inbox-surface";

export default function InboxPage() {
  return (
    <Suspense fallback={<InboxPageFallback />}>
      <InboxSurface />
    </Suspense>
  );
}

function InboxPageFallback() {
  return (
    <div className="work-page inbox-page" aria-busy="true">
      <div className="empty-work-state" aria-live="polite">
        <div>
          <h1>审核收件箱</h1>
          <p>正在同步审核队列。</p>
        </div>
      </div>
    </div>
  );
}
