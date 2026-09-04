import { useState } from 'react';

/**
 * Drop-in replacement for <input type="password" ... /> with a built-in
 * show/hide eye toggle. Forwards every other prop straight through
 * (value, onChange, required, minLength, placeholder, autoFocus, etc.),
 * so existing password fields just swap the tag name -- see Login.jsx,
 * SetPassword.jsx, and ChangePasswordForm.jsx.
 */
export default function PasswordInput({ className = '', ...rest }) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="password-input">
      <input type={visible ? 'text' : 'password'} className={className} {...rest} />
      <button
        type="button"
        className="password-input-toggle"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
      >
        {visible ? (
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
            <path d="M3 3l18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <path
              d="M10.6 5.1A10.6 10.6 0 0 1 12 5c6.4 0 10 7 10 7a17.7 17.7 0 0 1-3.1 4.1M6.6 6.6C4 8.3 2 12 2 12s3.6 7 10 7a10.4 10.4 0 0 0 4.2-.9"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M9.9 9.9a3 3 0 0 0 4.2 4.2"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
            <path
              d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
          </svg>
        )}
      </button>
    </div>
  );
}