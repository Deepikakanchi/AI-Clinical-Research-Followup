/*
 * components/common/ui.jsx - Shared building blocks for every page.
 *
 * Formatting:  pretty, dateTime, dateOnly
 * Display:     Badge, Empty, ErrorBanner, LoadState, PageHeading, DataTable, History, ComingSoon
 * Forms:       Field, SaveButton, Modal, StudySelect
 * Data:        useApi (load), useSave (create / update, then refresh the page's data)
 */
import { Children, cloneElement, isValidElement, useEffect, useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, ArrowLeft, Construction, Inbox, Loader2, X } from 'lucide-react';
import { api } from '@/api/client';

/* ---------- Formatting ---------- */

// "FOLLOW_UP" -> "Follow Up"
export const pretty = text =>
  String(text ?? '').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase());

export const dateTime = value =>
  value
    ? new Date(value).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—';

export const dateOnly = value =>
  value ? new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';

/* ---------- Data hooks ---------- */

// Loads data and caches it under `key`. Returns React Query's result
// ({ data, isPending, error, refetch }).
export function useApi(key, loader, options = {}) {
  return useQuery({ queryKey: key, queryFn: loader, ...options });
}

// Runs a create/update call, keeps busy/error state, and refreshes all loaded
// data afterwards so every screen shows what is now in the database.
export function useSave() {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function run(call) {
    setBusy(true);
    setError(null);
    try {
      const result = await call();
      await queryClient.invalidateQueries();
      return result;
    } catch (err) {
      setError(err);
      return null;
    } finally {
      setBusy(false);
    }
  }

  return { run, busy, error, setError };
}

/* ---------- Display ---------- */

const BADGE_TEXT = { AI_DRAFT: 'AI draft', AWAITING_REVIEW: 'Awaiting review', UNAVAILABLE: 'Draft unavailable' };

export function Badge({ value }) {
  if (!value) return null;
  const css = `status-${String(value).toLowerCase().replaceAll('_', '-')}`;
  return <span className={`status-badge ${css}`}>{BADGE_TEXT[value] || pretty(value)}</span>;
}

export function Empty({ text = 'No records to display.' }) {
  return <div className="empty"><Inbox size={28} /><p>{text}</p></div>;
}

// Plain-language message for any API error.
export function errorMessage(error) {
  if (!error) return '';
  if (error.status === 403) return 'Not allowed for your role.';
  if (error.status === 404) return 'Record not found or not available to you.';
  return error.message;
}

export function ErrorBanner({ error }) {
  const [dismissed, setDismissed] = useState(null);
  if (!error || dismissed === error) return null;
  return (
    <div role="alert" className="error-banner">
      <AlertCircle size={18} />
      <span>{errorMessage(error)}</span>
      <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="Dismiss error" onClick={() => setDismissed(error)}>
        <X size={14} />
      </button>
    </div>
  );
}

// Shows a skeleton while loading, a not-found page for 404, an error with
// "Try again" for other failures, otherwise the children.
export function LoadState({ query, children, back }) {
  if (query.isPending) {
    return <div className="skeleton-list" aria-label="Loading">{[1, 2, 3].map(i => <div key={i} className="skeleton" />)}</div>;
  }
  if (query.error?.status === 404) {
    return (
      <div className="empty">
        <h2>Record not found or not available to you</h2>
        {back && <Link className="back-link" to={back}><ArrowLeft size={14} /> Go back</Link>}
      </div>
    );
  }
  if (query.error) {
    return (
      <>
        <ErrorBanner error={query.error} />
        <button className="btn btn-outline" onClick={() => query.refetch()}>Try again</button>
      </>
    );
  }
  return children;
}

export function PageHeading({ eyebrow = 'STUDY COORDINATION', title, description, children }) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {children && <div className="heading-actions">{children}</div>}
    </div>
  );
}

export function DataTable({ columns, rows, renderRow, empty }) {
  if (!rows?.length) return <Empty text={empty} />;
  return (
    <div className="table-scroll">
      <table>
        <thead><tr>{columns.map(c => <th key={c} scope="col">{c}</th>)}</tr></thead>
        <tbody>{rows.map(renderRow)}</tbody>
      </table>
    </div>
  );
}

