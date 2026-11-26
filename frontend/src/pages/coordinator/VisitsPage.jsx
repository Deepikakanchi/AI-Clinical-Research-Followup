/*
 * pages/coordinator/VisitsPage.jsx - Visit schedule and booking.
 * Uses Person 2's endpoints: GET /api/visits (filters run in SQL; only the logged-in
 * coordinator's visits) and POST /api/visits.  US-10, US-11, US-13.
 * The visit belongs to the logged-in coordinator; withdrawn participants cannot be booked.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Plus } from 'lucide-react';
import { api } from '@/api/client';
import { useAuth } from '@/components/common/AuthContext';
import {
  Badge, DataTable, ErrorBanner, Field, LoadState, Modal, PageHeading, SaveButton, StudySelect,
  dateTime, localInputToIso, pretty, toLocalInput, useApi, useSave,
} from '@/components/common/ui';

const NO_FILTERS = { study_id: '', status: '', from: '', to: '', view: 'all' };
const EMPTY_FORM = { participant_id: '', scheduled_for: '', visit_type: 'FOLLOW_UP' };

export default function VisitsPage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState(NO_FILTERS);
  const query = {
    ...filters,
    from: filters.from ? `${filters.from}T00:00:00` : '',
    to: filters.to ? `${filters.to}T23:59:59` : '',
    view: filters.view === 'all' ? '' : filters.view,
  };
  const visits = useApi(['visits', query], () => api.visits(query));
  const participants = useApi(['participants', ''], () => api.participants());
  const save = useSave();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [created, setCreated] = useState('');

  const setFilter = (key, value) => setFilters(f => ({ ...f, [key]: value }));
  const set = (key, value) => setForm(f => ({ ...f, [key]: value }));

  function openForm() {
    setForm(EMPTY_FORM);
    save.setError(null);
    setOpen(true);
  }

  async function submit(event) {
    event.preventDefault();
    const visit = await save.run(() => api.createVisit({
      participant_id: Number(form.participant_id),
      scheduled_for: localInputToIso(form.scheduled_for),
      visit_type: form.visit_type,
      coordinator_code: user.staff_code,      // always the logged-in coordinator
    }));
    if (visit) {
      setOpen(false);
      setCreated(`Visit scheduled for ${visit.participant_code} on ${dateTime(visit.scheduled_for)}.`);
    }
  }

  return (
    <>
      <PageHeading title="Visit schedule" description="Plan appointments and keep each visit up to date.">
        <button className="btn" onClick={openForm}><Plus />Schedule visit</button>
      </PageHeading>

      <div className="filters">
        <StudySelect value={filters.study_id} onChange={v => setFilter('study_id', v)} />
        <Field label="Status">
          <select value={filters.status} onChange={e => setFilter('status', e.target.value)}>
            <option value="">All statuses</option>
            {['SCHEDULED', 'COMPLETED', 'MISSED', 'CANCELLED'].map(s => <option key={s} value={s}>{pretty(s)}</option>)}
          </select>
        </Field>
        <Field label="Show">
          <select value={filters.view} onChange={e => setFilter('view', e.target.value)}>
            <option value="all">All visits</option>
            <option value="upcoming">Upcoming</option>
            <option value="due">Due (next 7 days)</option>
            <option value="overdue">Overdue</option>
          </select>
        </Field>
        <Field label="From date">
          <input type="date" value={filters.from} max={filters.to || undefined} onChange={e => setFilter('from', e.target.value)} />
        </Field>
        <Field label="To date">
          <input type="date" value={filters.to} min={filters.from || undefined} onChange={e => setFilter('to', e.target.value)} />
        </Field>
        <button className="btn btn-ghost btn-sm" onClick={() => setFilters(NO_FILTERS)}>Clear filters</button>
      </div>

      {created && <div className="success-banner" role="status">{created}</div>}

      <LoadState query={visits}>
        <DataTable
          columns={['Participant', 'Study', 'Date & time', 'Visit type', 'Reviewer', 'Status', '']}
          rows={visits.data}
          empty="No visits match these filters."
          renderRow={v => (
            <tr key={v.visit_id}>
              <td><Link to={`/coordinator/visits/${v.visit_id}`}>{v.participant_code}</Link></td>
              <td>{v.study_code}</td>
              <td>{dateTime(v.scheduled_for)}</td>
              <td>{pretty(v.visit_type)}</td>
              <td>{v.reviewer_code || '—'}</td>
              <td><div className="badge-pair"><Badge value={v.status} />{v.due_label && <Badge value={v.due_label} />}</div></td>
              <td><Link to={`/coordinator/visits/${v.visit_id}`} aria-label="Open visit"><ChevronRight size={16} /></Link></td>
            </tr>
          )}
        />
      </LoadState>

      <Modal open={open} onClose={() => setOpen(false)} title="Schedule visit" description={`Coordinator: ${user.staff_code}`}>
        <form onSubmit={submit}>
          <Field label="Participant" name="participant_id" error={save.error}>
            <select required value={form.participant_id} onChange={e => set('participant_id', e.target.value)}>
              <option value="">{participants.isPending ? 'Loading participants…' : 'Select a participant'}</option>
              {participants.data?.map(p => (
                <option key={p.participant_id} value={p.participant_id} disabled={p.consent_status === 'WITHDRAWN'}>
                  {p.participant_code} · {p.study_code}{p.consent_status === 'WITHDRAWN' ? ' (consent withdrawn)' : ''}
                </option>
              ))}
            </select>
          </Field>
          {participants.data && !participants.data.length && (
            <p className="muted small">You have no participants yet. <Link to="/coordinator/participants">Register a participant first.</Link></p>
          )}
          <Field label="Date and time" name="scheduled_for" error={save.error} helper="Must be in the future.">
            <input type="datetime-local" required min={toLocalInput()} value={form.scheduled_for} onChange={e => set('scheduled_for', e.target.value)} />
          </Field>
          <Field label="Visit type" name="visit_type" error={save.error}>
            <select value={form.visit_type} onChange={e => set('visit_type', e.target.value)}>
              <option value="BASELINE">Baseline</option>
              <option value="FOLLOW_UP">Follow-up</option>
              <option value="CLOSE_OUT">Close-out</option>
            </select>
          </Field>
          {save.error?.status === 409
            ? <div className="warning-banner" role="alert">{save.error.message}</div>
            : <ErrorBanner error={save.error} />}
          <div className="form-actions">
            <button type="button" className="btn btn-outline" onClick={() => setOpen(false)}>Cancel</button>
            <SaveButton busy={save.busy}>Schedule visit</SaveButton>
          </div>
        </form>
      </Modal>
    </>
  );
}