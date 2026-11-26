/*
 * pages/coordinator/VisitDetailPage.jsx - One visit: status changes, notes, AI draft state
 * and history, owned by Rajnish Maurya.
 *
 * Person 2's endpoints:
 *   GET   /api/visits/{id}          visit + draft_state
 *   PATCH /api/visits/{id}          reschedule or change status (the API enforces the rules)
 *   GET   /api/visits/{id}/notes    source notes, oldest first
 *   POST  /api/visits/{id}/notes    append a note (COMPLETED visits only)
 * Person 3's endpoints:
 *   POST  /api/visits/{id}/draft-summary   generate a DRAFT (stored even when it fails, without text)
 *   GET   /api/visits/{id}/summaries       draft history
 *   GET   /api/summaries/{summary_id}      latest draft + reviewer decision
 * Notes are append-only: there is no edit or delete.  US-12, US-15, US-16.
 */
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, CalendarClock, Loader2, Sparkles } from 'lucide-react';
import { api } from '@/api/client';
import {
  Badge, Empty, ErrorBanner, Field, History, LoadState, Modal, PageHeading, SaveButton,
  allowedStatusChanges, dateTime, localInputToIso, pretty, toLocalInput, useApi, useSave,
} from '@/components/common/ui';
import { DraftContent } from '@/components/review/DraftPanel';

const ACTIONS = {
  SCHEDULED: 'Reschedule',
  COMPLETED: 'Mark completed',
  MISSED: 'Mark missed',
  CANCELLED: 'Cancel visit',
};

const DRAFT_TEXT = {
  NO_NOTES: 'Add a visit note before an AI draft can be generated.',
  NOT_REQUESTED: 'No AI draft has been generated yet.',
  AWAITING_REVIEW: 'An AI draft is waiting for the assigned reviewer.',
  APPROVED: 'The reviewer approved a final summary for this visit.',
  REJECTED: 'The reviewer rejected the last draft. A new draft can be generated.',
  DRAFT_UNAVAILABLE: 'The last attempt failed. You can try again.',
  CONSENT_WITHDRAWN: 'Consent withdrawn — AI drafts are disabled.',
};
// States in which a new draft must NOT be requested; any other state (no draft yet,
// rejected, failed) allows one. The API checks consent and notes again anyway.
const BLOCKS_GENERATION = ['NO_NOTES', 'AWAITING_REVIEW', 'APPROVED', 'CONSENT_WITHDRAWN'];

// Notes hold observations only. 16,000 characters is about 4,000 tokens (~4 characters per token).
const NOTE_MAX = 16000;
const TOKENS_MAX = 4000;
const estimateTokens = text => Math.ceil(text.length / 4);

