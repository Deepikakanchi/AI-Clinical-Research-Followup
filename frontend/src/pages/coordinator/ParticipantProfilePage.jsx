/*
 * pages/coordinator/ParticipantProfilePage.jsx - One participant's record, consent and history, US-08, US-09, US-30.
 *
 * GET /api/participants/{id}             -> profile + visits (newest first)
 * PATCH /api/participants/{id}/consent   -> change consent (owning coordinator only)
 * GET /api/audit-events                  -> history
 * A participant owned by another coordinator returns 404, shown as "not available to you".
 * There is no delete button: withdrawal is the only way to stop processing.
 */
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ChevronRight, ShieldAlert } from 'lucide-react';
import { api } from '@/api/client';
import {
  Badge, DataTable, ErrorBanner, History, LoadState, Modal, PageHeading, SaveButton, dateOnly, dateTime, pretty, useApi, useSave,
} from '@/components/common/ui';

export default function ParticipantProfilePage() {
  const { id } = useParams();
  const participant = useApi(['participant', id], () => api.participant(id));
  const save = useSave();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const p = participant.data;
  const nextConsent = p?.consent_status === 'ACTIVE' ? 'WITHDRAWN' : 'ACTIVE';

  async function changeConsent(event) {
    event.preventDefault();
    if (await save.run(() => api.changeConsent(id, { consent_status: nextConsent }))) setConfirmOpen(false);
  }

  return (
    <>
      <Link className="back-link" to="/coordinator/participants"><ArrowLeft size={14} />Participants</Link>
      <LoadState query={participant} back="/coordinator/participants">
        {p && (
          <>
            <PageHeading title={p.participant_code} description={`Participant record · ${p.study_code}`}>
              <button className="btn btn-outline" onClick={() => { save.setError(null); setConfirmOpen(true); }}>
                {p.consent_status === 'ACTIVE' ? 'Withdraw consent' : 'Re-activate consent'}
              </button>
            </PageHeading>

            {p.consent_status === 'WITHDRAWN' && (
              <div className="warning-banner" role="status">
                <ShieldAlert size={18} />Consent withdrawn — new visits and AI drafts are disabled for this participant.
              </div>
            )}

            <div className="record-facts">
              <div><small>STUDY</small><strong>{p.study_code}</strong></div>
              <div><small>CONSENT</small><Badge value={p.consent_status} /></div>
              <div><small>CONSENT UPDATED</small><strong>{dateTime(p.consent_updated_at)}</strong></div>
              <div><small>COORDINATOR</small><strong>{p.coordinator_code}</strong></div>
              <div><small>REVIEWER</small><strong>{p.reviewer_code}</strong></div>
              <div><small>ENROLLED</small><strong>{dateOnly(p.enrolled_at)}</strong></div>
            </div>

            <section className="section-block">
              <div className="section-header"><h2>Visits</h2><span className="muted small">Newest first</span></div>
              <DataTable
                columns={['Date & time', 'Visit type', 'Coordinator', 'Status', '']}
                rows={p.visits}
                empty="No visits scheduled yet."
                renderRow={v => (
                  <tr key={v.visit_id}>
                    <td>{dateTime(v.scheduled_for)}</td>
                    <td>{pretty(v.visit_type)}</td>
                    <td>{v.coordinator_code}</td>
                    <td><Badge value={v.status} /></td>
                    <td><Link to={`/coordinator/visits/${v.visit_id}`} aria-label="Open visit"><ChevronRight size={16} /></Link></td>
                  </tr>
                )}
              />
            </section>

            <History entityType="participant" entityId={p.participant_id} />

            <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)}
              title={nextConsent === 'WITHDRAWN' ? 'Withdraw consent?' : 'Re-activate consent?'}
              description={nextConsent === 'WITHDRAWN'
                ? `${p.participant_code} will be marked WITHDRAWN. New visits and AI drafts will be blocked. The change is recorded in the history.`
                : `${p.participant_code} will be marked ACTIVE again. The change is recorded in the history.`}>
              <form onSubmit={changeConsent}>
                <ErrorBanner error={save.error} />
                <div className="form-actions">
                  <button type="button" className="btn btn-outline" onClick={() => setConfirmOpen(false)}>Keep current consent</button>
                  <SaveButton busy={save.busy} className={nextConsent === 'WITHDRAWN' ? 'btn-danger' : ''}>
                    {nextConsent === 'WITHDRAWN' ? 'Withdraw consent' : 'Re-activate consent'}
                  </SaveButton>
                </div>
              </form>
            </Modal>
          </>
        )}
      </LoadState>
    </>
  );
}