import { useState } from 'react';
import { Link } from 'react-router-dom';
import { changePassword, ApiError } from '../api/client';

export default function ChangePassword() {
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
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not change your password.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="report-page">
      <Link to="/" className="back-link">
        ← Back
      </Link>
      <form className="report-card" onSubmit={handleSubmit}>
        <h1 className="report-heading">Change password</h1>

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
        {done && <p className="claim-form-success-note">✅ Password changed.</p>}

        <button type="submit" className="submit-btn" disabled={submitting}>
          {submitting ? 'Saving…' : 'Change password'}
        </button>
      </form>
    </div>
  );
}