import { useState } from 'react';
import { changePassword, ApiError } from '../api/client';

/**
 * The change-password form on its own -- no page chrome. Both entry points
 * (the profile page's "Reset password" modal and the standalone
 * /change-password route) render it with `bare`, so the UI never drifts.
 *
 * bare: drop the bordered card styling + built-in heading, so the caller
 *   can slot it into an existing container (a modal, a section).
 * onCancel: when given, renders a Cancel button beside the submit.
 * onSuccess: called after the password is successfully changed.
 */
export default function ChangePasswordForm({ bare = false, onCancel, onSuccess }) {
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New passwords don't match.");
      return;
    }

    setSubmitting(true);
    try {
      await changePassword(oldPassword, newPassword);
      setDone(true);
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
      onSuccess?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not change your password.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className={bare ? 'stacked-form' : 'report-card'} onSubmit={handleSubmit}>
      {!bare && <h2 className="report-heading">Change password</h2>}

      <label className="field">
        <span>Current password</span>
        <input
          type="password"
          required
          value={oldPassword}
          onChange={(e) => setOldPassword(e.target.value)}
        />
      </label>

      <label className="field">
        <span>New password</span>
        <input
          type="password"
          required
          minLength={8}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Confirm new password</span>
        <input
          type="password"
          required
          minLength={8}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
        />
      </label>

      {error && <p className="form-error">{error}</p>}
      {done && <p className="claim-form-success-note">Password changed.</p>}

      {bare ? (
        <div className="modal-actions">
          {onCancel && (
            <button type="button" className="claim-form-cancel" onClick={onCancel}>
              {done ? 'Close' : 'Cancel'}
            </button>
          )}
          <button type="submit" className="submit-btn" disabled={submitting}>
            {submitting ? 'Saving…' : 'Change password'}
          </button>
        </div>
      ) : (
        <button type="submit" className="submit-btn" disabled={submitting}>
          {submitting ? 'Saving…' : 'Change password'}
        </button>
      )}
    </form>
  );
}
