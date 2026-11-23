/*
 * components/review/SourceNotesPanel.jsx - Read-only source notes (grey).
 * The facts the AI draft must be grounded in. Never editable on the review screen.
 */
import { Empty } from '@/components/common/ui';

export function SourceNotes({ notes }) {
  if (!notes?.length) return <Empty text="No visit notes recorded." />;
  return notes.map(n => (
    <article className="source-note" key={n.note_id}>
      <span className="eyebrow">SOURCE NOTE</span>
      <p>{n.observation_text}</p>
      {n.follow_up_actions?.length > 0 && (
        <>
          <h3>Documented follow-up actions</h3>
          <ul>{n.follow_up_actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        </>
      )}
      {n.author_code && <small>{n.author_code}</small>}
    </article>
  ));
}

export default function SourceNotesPanel({ notes }) {
  return (
    <section className="review-panel source-panel" aria-label="Source notes">
      <header><span>SOURCE NOTES</span><p>Original study documentation · read-only</p></header>
      <SourceNotes notes={notes} />
    </section>
  );
}