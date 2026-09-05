import { useState } from 'react';
import { API_BASE, deleteReport } from '../api/client';
import Modal from './Modal';

function timeAgo(dateString) {
  if (!dateString) return '';
  const then = new Date(dateString).getTime();
  const diffMs = Date.now() - then;
  const mins = Math.round(diffMs / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/**
 * report: { id, report_type, title, description, category, color, brand,
 *           location_name, item_datetime, status, created_at, reporter_id }
 * compact: hides the description (used in the Matches connector rows)
 * onFindMatches: optional. Shows a "Find matches" link that fires this
 * primaryAction: optional { label, onClick }. Shows a solid button in the
 *   footer (used for "Claim this item" so it reads as the card's main
 *   call to action, not a stray link floating outside the card)
 * currentUserId: id of the logged-in user, if any. Used to decide
 *   whether to show the Delete link (only the reporter sees it)
 * token: logged-in user's JWT, needed to authorize the delete call
 * onDeleted: called with report.id after a successful delete, so the
 *   parent list can remove the card from state
 */
export default function NoticeCard({
  report,
  compact = false,
  onFindMatches,
  primaryAction,
  currentUserId,
  token,
  onDeleted,
}) {
  const isFound = report.report_type === 'found';
  const thumbnail = report.photo_paths?.[0];
  const isEscalated = report.status === 'escalated';
  const isResolved = report.status === 'resolved';
  const photosRedacted = report.photos_redacted && thumbnail;
  const isOwner = Boolean(currentUserId) && report.reporter_id === currentUserId;
  const [photoOpen, setPhotoOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  async function confirmDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteReport(report.id, token);
      setConfirmOpen(false);
      onDeleted?.(report.id);
    } catch (err) {
      setDeleteError(err.message || 'Could not delete report.');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className={`notice-card ${isFound ? 'notice-card--found' : ''} ${compact ? 'notice-card--compact' : ''}`}>
      {thumbnail && (
        <>
          <button
            type="button"
            className="notice-photo-view-btn"
            onClick={() => setPhotoOpen(true)}
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
              <path
                d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
            </svg>
            {photosRedacted ? 'View photo (pixelated)' : 'View photo'}
          </button>

          {photoOpen && (
            <Modal
              onClose={() => setPhotoOpen(false)}
              labelledBy="photo-viewer-heading"
              className="modal-panel--photo"
            >
              {/* Visually hidden -- the dialog still needs an accessible
                  name, but a photo viewer doesn't need a visible title. */}
              <h2 id="photo-viewer-heading" className="sr-only">
                {report.title} photo
              </h2>
              <div className="photo-viewer">
                <img src={`${API_BASE}${thumbnail}`} alt="" />
                {photosRedacted && (
                  <span
                    className="notice-thumb-redacted-badge"
                    title="Photo is pixelated until a claim is verified, since this is a high-risk item"
                  >
                    Hidden until claimed
                  </span>
                )}
              </div>
            </Modal>
          )}
        </>
      )}
      <div className="notice-tag-row">
        <span className={`notice-tag ${isFound ? 'notice-tag--found' : 'notice-tag--lost'}`}>
          {isFound ? 'Found' : 'Lost'}
        </span>
        {report.is_high_risk && (
          <span className="notice-tag notice-tag--risk" title="ID, phone, or academic documents get priority handling">
            High-risk
          </span>
        )}
        {isEscalated && (
          <span className="notice-tag notice-tag--risk" title="Unclaimed for over a week">
            Escalated
          </span>
        )}
        {isResolved && (
          <span className="notice-tag notice-tag--resolved" title="Claimed and returned to its owner">
            Resolved
          </span>
        )}
      </div>
      <h3 className="notice-title">{report.title}</h3>
      {!compact && <p className="notice-desc">{report.description}</p>}
      {report.is_stale && !compact && (
        <p className="notice-stale-note">
          Still searching. Reported {report.days_open} days ago.
        </p>
      )}
      <dl className="notice-meta">
        {report.category && (
          <div>
            <dt>Category</dt>
            <dd>{report.category}</dd>
          </div>
        )}
        {report.location_name && (
          <div>
            <dt>Where</dt>
            <dd>{report.location_name}</dd>
          </div>
        )}
      </dl>
      <div className="notice-footer">
        <span>{timeAgo(report.created_at || report.item_datetime)}</span>
        {onFindMatches && report.status === 'open' && (
          <button type="button" className="notice-footer-link" onClick={onFindMatches}>
            Find matches →
          </button>
        )}
        {/* No delete once resolved -- the card is now part of the handover
            record the admin audits, so it must stay put. */}
        {isOwner && !isResolved && (
          <button
            type="button"
            className="notice-footer-link notice-footer-link--danger"
            onClick={() => {
              setDeleteError(null);
              setConfirmOpen(true);
            }}
          >
            Delete
          </button>
        )}
      </div>

      {confirmOpen && (
        <Modal onClose={() => !deleting && setConfirmOpen(false)} labelledBy="delete-confirm-heading">
          <h2 id="delete-confirm-heading" className="modal-heading">
            Delete this report?
          </h2>
          <p className="modal-text">
            “{report.title}” will be removed for good. This can’t be undone.
          </p>
          {deleteError && <p className="form-error">{deleteError}</p>}
          <div className="modal-actions">
            <button
              type="button"
              className="claim-form-cancel"
              onClick={() => setConfirmOpen(false)}
              disabled={deleting}
            >
              Cancel
            </button>
            <button
              type="button"
              className="submit-btn submit-btn--danger"
              onClick={confirmDelete}
              disabled={deleting}
            >
              {deleting ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </Modal>
      )}
      {primaryAction && (
        <button type="button" className="notice-primary-action" onClick={primaryAction.onClick}>
          {primaryAction.label}
        </button>
      )}
    </div>
  );
}