export default function VisitDetailPage() {
  const { id } = useParams();
  const visit = useApi(['visit', id], () => api.visit(id));
  const notes = useApi(['notes', id], () => api.notes(id));
  const summaries = useApi(['summaries', id], () => api.visitSummaries(id));
  const latest = summaries.data?.length
    ? [...summaries.data].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0]
    : null;
  const latestDetail = useApi(['summary', String(latest?.summary_id)], () => api.summary(latest.summary_id),
    { enabled: !!latest });
  const statusSave = useSave();
  const noteSave = useSave();
  const draftSave = useSave();

  const [action, setAction] = useState(null);          // which status change is being confirmed
  const [newTime, setNewTime] = useState('');
  const [observation, setObservation] = useState('');
  const v = visit.data;

  function startAction(target) {
    statusSave.setError(null);
    setNewTime('');
    setAction(target);
  }

  async function confirmAction(event) {
    event.preventDefault();
    const body = action === 'SCHEDULED' ? { scheduled_for: localInputToIso(newTime) } : { status: action };
    if (await statusSave.run(() => api.updateVisit(id, body))) setAction(null);
  }

  async function addNote(event) {
    event.preventDefault();
    const saved = await noteSave.run(() => api.addNote(id, {
      observation_text: observation.trim(),
    }));
    if (saved) setObservation('');
  }

  // A failed attempt is stored as a FAILED row too, so refresh the visit and its drafts either way.
  async function generate() {
    await draftSave.run(() => api.generateDraft(id));
    visit.refetch();
    summaries.refetch();
  }

  const draftError = draftSave.error;
  const aiNotReady = draftError && draftError.status === 405;
  const aiUnavailable = draftError && [502, 503, 504].includes(draftError.status);
  const canGenerate = v && v.status === 'COMPLETED' && !BLOCKS_GENERATION.includes(v.draft_state) && v.consent_status !== 'WITHDRAWN';

  return (
    <>
      <Link className="back-link" to="/coordinator/visits"><ArrowLeft size={14} />Visit schedule</Link>
      <LoadState query={visit} back="/coordinator/visits">
        {v && (
          <>
            <PageHeading title={`Visit · ${v.participant_code}`} description={`${pretty(v.visit_type)} visit${v.study_code ? ` · ${v.study_code}` : ''}`}>
              <div className="badge-pair"><Badge value={v.status} />{v.due_label && <Badge value={v.due_label} />}</div>
            </PageHeading>

            <div className="record-facts">
              <div><small>PARTICIPANT</small><Link to={`/coordinator/participants/${v.participant_id}`}><strong>{v.participant_code}</strong></Link></div>
              <div><small>DATE & TIME</small><strong>{dateTime(v.scheduled_for)}</strong></div>
              <div><small>VISIT TYPE</small><strong>{pretty(v.visit_type)}</strong></div>
              <div><small>COORDINATOR</small><strong>{v.coordinator_code}</strong></div>
              {v.reviewer_code && <div><small>REVIEWER</small><strong>{v.reviewer_code}</strong></div>}
              {v.consent_status && <div><small>CONSENT</small><Badge value={v.consent_status} /></div>}
            </div>

            {/* ---------- Status ---------- */}
            <section className="section-block">
              <h2>Status</h2>
              {allowedStatusChanges(v).length ? (
                <div className="action-row" style={{ marginTop: 14 }}>
                  {allowedStatusChanges(v).map(target => (
                    <button key={target} className={`btn ${target === 'CANCELLED' ? 'btn-outline' : 'btn-secondary'}`} onClick={() => startAction(target)}>
                      {target === 'SCHEDULED' && <CalendarClock />}{ACTIONS[target]}
                    </button>
                  ))}
                </div>
              ) : <p className="muted small">This visit is closed; its status can no longer change.</p>}
            </section>

            {/* ---------- Notes ---------- */}
            <section className="section-block">
              <div className="section-header"><h2>Visit notes</h2><span className="muted small">Append-only source documentation</span></div>
              <LoadState query={notes}>
                {notes.data?.length ? notes.data.map(n => (
                  <article className="source-note" key={n.note_id}>
                    <span className="eyebrow">SOURCE NOTE</span>
                    <p>{n.observation_text}</p>
                    {n.follow_up_actions?.length > 0 && (
                      <><strong className="small">Follow-up actions (older note)</strong>
                        <ul>{n.follow_up_actions.map((a, i) => <li key={i}>{a}</li>)}</ul></>
                    )}
                    <small>{n.author_code} · {dateTime(n.created_at)}</small>
                  </article>
                )) : <Empty text="No notes recorded for this visit." />}
              </LoadState>

              {v.status === 'COMPLETED' ? (
                <form className="note-form" onSubmit={addNote}>
                  <h3>Add a note</h3>
                  <div className="note-guidance">
                    <strong>How to write a good note</strong>
                    <ul>
                      <li>Write a complete note for this visit: the AI draft uses only the latest saved note.</li>
                      <li>Record only what was observed or reported, in short factual sentences.</li>
                      <li>Do not add follow-up actions here: the AI proposes up to 3 and the reviewer decides the final ones.</li>
                      <li>Avoid numbers unless needed, and never calculate totals.</li>
                      <li>No names, contact details or diagnoses: fictional information only.</li>
                    </ul>
                  </div>
                  <Field label="Observations" name="observation_text" error={noteSave.error}
                    helper={`20 to ${NOTE_MAX.toLocaleString()} characters (about ${TOKENS_MAX.toLocaleString()} tokens).`}>
                    <textarea required minLength={20} maxLength={NOTE_MAX} value={observation} onChange={e => setObservation(e.target.value)} />
                  </Field>
                  <div className="counter">
                    {observation.length.toLocaleString()} / {NOTE_MAX.toLocaleString()} characters · about {estimateTokens(observation).toLocaleString()} / {TOKENS_MAX.toLocaleString()} tokens
                  </div>
                  <div className="form-actions"><SaveButton busy={noteSave.busy}>Save note</SaveButton></div>
                </form>
              ) : <p className="muted small">Notes can be added once the visit is marked completed.</p>}
            </section>

            {/* ---------- AI draft ---------- */}
            <section className="section-block">
              <div className="section-header">
                <div><h2>AI draft</h2><p>Drafts are reviewed and approved by the assigned reviewer, never by the AI.</p></div>
                <button className="btn btn-outline" disabled={!canGenerate || draftSave.busy} onClick={generate}>
                  {draftSave.busy ? <Loader2 className="spin" /> : <Sparkles />}{draftSave.busy ? 'Generating…' : 'Generate AI draft'}
                </button>
              </div>
              <div className="badge-pair"><Badge value={v.draft_state} /></div>
              <p className="muted small">{DRAFT_TEXT[v.draft_state] || ''}</p>
              {aiUnavailable && (
                <div className="warning-banner" role="alert">
                  <AlertTriangle size={18} />Draft unavailable — try again later.
                  <button className="btn btn-outline btn-sm" onClick={generate}>Retry</button>
                </div>
              )}
              {aiNotReady && <div className="warning-banner" role="status"><AlertTriangle size={18} />AI drafting is not available yet in this build.</div>}
              {draftError && !aiUnavailable && !aiNotReady && <ErrorBanner error={draftError} />}

              {latest && (
                <>
                  <div className={latest.generation_status === 'FAILED' ? '' : 'draft-box'}>
                    {latest.generation_status !== 'FAILED' && <span className="eyebrow">LATEST AI DRAFT · NOT A CLINICAL DECISION</span>}
                    <DraftContent summary={latest} />
                  </div>
                  {latestDetail.data?.review && (
                    <div className={latestDetail.data.review.decision === 'APPROVED' ? 'approved-box' : 'source-note'}>
                      <span className="eyebrow">
                        {latestDetail.data.review.decision === 'APPROVED' ? 'REVIEWER-APPROVED RECORD' : 'REJECTED BY REVIEWER'}
                      </span>
                      {latestDetail.data.review.final_text && <p>{latestDetail.data.review.final_text}</p>}
                      {latestDetail.data.review.final_follow_up_actions?.length > 0 && (
                        <><strong className="small">Follow-up actions</strong>
                          <ul>{latestDetail.data.review.final_follow_up_actions.map((a, i) => <li key={i}>{a}</li>)}</ul></>
                      )}
                      {latestDetail.data.review.rejection_reasons?.length > 0 && (
                        <><strong className="small">Reasons for rejection</strong>
                          <ul>{latestDetail.data.review.rejection_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul></>
                      )}
                      {latestDetail.data.review.reviewer_comment && <p className="small">Comment: {latestDetail.data.review.reviewer_comment}</p>}
                      <small className="muted">{latestDetail.data.review.reviewer_code} · {dateTime(latestDetail.data.review.reviewed_at)}</small>
                    </div>
                  )}
                  {summaries.data.length > 1 && <p className="muted small">{summaries.data.length} drafts generated for this visit; the latest is shown.</p>}
                </>
              )}
            </section>

            <History entityType="visit" entityId={v.visit_id} />

            {/* ---------- Confirm status change ---------- */}
            <Modal open={!!action} onClose={() => setAction(null)} title={ACTIONS[action] || 'Update visit'} description={`Visit for ${v.participant_code} on ${dateTime(v.scheduled_for)}.`}>
              <form onSubmit={confirmAction}>
                {action === 'SCHEDULED' ? (
                  <Field label="New date and time" name="scheduled_for" error={statusSave.error} helper="Must be in the future.">
                    <input type="datetime-local" required min={toLocalInput()} value={newTime} onChange={e => setNewTime(e.target.value)} />
                  </Field>
                ) : (
                  <p>Mark this visit as <strong>{pretty(action)}</strong>? Closed visits cannot be changed again.</p>
                )}
                {statusSave.error?.status === 409
                  ? <div className="warning-banner" role="alert">{statusSave.error.message}</div>
                  : <ErrorBanner error={statusSave.error} />}
                <div className="form-actions">
                  <button type="button" className="btn btn-outline" onClick={() => setAction(null)}>Keep unchanged</button>
                  <SaveButton busy={statusSave.busy}>Confirm</SaveButton>
                </div>
              </form>
            </Modal>
          </>
        )}
      </LoadState>
    </>
  );
}