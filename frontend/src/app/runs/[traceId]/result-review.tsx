import type { ResultReview } from "@/lib/schemas/runs";
import { safeDisplayError } from "@/app/shared/safe-error";

type ResultReviewProps = {
  review: ResultReview;
};

function statusTone(status: string): string {
  if (status === "scorable") return "badge-success";
  if (status === "mock_visibility_only" || status === "pending") return "badge-pending";
  if (status === "unscorable") return "badge-failed";
  return "badge-neutral";
}

function primaryTitle(review: ResultReview): string {
  if (review.status === "not_collected") return "结果尚未生成";
  return review.label || "复盘状态已记录";
}

function sourceSummary(review: ResultReview): string {
  if (review.status === "not_collected") return "未采集";
  if (review.can_score) return "真实行情采集";
  if (review.status === "mock_visibility_only") return "本地展示样本";
  if (review.status === "pending") return "等待采集";
  return "不可评分样本";
}

function scoreSummary(review: ResultReview): string {
  if (review.status === "not_collected") return "未记录";
  if (review.can_score) return "可用于质量复盘";
  if (review.status === "pending") return "等待窗口成熟";
  return "不可评分";
}

export function ResultReviewCard({ review }: ResultReviewProps) {
  const firstItem = review.items[0];

  return (
    <section className="panel section-gap result-review" aria-label="后续复盘">
      <div className="panel-heading">
        <div>
          <h2>后续复盘</h2>
          <p>记录这条提醒在观察窗口内的后续表现；仅用于复盘，不代表自动下单或收益承诺。</p>
        </div>
        <span className={`badge ${statusTone(review.status)}`}>{review.label}</span>
      </div>

      <div className={`review-status-conclusion ${review.can_score ? "tone-ok" : review.status === "unscorable" ? "tone-danger" : "tone-warn"}`}>
        <strong>{primaryTitle(review)}</strong>
        <span>{safeDisplayError(review.message, "复盘状态已记录，详情可在工程日志中排查。")}</span>
      </div>

      <dl className="detail-list result-review-grid">
        <div>
          <dt>观察窗口</dt>
          <dd>{firstItem?.window_text ?? "等待观察窗口成熟"}</dd>
        </div>
        <div>
          <dt>入场状态</dt>
          <dd>{review.status === "not_collected" ? "未记录" : "已形成记录"}</dd>
        </div>
        <div>
          <dt>价格结果</dt>
          <dd>{firstItem?.price_result_text ?? "结果未记录"}</dd>
        </div>
        <div>
          <dt>复盘来源</dt>
          <dd>{firstItem?.source_label ?? sourceSummary(review)}</dd>
        </div>
        <div>
          <dt>评分状态</dt>
          <dd>{scoreSummary(review)}</dd>
        </div>
        <div>
          <dt>结果样本</dt>
          <dd>{review.sample_count} 条</dd>
        </div>
      </dl>

      {review.items.length > 0 ? (
        <div className="result-review-list" aria-label="复盘样本摘要">
          {review.items.slice(0, 3).map((item, index) => (
            <div key={`${item.target_label}-${item.window_text}-${index}`} className="result-review-item">
              <strong>{item.target_label}</strong>
              <span>{item.window_text}</span>
              <span>{item.unscored_label === "-" ? "已形成可评分结果样本" : item.unscored_label}</span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