// Audit history for one record (GET /api/audit-events).
export function History({ entityType, entityId }) {
  const q = useApi(['history', entityType, String(entityId)], () => api.auditEvents(entityType, entityId));
  return (
    <section className="section-block">
      <h2>History</h2>
      <LoadState query={q}>
        {!q.data?.length ? (
          <p className="muted small">No history recorded.</p>
        ) : (
          <ol className="timeline">
            {q.data.map(e => (
              <li key={e.event_id}>
                <strong>{pretty(e.action)}</strong>
                {(e.old_value || e.new_value) && <p>{e.old_value ? `${e.old_value} → ` : ''}{e.new_value}</p>}
                <small>{e.actor_code} · {dateTime(e.created_at)}</small>
              </li>
            ))}
          </ol>
        )}
      </LoadState>
    </section>
  );
}

// Placeholder for screens that come in a later batch.
export function ComingSoon({ title }) {
  return (
    <>
      <PageHeading title={title} />
      <div className="empty"><Construction size={28} /><p>This screen is added in the next step.</p></div>
    </>
  );
}

/* ---------- Forms ---------- */

// Messages from a FastAPI 422 detail list that belong to this field name.
function fieldErrors(error, name) {
  if (!name || !Array.isArray(error?.detail)) return [];
  return error.detail.filter(item => item.loc?.[item.loc.length - 1] === name).map(item => item.msg);
}

// Label + input + helper text + server errors, linked for screen readers.
export function Field({ label, name, error, helper, children }) {
  const id = useId();
  const messages = fieldErrors(error, name);
  const describedBy = helper || messages.length ? `${id}-help` : undefined;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {Children.map(children, (child, index) =>
        index === 0 && isValidElement(child)
          ? cloneElement(child, { id, 'aria-invalid': messages.length > 0 || undefined, 'aria-describedby': describedBy })
          : child,
      )}
      {describedBy && (
        <div id={describedBy}>
          {helper && <small>{helper}</small>}
          {messages.map(m => <small key={m} className="field-error">{m}</small>)}
        </div>
      )}
    </div>
  );
}

export function SaveButton({ busy, children = 'Save', disabled, className = '' }) {
  return (
    <button type="submit" className={`btn ${className}`} disabled={busy || disabled}>
      {busy && <Loader2 className="spin" />}
      {busy ? 'Saving…' : children}
    </button>
  );
}

// Simple accessible dialog: Escape or the backdrop closes it.
export function Modal({ open, onClose, title, description, children }) {
  const titleId = useId();
  useEffect(() => {
    if (!open) return undefined;
    const onKey = e => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <button type="button" className="btn btn-ghost btn-icon modal-close" aria-label="Close" onClick={onClose}><X size={16} /></button>
        <h2 id={titleId}>{title}</h2>
        {description && <p className="modal-description">{description}</p>}
        {children}
      </div>
    </div>
  );
}

// Study filter used on several pages ("" = all studies).
export function StudySelect({ value, onChange, allLabel = 'All studies' }) {
  const studies = useApi(['studies'], api.studies);
  return (
    <Field label="Study">
      <select value={value} onChange={e => onChange(e.target.value)}>
        <option value="">{allLabel}</option>
        {studies.data?.map(s => <option key={s.study_id} value={s.study_id}>{s.study_code} · {s.title}</option>)}
      </select>
    </Field>
  );
}



/* ---------- Date helpers for <input type="datetime-local"> ---------- */

// Date -> "YYYY-MM-DDTHH:mm" in the browser's local time (value for datetime-local inputs).
export function toLocalInput(date = new Date()) {
  const d = new Date(date);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

// "YYYY-MM-DDTHH:mm" (local) -> ISO string with timezone, as the API expects.
export const localInputToIso = value => new Date(value).toISOString();

/* ---------- Visit status actions ---------- */

// Which status changes the API allows for a visit. Uses the API's own list when it sends one;
// otherwise only SCHEDULED visits can change (the API still checks every change).
export function allowedStatusChanges(visit) {
  if (Array.isArray(visit?.allowed_status_changes)) return visit.allowed_status_changes;
  return visit?.status === 'SCHEDULED' ? ['SCHEDULED', 'COMPLETED', 'MISSED', 'CANCELLED'] : [];
}