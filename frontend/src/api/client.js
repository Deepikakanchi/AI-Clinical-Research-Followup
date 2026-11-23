/*
 * api/client.js - Every call to the FastAPI backend.
 *
 * - The only file that knows the backend address (VITE_API_BASE_URL in .env).
 * - Adds "Authorization: Bearer <token>" to every request after login.
 * - Turns error responses into ApiError { status, message, detail }.
 *   detail is FastAPI's field list for 422 errors, so forms can show each
 *   message beside its field.
 * - A 401 on any request except login calls the sign-out handler.
 * Field names match openapi.yaml exactly; the screens use them as they are.
 */
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

let token = null;
let onUnauthorized = () => {};

export function setAuth(nextToken, unauthorizedHandler = () => {}) {
  token = nextToken;
  onUnauthorized = unauthorizedHandler;
}

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export async function request(path, { method = 'GET', body } = {}) {
  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  } catch {
    throw new ApiError('Unable to reach the server. Check that the backend is running.', 0);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === 'string' ? detail : 'Please check the highlighted fields.';
    if (response.status === 401 && path !== '/api/auth/login') onUnauthorized();
    throw new ApiError(message, response.status, detail);
  }
  return data;
}

// Builds "?a=1&b=2", skipping empty values.
export function qs(params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== '' && value !== null && value !== undefined),
  );
  const text = query.toString();
  return text ? `?${text}` : '';
}

export const api = {
  // ---- Auth (Person 1) ----
  login: (email, password) => request('/api/auth/login', { method: 'POST', body: { email, password } }),
  me: () => request('/api/auth/me'),

  // ---- Staff, studies, participants, audit (Person 1) ----
  reviewers: () => request('/api/staff'),
  studies: () => request('/api/studies'),
  createStudy: body => request('/api/studies', { method: 'POST', body }),
  participants: (params = {}) => request(`/api/participants${qs(params)}`),
  participant: id => request(`/api/participants/${id}`),
  registerParticipant: body => request('/api/participants', { method: 'POST', body }),
  changeConsent: (id, body) => request(`/api/participants/${id}/consent`, { method: 'PATCH', body }),
  auditEvents: (entityType, entityId) => request(`/api/audit-events${qs({ entity_type: entityType, entity_id: entityId })}`),

  // ---- Visits, notes, reports (Person 2) ----
  visits: (params = {}) => request(`/api/visits${qs(params)}`),
  visit: id => request(`/api/visits/${id}`),
  createVisit: body => request('/api/visits', { method: 'POST', body }),
  updateVisit: (id, body) => request(`/api/visits/${id}`, { method: 'PATCH', body }),
  notes: visitId => request(`/api/visits/${visitId}/notes`),
  addNote: (visitId, body) => request(`/api/visits/${visitId}/notes`, { method: 'POST', body }),
  followUpReport: (params = {}) => request(`/api/reports/follow-ups${qs(params)}`),
  followUpItems: (params = {}) => request(`/api/reports/follow-ups/items${qs(params)}`),

  // ---- AI drafts and review (Person 3) ----
  generateDraft: visitId => request(`/api/visits/${visitId}/draft-summary`, { method: 'POST' }),
  visitSummaries: visitId => request(`/api/visits/${visitId}/summaries`),
  summary: id => request(`/api/summaries/${id}`),
  reviewSummary: (id, body) => request(`/api/summaries/${id}/review`, { method: 'PATCH', body }),
  reviewQueue: (params = {}) => request(`/api/review-queue${qs(params)}`),

  health: () => request('/api/health'),
};