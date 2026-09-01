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

// --- Auth token storage -----------------------------------------------
// Kept in localStorage (not sessionStorage) so logging in once survives
// closing the tab -- this is a real deployed app, not a Claude.ai
// artifact, so localStorage is the right, normal choice here.
const TOKEN_KEY = 'findit:auth_token';

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setAuthToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearAuthToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request(path, options = {}) {
  const token = getStoredToken();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
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

/**
 * POST /matches/{match_id}/disambiguate — forced-choice resolution when
 * multiple candidates were too close to auto-rank (status
 * NEEDS_DISAMBIGUATION). `matchId` is the one the user picked as theirs;
 * the backend promotes it back to a normal CANDIDATE and rejects the rest
 * of the competing cluster. Returns the updated cluster (List[MatchOut]).
 */
export function disambiguateMatch(matchId) {
  return request(`/matches/${matchId}/disambiguate`, { method: 'POST' });
}

export { ApiError };

// --- Auth ---------------------------------------------------------------

/** POST /auth/request-access — first-time signup: claims/verifies the
 * registration number against a pre-added account row. */
export function requestAccess(email, registrationNumber) {
  return request('/auth/request-access', {
    method: 'POST',
    body: JSON.stringify({ email, registration_number: registrationNumber }),
  });
}

/** POST /auth/forgot-password — already has an account, forgot the password. */
export function forgotPassword(email) {
  return request('/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

/** POST /auth/login — returns { access_token, must_set_password, user }. */
export function login(email, password) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

/** POST /auth/set-password — forced first-login / post-reset password set. */
export function setPassword(newPassword) {
  return request('/auth/set-password', {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  });
}

/** POST /auth/change-password — voluntary change, requires the old password. */
export function changePassword(oldPassword, newPassword) {
  return request('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });
}

/** GET /auth/me */
export function getMe() {
  return request('/auth/me');
}

/** PATCH /auth/me — update name/phone/registration_number. */
export function updateMe(payload) {
  return request('/auth/me', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/** GET /matches/{match_id} — single match, with found_contact/claimant_info
 * filled in when the logged-in user is authorized to see them. */
export function getMatch(matchId) {
  return request(`/matches/${matchId}`);
}