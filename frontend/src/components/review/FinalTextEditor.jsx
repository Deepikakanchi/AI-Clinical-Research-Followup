/*
 * components/review/FinalTextEditor.jsx - Reviewer's decision (green).
 * PATCH /api/summaries/{id}/review  { decision, final_text, reviewer_comment, follow_up_flag }
 * - Approve needs final text of 20-4000 characters; Reject needs a comment.
 * - One decision per draft: once saved, the panel shows the recorded decision read-only.
 * - Only the assigned reviewer can save (the API returns 403/404 otherwise).
 */
import { useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { api } from '@/api/client';
import { Badge, ErrorBanner, Field, SaveButton, dateTime, useSave } from '@/components/common/ui';

function RecordedDecision({ review }) {
  return (
    <>
      {review.decision === 'APPROVED'
        ? <div className="final-approved">REVIEWER-APPROVED</div>
        : <Badge value="REJECTED" />}
      {review.final_text && (<><h3>Final text</h3><p>{review.final_text}</p></>)}
      {review.reviewer_comment && (<><h3>Reviewer comment</h3><p>{review.reviewer_comment}</p></>)}
      {review.follow_up_flag && <p className="small"><strong>Flagged for qualified follow-up</strong></p>}
      <div className="review-meta">{review.reviewer_code}<br />{dateTime(review.reviewed_at)}</div>
    </>
  );
}

export default function FinalTextEditor({ detail }) {
  const { summary, review } = detail;
  const save = useSave();
  const [decision, setDecision] = useState('APPROVED');
  const [finalText, setFinalText] = useState(summary.draft?.visit_summary || '');
  const [comment, setComment] = useState('');
  const [flag, setFlag] = useState(false);
  const [localError, setLocalError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setLocalError('');
    if (decision === 'APPROVED' && finalText.trim().length < 20) {
      setLocalError('Final text must be at least 20 characters to approve.');
      return;
    }
    if (decision === 'REJECTED' && !comment.trim()) {
      setLocalError('A comment is required when rejecting.');
      return;
    }
    await save.run(() => api.reviewSummary(summary.summary_id, {
      decision,
      final_text: decision === 'APPROVED' ? finalText.trim() : null,
      reviewer_comment: comment.trim(),
      follow_up_flag: flag,
    }));
  }

  let body;
  if (review) {
    body = <RecordedDecision review={review} />;
  } else if (summary.generation_status === 'FAILED') {
    body = <p className="muted">There is no draft to review. A new draft must be generated from the visit page.</p>;
  } else {
    body = (
      <form onSubmit={submit}>
        <Field label="Final text" name="final_text" error={save.error} helper="Edit the draft so it matches the source notes. 20–4000 characters.">
          <textarea maxLength={4000} value={finalText} onChange={e => setFinalText(e.target.value)} disabled={decision === 'REJECTED'} />
        </Field>
        <div className="counter">{finalText.length} / 4000</div>

        <h3>Decision</h3>
        <div className="decision-options" role="radiogroup" aria-label="Decision">
          <label><input type="radio" name="decision" checked={decision === 'APPROVED'} onChange={() => setDecision('APPROVED')} />Approve</label>
          <label><input type="radio" name="decision" checked={decision === 'REJECTED'} onChange={() => setDecision('REJECTED')} />Reject</label>
        </div>

        <Field label={`Reviewer comment${decision === 'REJECTED' ? ' (required)' : ' (optional)'}`} name="reviewer_comment" error={save.error}>
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
        <SaveButton busy={save.busy} className="btn-block"><CheckCircle2 />Save decision</SaveButton>
      </form>
    );
  }

  return (
    <section className="review-panel final-panel" aria-label="Reviewer final">
      <header>
        <span>REVIEWER FINAL</span>
        <p>{review ? 'Recorded decision · read-only' : 'Your final record and decision'}</p>
      </header>
      {body}
    </section>
  );
}