import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { login as loginApi, ApiError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await loginApi(email.trim().toLowerCase(), password);
      login(res.access_token, res.user);

      if (res.must_set_password) {
        navigate('/set-password', { replace: true });
        return;
      }
      const redirectTo = location.state?.from || '/';
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not log in.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="report-page">
      <form className="report-card" onSubmit={handleSubmit}>
        <h1 className="report-heading">Log in</h1>
        <p className="verification-note">
          Use your @vitstudent.ac.in email. First time here? Use{' '}
          <Link to="/request-access">Request access</Link> to get a temporary password.
        </p>

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

        <label className="field">
          <span>Password</span>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {error && <p className="form-error">{error}</p>}

        <button type="submit" className="submit-btn" disabled={submitting}>
          {submitting ? 'Logging in…' : 'Log in'}
        </button>

        <p className="verification-note">
          Forgot your password? <Link to="/forgot-password">Reset it</Link>
        </p>
      </form>
    </div>
  );
}