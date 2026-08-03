import { useTheme } from '../hooks/useTheme';

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="4.5" fill="currentColor" />
      <path
        d="M12 2.5v3M12 18.5v3M21.5 12h-3M5.5 12h-3M18.36 5.64l-2.12 2.12M7.76 16.24l-2.12 2.12M18.36 18.36l-2.12-2.12M7.76 7.76L5.64 5.64"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
      <path
        d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z"
        fill="currentColor"
      />
    </svg>
  );
}

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === 'light';

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggleTheme}
      aria-label={isLight ? 'Switch to dark mode' : 'Switch to light mode'}
      aria-pressed={isLight}
      title={isLight ? 'Switch to dark mode' : 'Switch to light mode'}
    >
      <span className="theme-toggle-track">
        <span className="theme-toggle-thumb">{isLight ? <SunIcon /> : <MoonIcon />}</span>
      </span>
    </button>
  );
}
