/*
 * components/review/DraftPanel.jsx - The AI draft (amber), owned by Rajnish Maurya.
 * Shows the stored draft exactly as the model produced it: up to 5 summary points
 * and up to 3 proposed follow-up actions. It is never edited: the reviewer writes
 * the final text and decides the follow-up actions separately.
 */
import { AlertTriangle } from 'lucide-react';
import { dateTime } from '@/components/common/ui';

// Body of a draft; also used on the coordinator's visit page.
export function DraftContent({ summary }) {
  if (summary.generation_status === 'FAILED' || !summary.draft) {
    return (
      <div className="warning-banner" role="status">
        <AlertTriangle size={18} />Draft unavailable{summary.error_code ? ` (${summary.error_code.replaceAll('_', ' ').toLowerCase()})` : ''}. No draft text was stored.
      </div>
    );
  }
  const d = summary.draft;
  return (
    <>
      <h3>Summary</h3>
      <ol className="summary-points">{(d.summary_points || []).map((p, i) => <li key={i}>{p}</li>)}</ol>
      <h3>Proposed follow-up actions</h3>
      {d.follow_up_actions?.length
        ? <ul>{d.follow_up_actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        : <p className="muted small">No follow-up actions proposed.</p>}
      <p className="ai-disclaimer">AI-generated draft — not medical advice. The reviewer decides the final follow-up actions.</p>
      <div className="review-meta">
        {[summary.deployment_name, summary.model_id].filter(Boolean).join(' / ')}
        <br />Created {dateTime(summary.created_at)}
        {summary.latency_ms != null && <> · {summary.latency_ms} ms</>}
      </div>
    </>
  );
}

export default function DraftPanel({ summary, reviewed }) {
  return (
    <section className="review-panel draft-panel" aria-label="AI draft">
      <header>
        <span>AI DRAFT</span>
        <p>{reviewed ? 'Original AI draft · unchanged' : 'AI DRAFT — not reviewed'}</p>
      </header>
      <DraftContent summary={summary} />
    </section>
  );
}