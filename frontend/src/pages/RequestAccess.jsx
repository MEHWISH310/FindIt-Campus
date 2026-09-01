import { useState } from 'react';
import { Link } from 'react-router-dom';
import { requestAccess, ApiError } from '../api/client';

export default function RequestAccess() {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await requestAccess(email.trim().toLowerCase());
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send access email.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="report-page">
      <div className="report-card">
        <h1 className="report-heading">Request access</h1>
        <p className="verification-note">
          For students who already have an account on FindIt Campus but have never logged in
          yet. Enter your @vitstudent.ac.in email and we'll send you a temporary password.
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
              {submitting ? 'Sending…' : 'Send temporary password'}
            </button>
          </form>
        )}

        <p className="verification-note">
          Already set a password before? <Link to="/login">Log in</Link>
        </p>
      </div>
    </div>
  );
}