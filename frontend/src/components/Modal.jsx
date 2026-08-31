import { useEffect } from 'react';
import { createPortal } from 'react-dom';

/**
 * Generic centered popup: dims the page behind a backdrop, closes on
 * Escape or a backdrop click, and portals to document.body so it always
 * sits above the page regardless of where it's rendered in the tree
 * (e.g. inside a flex row like thread-row, where an inline element would
 * otherwise get squeezed into that row's layout).
 */
export default function Modal({ onClose, children, labelledBy }) {
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body
  );
}
