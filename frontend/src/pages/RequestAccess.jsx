import { useState } from 'react';
import { Link } from 'react-router-dom';
import { requestAccess, ApiError } from '../api/client';

/**
 * First-time "signup" for a student whose account row was already added
 * by an admin (email only, no password) but who's never logged in. They
 * prove they're the right person by supplying their registration number
 * -- whichever number is submitted first for a given email is what gets
 * recorded against it (see backend/app/routers/auth.py's request_access).
 */
export default function RequestAccess() {
  const [email, setEmail] = useState('');
  const [registrationNumber, setRegistrationNumber] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await requestAccess(email.trim().toLowerCase(), registrationNumber.trim().toUpperCase());
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send access email.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="report-page auth-page">
      <div className="report-card">
        <h1 className="report-heading">Sign up</h1>
        <p className="verification-note">
          Already added by an admin? Enter your email and registration number to get a
          temporary password.
        </p>

        {sent ? (
          <p className="claim-form-success-note">
            If that email/registration number is on file, a temporary password has been sent.
            Check your inbox, then <Link to="/login">log in</Link>.
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
                placeholder="name@vitstudent.ac.in or name@vit.ac.in"
              />
            </label>

            <label className="field">
              <span>Registration number</span>
              <input
                type="text"
                required
                value={registrationNumber}
                onChange={(e) => setRegistrationNumber(e.target.value)}
                placeholder="23BCE0000"
              />
            </label>

            {error && <p className="form-error">{error}</p>}

            <button type="submit" className="submit-btn" disabled={submitting}>
              {submitting ? 'Sending…' : 'Send temporary password'}
            </button>
          </form>
        )}

        <p className="verification-note">
          Already set a password before?{' '}
          <Link to="/login" className="auth-link-accent">
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}