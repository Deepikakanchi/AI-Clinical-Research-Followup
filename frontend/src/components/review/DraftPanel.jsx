/*
 * components/review/DraftPanel.jsx - The AI draft (amber).
 * Shows SummaryOut exactly as stored. It is never edited: the reviewer writes the
 * final text separately, so the original draft can always be compared.
 */
import { AlertTriangle } from 'lucide-react';
import { dateTime } from '@/components/common/ui';

const SECTIONS = [
  ['recorded_observations', 'Recorded observations'],
  ['follow_up_actions', 'Follow-up actions'],
  ['missing_information', 'Missing information'],
];

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
      <h3>Visit summary</h3>
      <p>{d.visit_summary}</p>
      {SECTIONS.map(([key, label]) => (d[key]?.length > 0 ? (
        <div key={key} className={key === 'missing_information' ? 'missing-info' : ''}>
          <h3>{label}</h3>
          <ul>{d[key].map((item, i) => <li key={i}>{item}</li>)}</ul>
        </div>
      ) : null))}
      {d.follow_up_message_draft && (
        <>
          <h3>Follow-up message draft (never sent)</h3>
          <p>{d.follow_up_message_draft}</p>
        </>
      )}
      <p className="ai-disclaimer">AI-generated draft — not medical advice.</p>
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