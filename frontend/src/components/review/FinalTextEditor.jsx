/*
 * components/review/FinalTextEditor.jsx - Reviewer's decision (green), owned by Rajnish Maurya.
 * PATCH /api/summaries/{id}/review
 *   APPROVE: final text (20-4000) + comment + at least one follow-up action.
 *            The AI's proposed actions are pre-filled; the reviewer can edit, remove or add more.
 *   REJECT:  at least one reason why; no follow-up actions.
 * One decision per draft: once saved, the panel shows the recorded decision read-only.
 */
import { useState } from 'react';
import { CheckCircle2, Plus, X } from 'lucide-react';
import { api } from '@/api/client';
import { Badge, ErrorBanner, Field, SaveButton, dateTime, useSave } from '@/components/common/ui';

const MAX_ACTIONS = 10;
const MAX_REASONS = 10;

function RecordedDecision({ review }) {
  return (
    <>
      {review.decision === 'APPROVED'
        ? <div className="final-approved">REVIEWER-APPROVED</div>
        : <Badge value="REJECTED" />}
      {review.final_text && (<><h3>Final text</h3><p>{review.final_text}</p></>)}
      {review.final_follow_up_actions?.length > 0 && (
        <><h3>Follow-up actions</h3><ul>{review.final_follow_up_actions.map((a, i) => <li key={i}>{a}</li>)}</ul></>
      )}
      {review.rejection_reasons?.length > 0 && (
        <><h3>Reasons for rejection</h3><ul>{review.rejection_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul></>
      )}
      {review.reviewer_comment && (<><h3>Reviewer comment</h3><p>{review.reviewer_comment}</p></>)}
      {review.follow_up_flag && <p className="small"><strong>Flagged for qualified follow-up</strong></p>}
      <div className="review-meta">{review.reviewer_code}<br />{dateTime(review.reviewed_at)}</div>
    </>
  );
}

// An editable list of short lines (follow-up actions or rejection reasons).
function LineList({ label, items, setItems, max, placeholder, addLabel }) {
  return (
    <div className="line-list">
      <h3>{label}</h3>
      {items.map((value, i) => (
        <div className="action-input" key={i}>
          <Field label={`${label.replace(/s$/, '')} ${i + 1}`}>
            <input value={value} maxLength={200} placeholder={placeholder}
              onChange={e => setItems(items.map((x, j) => (j === i ? e.target.value : x)))} />
          </Field>
          <button type="button" className="btn btn-ghost btn-icon" aria-label={`Remove ${label.toLowerCase()} ${i + 1}`}
            onClick={() => setItems(items.filter((_, j) => j !== i))}><X size={16} /></button>
        </div>
      ))}
      <button type="button" className="btn btn-outline btn-sm" disabled={items.length >= max}
        onClick={() => setItems([...items, ''])}><Plus />{addLabel}</button>
    </div>
  );
}

export default function FinalTextEditor({ detail }) {
  const { summary, review } = detail;
  const save = useSave();
  const draft = summary.draft;
  const [decision, setDecision] = useState('APPROVED');
  const [finalText, setFinalText] = useState((draft?.summary_points || []).join(' '));
  const [comment, setComment] = useState('');
  const [actions, setActions] = useState(draft?.follow_up_actions?.length ? [...draft.follow_up_actions] : ['']);
  const [reasons, setReasons] = useState(['']);
  const [flag, setFlag] = useState(false);
  const [localError, setLocalError] = useState('');

  const clean = list => list.map(x => x.trim()).filter(Boolean);

  async function submit(event) {
    event.preventDefault();
    setLocalError('');
    if (decision === 'APPROVED') {
      if (finalText.trim().length < 20) return setLocalError('Final text must be at least 20 characters to approve.');
      if (!comment.trim()) return setLocalError('Add a comment before approving.');
      if (!clean(actions).length) return setLocalError('Add at least one follow-up action before approving.');
    } else if (!clean(reasons).length) {
      return setLocalError('Add at least one reason for rejecting.');
    }
    await save.run(() => api.reviewSummary(summary.summary_id, decision === 'APPROVED'
      ? { decision, final_text: finalText.trim(), reviewer_comment: comment.trim(), follow_up_actions: clean(actions), follow_up_flag: flag }
      : { decision, rejection_reasons: clean(reasons), reviewer_comment: comment.trim(), follow_up_flag: flag }));
  }

  let body;
  if (review) {
    body = <RecordedDecision review={review} />;
  } else if (summary.generation_status === 'FAILED') {
    body = <p className="muted">There is no draft to review. A new draft must be generated from the visit page.</p>;
  } else {
    const approving = decision === 'APPROVED';
    body = (
      <form onSubmit={submit}>
        <h3>Decision</h3>
        <div className="decision-options" role="radiogroup" aria-label="Decision">
          <label><input type="radio" name="decision" checked={approving} onChange={() => setDecision('APPROVED')} />Approve</label>
          <label><input type="radio" name="decision" checked={!approving} onChange={() => setDecision('REJECTED')} />Reject</label>
        </div>

        {approving ? (
          <>
            <Field label="Final text" name="final_text" error={save.error} helper="Edit the summary so it matches the source notes. 20–4000 characters.">
              <textarea maxLength={4000} value={finalText} onChange={e => setFinalText(e.target.value)} />
            </Field>
            <div className="counter">{finalText.length} / 4000</div>
            <LineList label="Follow-up actions" items={actions} setItems={setActions} max={MAX_ACTIONS}
              placeholder="e.g. Book the next follow-up visit" addLabel="Add follow-up action" />
          </>
        ) : (
          <LineList label="Reasons for rejection" items={reasons} setItems={setReasons} max={MAX_REASONS}
            placeholder="e.g. Sleep hours are not recorded in the note" addLabel="Add reason" />
        )}

        <Field label={`Reviewer comment${approving ? ' (required)' : ' (optional)'}`} name="reviewer_comment" error={save.error}>
          <textarea maxLength={1000} value={comment} onChange={e => setComment(e.target.value)} style={{ minHeight: 90 }} />
        </Field>

        <label className="check-label">
          <input type="checkbox" checked={flag} onChange={e => setFlag(e.target.checked)} />
          Flag for qualified follow-up
        </label>

        {localError && <div className="error-banner" role="alert"><span>{localError}</span></div>}
        {save.error?.status === 409
          ? <div className="warning-banner" role="alert">This draft has already been reviewed.</div>
          : <ErrorBanner error={save.error} />}
        <SaveButton busy={save.busy} className="btn-block"><CheckCircle2 />{approving ? 'Approve' : 'Reject'}</SaveButton>
      </form>
    );
  }

  return (
    <section className="review-panel final-panel" aria-label="Reviewer final">
      <header>
        <span>REVIEWER FINAL</span>
        <p>{review ? 'Recorded decision · read-only' : 'Your final record, follow-up actions and decision'}</p>
      </header>
      {body}
    </section>
  );
}