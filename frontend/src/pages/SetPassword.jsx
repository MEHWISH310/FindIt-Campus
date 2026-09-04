import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { setPassword as setPasswordApi, ApiError } from '../api/client';
import { useAuth } from '../context/AuthContext';
import PasswordInput from '../components/PasswordInput';

export default function SetPassword() {
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const { refreshUser } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setSubmitting(true);
    try {
      await setPasswordApi(newPassword);
      await refreshUser();
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not set your password.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="report-page auth-page">
      <form className="report-card" onSubmit={handleSubmit}>
        <h1 className="report-heading">Set a new password</h1>
        <p className="verification-note">
          You're using a temporary password. Set your own before continuing.
        </p>

        <label className="field">
          <span>New password</span>
          <PasswordInput
            required
            minLength={8}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
        </label>

        <label className="field">
          <span>Confirm new password</span>
          <PasswordInput
            required
            minLength={8}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
        </label>

        {error && <p className="form-error">{error}</p>}

        <button type="submit" className="submit-btn" disabled={submitting}>
          {submitting ? 'Saving…' : 'Save password'}
        </button>
      </form>
    </div>
  );
}