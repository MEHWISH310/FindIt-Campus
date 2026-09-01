import { useState } from 'react';
import { Link } from 'react-router-dom';
import { forgotPassword, ApiError } from '../api/client';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await forgotPassword(email.trim().toLowerCase());
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send reset email.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="report-page">
      <div className="report-card">
        <h1 className="report-heading">Forgot password</h1>
        <p className="verification-note">
          Enter your @vitstudent.ac.in email and we'll send you a new temporary password. You'll
          be asked to set a new one after logging in with it.
        </p>

        {sent ? (
          <p className="claim-form-success-note">
            ✅ If that email has an account, a temporary password has been sent. Check your
            inbox, then <Link to="/login">log in</Link>.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="report-card" style={{ padding: 0, boxShadow: 'none', border: 'none' }}>
            <label className="field">
              <span>College email</span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you.2023@vitstudent.ac.in"
              />
            </label>

            {error && <p className="form-error">{error}</p>}

            <button type="submit" className="submit-btn" disabled={submitting}>
              {submitting ? 'Sending…' : 'Send reset password'}
            </button>
          </form>
        )}

        <p className="verification-note">
          Remembered it? <Link to="/login">Log in</Link>
        </p>
      </div>
    </div>
  );
}