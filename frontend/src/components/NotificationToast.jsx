import { useEffect, useState } from 'react';
import { socket } from '../api/socket';
import { REPORTS_CHANGED_EVENT, TOAST_EVENT } from '../api/client';

// One entry per backend event (see backend/app/realtime.py's docstring for
// the full list) -- `render` turns the event payload into a human message.
// `silent: true` means we still listen (to keep Header's counts live) but
// don't surface a toast for it.
const EVENT_RENDERERS = [
  {
    name: 'report:created',
    silent: true,
  },
  {
    name: 'match:found',
    render: (d) =>
      `Strong match found for "${d.report_title}" (${Math.round((d.probability ?? d.score) * 100)}%)`,
  },
  {
    name: 'report:escalated',
    render: (d) => `${d.count} unclaimed high-risk item${d.count === 1 ? '' : 's'} escalated`,
  },
  {
    name: 'item:claimed',
    render: (d) => `"${d.item_name}" claimed by ${d.claimant_name}`,
  },
];

const TOAST_LIFETIME_MS = 6000;
let idCounter = 0;

/**
 * Mounted once near the app root (see App.jsx). Renders nothing when there's
 * nothing to show. On every live event it also re-fires the same
 * REPORTS_CHANGED_EVENT that REST calls use (see client.js), so Header's
 * counts stay live even when the change happened in a different tab or
 * from a different person entirely -- not just the tab that made the call.
 */
export default function NotificationToast() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    function pushToast(message) {
      const id = ++idCounter;
      setToasts((current) => [...current, { id, message }]);
      setTimeout(() => {
        setToasts((current) => current.filter((t) => t.id !== id));
      }, TOAST_LIFETIME_MS);
    }

    const bound = EVENT_RENDERERS.map(({ name, render, silent }) => {
      const handler = (data) => {
        if (!silent) {
          let message;
          try {
            message = render(data);
          } catch {
            message = 'Update received';
          }
          pushToast(message);
        }
        window.dispatchEvent(new Event(REPORTS_CHANGED_EVENT));
      };
      socket.on(name, handler);
      return { name, handler };
    });

    // Locally-triggered toasts (client.js's showToast) -- e.g. the admin
    // confirming a handover -- land in the same stack.
    const onLocalToast = (e) => pushToast(e.detail?.message ?? 'Done');
    window.addEventListener(TOAST_EVENT, onLocalToast);

    return () => {
      bound.forEach(({ name, handler }) => socket.off(name, handler));
      window.removeEventListener(TOAST_EVENT, onLocalToast);
    };
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className="toast">
          {t.message}
        </div>
      ))}
    </div>
  );
}