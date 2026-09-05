import { useCallback, useEffect, useState } from 'react';
import {
  listPendingPickups,
  confirmHandover,
  adminVerifyClaim,
  showToast,
  ApiError,
} from '../api/client';

const EMPTY_VERIFY = {
  match_id: '',
  claimant_name: '',
  claimant_registration_number: '',
  claimant_email: '',
  claimant_contact: '',
  notes: '',
};

/**
 * In-person verification: a student failed the online check (or used up
 * their 3 attempts and got locked out) but proved the item is theirs at
 * the desk. The admin fills the claimant's details in here; this stands in
 * for the answered verification question, so the match moves to VERIFIED
 * and shows up in the pickup queue below for the usual hand-over.
 */
function AdminVerifyForm({ onVerified }) {
  const [form, setForm] = useState(EMPTY_VERIFY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const set = (field, value) => setForm((f) => ({ ...f, [field]: value }));

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    const matchId = form.match_id.trim();
    const registrationNumber = form.claimant_registration_number.trim();
    const email = form.claimant_email.trim();
    if (!matchId || !form.claimant_name.trim() || !registrationNumber || !email) {
      setError('Match ref, claimant name, registration number, and email are required.');
      return;
    }
    setSubmitting(true);
    try {
      await adminVerifyClaim(matchId, {
        claimant_name: form.claimant_name.trim(),
        claimant_registration_number: registrationNumber.toUpperCase(),
        claimant_email: email,
        claimant_contact: form.claimant_contact.trim() || null,
        notes: form.notes.trim() || null,
      });
      setForm(EMPTY_VERIFY);
      showToast('Verified in person — the item is now ready for hand-over below.');
      onVerified();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not verify this claim.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <details className="admin-verify">
      <summary>Verify a claim in person</summary>
      <form className="stacked-form admin-verify-form" onSubmit={handleSubmit}>
        <p className="photo-hint">
          For a student who couldn't verify online. The match ref is shown on
          their matches page (labelled "ref"). This skips the hidden question —
          only do it once you've checked their ID against the item.
        </p>
        <label className="field">
          <span>Match ref *</span>
          <input
            value={form.match_id}
            onChange={(e) => set('match_id', e.target.value)}
            placeholder="e.g. 3f9c1a2b-…"
          />
        </label>
        <label className="field">
          <span>Claimant name *</span>
          <input value={form.claimant_name} onChange={(e) => set('claimant_name', e.target.value)} />
        </label>
        <div className="field-row">
          <label className="field">
            <span>Registration number *</span>
            <input
              value={form.claimant_registration_number}
              onChange={(e) => set('claimant_registration_number', e.target.value)}
              placeholder="23BCE0000"
              required
            />
          </label>
          <label className="field">
            <span>Email *</span>
            <input
              type="email"
              value={form.claimant_email}
              onChange={(e) => set('claimant_email', e.target.value)}
              required
            />
          </label>
          <label className="field">
            <span>Phone</span>
            <input value={form.claimant_contact} onChange={(e) => set('claimant_contact', e.target.value)} />
          </label>
        </div>
        <label className="field">
          <span>Notes</span>
          <input
            value={form.notes}
            onChange={(e) => set('notes', e.target.value)}
            placeholder="e.g. verified against student ID card"
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit" className="submit-btn" disabled={submitting}>
          {submitting ? 'Verifying…' : 'Verify & queue for hand-over'}
        </button>
      </form>
    </details>
  );
}

function formatDate(dateString) {
  if (!dateString) return '—';
  return new Date(dateString).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

/**
 * Renders a person's name + email + phone. Most seeded/legacy users have
 * no `name` set, so falling back to `person.name || person.email` for the
 * first line while ALSO printing `person.email` on the line below showed
 * the email twice. Only show the name line when a real name exists.
 */
function renderPerson(person) {
  if (!person) return '—';
  return (
    <>
      {person.name ? (
        <>
          {person.name}
          <br />
        </>
      ) : null}
      <span className="mono">{person.email}</span>
      {person.phone ? (
        <>
          <br />
          {person.phone}
        </>
      ) : null}
    </>
  );
}

/**
 * Admin-only dashboard: the queue of matches where the claimant already
 * answered the verification question correctly (status VERIFIED), but the
 * item is still sitting with admin -- nobody's clicked "handed over" yet.
 *
 * Each row shows the report's unique id (match_id) plus who found it and
 * who's coming to collect it, so admin can look the person up by id when
 * they show up at the collection point, confirm it's really them, and
 * click the button below -- that's the one action that actually resolves
 * the reports, writes the custody record, and emails the finder.
 */
export default function Admin() {
  const [pickups, setPickups] = useState(null);
  const [error, setError] = useState(null);
  const [confirmingId, setConfirmingId] = useState(null);

  const reload = useCallback(() => {
    listPendingPickups()
      .then((data) => setPickups(data ?? []))
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load pending pickups.'));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function handleConfirm(matchId) {
    setConfirmingId(matchId);
    setError(null);
    try {
      await confirmHandover(matchId);
      setPickups((current) => current.filter((p) => p.match_id !== matchId));
      showToast('Handover confirmed — the finder has been emailed.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not confirm handover.');
    } finally {
      setConfirmingId(null);
    }
  }

  return (
    <div className="page-shell dashboard">
      <div className="dashboard-head">
        <h1 className="dashboard-title">
          Ready for pickup
          {pickups && <span className="dashboard-count">{pickups.length}</span>}
        </h1>
      </div>

      <p className="dashboard-status" style={{ marginTop: 0 }}>
        Everyone here has already passed verification — online, or in person with an
        admin. When they come to collect, match their name to the Report ID, hand the
        item over, then click "Mark handed over", that closes both reports and emails
        the finder to confirm the item's been returned.
      </p>

      <AdminVerifyForm onVerified={reload} />

      {error && <p className="dashboard-status dashboard-status--error">{error}</p>}
      {!pickups && !error && <p className="dashboard-status status-pulse">Loading…</p>}
      {pickups && pickups.length === 0 && (
        <p className="dashboard-status">Nobody's waiting on a pickup right now.</p>
      )}

      {pickups && pickups.length > 0 && (
        <div className="custody-table-wrap">
          <table className="custody-table pickup-table">
            <thead>
              <tr>
                <th>Report ID</th>
                <th>Item</th>
                <th>Collection point</th>
                <th>Found by</th>
                <th>Collecting owner</th>
                <th>Verified</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {pickups.map((p) => (
                <tr key={p.match_id}>
                  <td className="mono">{p.match_id}</td>
                  <td>
                    {p.item_title}
                    {p.category ? ` (${p.category})` : ''}
                  </td>
                  <td>{p.collection_point || '—'}</td>
                  <td className="pickup-person">{renderPerson(p.finder)}</td>
                  <td className="pickup-person">{renderPerson(p.owner)}</td>
                  <td className="mono">{formatDate(p.verified_at)}</td>
                  <td>
                    <button
                      type="button"
                      className="submit-btn"
                      disabled={confirmingId === p.match_id}
                      onClick={() => handleConfirm(p.match_id)}
                    >
                      {confirmingId === p.match_id ? 'Confirming…' : 'Mark handed over'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}