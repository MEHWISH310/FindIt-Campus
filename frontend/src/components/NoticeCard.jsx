import { API_BASE } from '../api/client';

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
 *           location_name, item_datetime, status, created_at }
 * compact: hides the description (used in the Matches connector rows)
 * onFindMatches: optional — shows a "Find matches" link that fires this
 * primaryAction: optional { label, onClick } — shows a solid button in the
 *   footer (used for "Claim this item" so it reads as the card's main
 *   call to action, not a stray link floating outside the card)
 */
export default function NoticeCard({ report, compact = false, onFindMatches, primaryAction }) {
  const isFound = report.report_type === 'found';
  const thumbnail = report.photo_paths?.[0];
  const isEscalated = report.status === 'escalated';
  const isResolved = report.status === 'resolved';
  const photosRedacted = report.photos_redacted && thumbnail;

  return (
    <div className={`notice-card ${isFound ? 'notice-card--found' : ''} ${compact ? 'notice-card--compact' : ''}`}>
      {thumbnail && (
        <div className="notice-thumb">
          <img src={`${API_BASE}${thumbnail}`} alt="" className={photosRedacted ? 'notice-thumb-img--redacted' : ''} />
          {photosRedacted && (
            <span className="notice-thumb-redacted-badge" title="Photo is pixelated until a claim is verified, since this is a high-risk item">
              🔒 Hidden until claimed
            </span>
          )}
        </div>
      )}
      <div className="notice-tag-row">
        <span className={`notice-tag ${isFound ? 'notice-tag--found' : 'notice-tag--lost'}`}>
          {isFound ? 'Found' : 'Lost'}
        </span>
        {report.is_high_risk && (
          <span className="notice-tag notice-tag--risk" title="ID, phone, or academic documents get priority handling">
            ⚠ High-risk
          </span>
        )}
        {isEscalated && (
          <span className="notice-tag notice-tag--risk" title="Unclaimed for over a week">
            Escalated
          </span>
        )}
        {isResolved && (
          <span className="notice-tag notice-tag--resolved" title="Claimed and returned to its owner">
            ✅ Resolved
          </span>
        )}
      </div>
      <h3 className="notice-title">{report.title}</h3>
      {!compact && <p className="notice-desc">{report.description}</p>}
      {report.is_stale && !compact && (
        <p className="notice-stale-note">
          Still searching — reported {report.days_open} days ago
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
      </div>
      {primaryAction && (
        <button type="button" className="notice-primary-action" onClick={primaryAction.onClick}>
          {primaryAction.label}
        </button>
      )}
    </div>
  );
}