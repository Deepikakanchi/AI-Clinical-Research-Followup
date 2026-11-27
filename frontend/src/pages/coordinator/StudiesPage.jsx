/*
 * pages/coordinator/StudiesPage.jsx - List and create fictional studies.
 * GET /api/studies, POST /api/studies (coordinators only). US-06.
 * Studies are shared reference data; reviewers are assigned per participant, not per study.
 */
import { useState } from 'react';
import { Plus } from 'lucide-react';
import { api } from '@/api/client';
import {
  Badge, DataTable, ErrorBanner, Field, LoadState, Modal, PageHeading, SaveButton, dateOnly, pretty, useApi, useSave,
} from '@/components/common/ui';

const EMPTY = { study_code: '', title: '', study_type: 'OBSERVATIONAL', active: true };

export default function StudiesPage() {
  const studies = useApi(['studies'], api.studies);
  const save = useSave();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [created, setCreated] = useState('');

  const set = (key, value) => setForm(f => ({ ...f, [key]: value }));

  function openForm() {
    setForm(EMPTY);
    save.setError(null);
    setOpen(true);
  }

  async function submit(event) {
    event.preventDefault();
    const body = { ...form, study_code: form.study_code.trim().toUpperCase(), title: form.title.trim() };
    const study = await save.run(() => api.createStudy(body));
    if (study) {
      setOpen(false);
      setCreated(`Study ${study.study_code} created.`);
    }
  }

  return (
    <>
      <PageHeading title="Studies" description="Fictional study protocols and registries.">
        <button className="btn" onClick={openForm}><Plus />New study</button>
      </PageHeading>

      {created && <div className="success-banner" role="status">{created}</div>}

      <LoadState query={studies}>
        <DataTable
          columns={['Study code', 'Title', 'Type', 'Participants', 'Created', 'Status']}
          rows={studies.data}
          empty="No studies yet."
          renderRow={s => (
            <tr key={s.study_id}>
              <td><strong>{s.study_code}</strong></td>
              <td className="table-title">{s.title}</td>
                            <td>{pretty(s.study_type)}</td>
              <td>
                <strong>{s.participant_count ?? 0}</strong>
                <span className="cell-sub">{s.active_participant_count ?? 0} active · {s.my_participant_count ?? 0} yours</span>
              </td>
              <td>{dateOnly(s.created_at)}</td>
              <td><Badge value={s.active ? 'ACTIVE' : 'INACTIVE'} /></td>
            </tr>
          )}
        />
      </LoadState>

      <Modal open={open} onClose={() => setOpen(false)} title="New study" description="Enter fictional study information only.">
        <form onSubmit={submit}>
          <Field label="Study code" name="study_code" error={save.error} helper="STD- followed by 3–20 capital letters, digits or hyphens, e.g. STD-DIA-03.">
            <input required pattern="STD-[A-Za-z0-9-]{3,20}" value={form.study_code} onChange={e => set('study_code', e.target.value)} />
          </Field>
          <Field label="Title" name="title" error={save.error}>
            <input required minLength={5} maxLength={150} value={form.title} onChange={e => set('title', e.target.value)} />
          </Field>
          <Field label="Study type" name="study_type" error={save.error}>
            <select value={form.study_type} onChange={e => set('study_type', e.target.value)}>
              <option value="OBSERVATIONAL">Observational</option>
              <option value="REGISTRY">Registry</option>
            </select>
          </Field>
          <label className="check-label">
            <input type="checkbox" checked={form.active} onChange={e => set('active', e.target.checked)} />
            Active study
          </label>
          <ErrorBanner error={save.error} />
          <div className="form-actions">
            <button type="button" className="btn btn-outline" onClick={() => setOpen(false)}>Cancel</button>
            <SaveButton busy={save.busy}>Create study</SaveButton>
          </div>
        </form>
      </Modal>
    </>
  );
}