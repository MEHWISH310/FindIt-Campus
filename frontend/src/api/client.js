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

export { ApiError };