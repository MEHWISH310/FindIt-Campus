// Thin wrapper around the FindIt Campus FastAPI backend.
// Set VITE_API_BASE_URL in your frontend/.env to override the default.

export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  let body = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    const detail = (body && body.detail) || res.statusText || 'Request failed';
    throw new ApiError(detail, res.status, body);
  }

  return body;
}

/** POST /reports/  — create a lost or found report. */
export function createReport(payload) {
  return request('/reports/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** GET /reports/  — optionally filtered by report_type ('lost' | 'found'). */
export function listReports(reportType) {
  const qs = reportType ? `?report_type=${encodeURIComponent(reportType)}` : '';
  return request(`/reports/${qs}`);
}

/** GET /reports/{id} */
export function getReport(reportId) {
  return request(`/reports/${reportId}`);
}

/** POST /matches/find/{report_id} — run the AI matching pipeline for a report. */
export function findMatches(reportId) {
  return request(`/matches/find/${reportId}`, { method: 'POST' });
}

export { ApiError };