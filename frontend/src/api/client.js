// Thin wrapper around the FindIt Campus FastAPI backend.
// Set VITE_API_BASE_URL in your frontend/.env to override the default.

export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// A tiny event bus so components that don't share state (like the Header's
// nav counts and the report form) can stay in sync. Simpler than lifting
// state up through the whole app for something this small -- whenever a
// report is created, resolved, or claimed, we fire this event and anything
// listening (right now: Header's counts) refetches.
export const REPORTS_CHANGED_EVENT = 'findit:reports-changed';
function notifyReportsChanged() {
  window.dispatchEvent(new Event(REPORTS_CHANGED_EVENT));
}

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
export async function createReport(payload) {
  const report = await request('/reports/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  notifyReportsChanged(); // header's Lost/Found counts should bump immediately
  return report;
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

/**
 * POST /reports/{report_id}/photos — attach photos to an existing report.
 * `files` is a FileList or array of File objects (max 5, from ReportForm's
 * file input). Doesn't go through request() because we must NOT set a
 * Content-Type header here -- the browser sets its own multipart boundary
 * when it sees a FormData body, and overriding it breaks the upload.
 */
export async function uploadPhotos(reportId, files) {
  const formData = new FormData();
  Array.from(files).forEach((file) => formData.append('files', file));

  const res = await fetch(`${API_BASE}/reports/${reportId}/photos`, {
    method: 'POST',
    body: formData,
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
    const detail = (body && body.detail) || res.statusText || 'Photo upload failed';
    throw new ApiError(detail, res.status, body);
  }

  return body;
}

/**
 * POST /reports/escalate-stale — sweep FOUND high-risk reports unclaimed
 * for 7+ days and mark them ESCALATED. No scheduler is wired up yet, so
 * this is triggered manually via the "Run escalation check" button on
 * the Found dashboard rather than running automatically in the background.
 */
export function escalateStale() {
  return request('/reports/escalate-stale', { method: 'POST' });
}

/**
 * POST /matches/{match_id}/verify — submit a claim attempt (claimant_name,
 * claimant_contact, hidden_answer, notes). Returns { verified, message,
 * match, custody_record }. A wrong answer comes back as verified: false,
 * not a thrown error, so the form can show it inline and let them retry.
 * A correct answer resolves both reports, so we fire the reports-changed
 * event to bump counts back down (see Header.jsx).
 */
export async function claimMatch(matchId, payload) {
  const result = await request(`/matches/${matchId}/verify`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (result?.verified) {
    notifyReportsChanged();
  }
  return result;
}

/** GET /custody/ — the full handover log, for the "Claimed items" page. */
export function listCustodyRecords() {
  return request('/custody/');
}

export { ApiError };