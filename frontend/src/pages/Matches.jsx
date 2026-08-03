import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getReport, findMatches, ApiError } from '../api/client';
import NoticeCard from '../components/NoticeCard';

function ThreadRow({ match, sourceId, index }) {
  const [counterpart, setCounterpart] = useState(null);
  const [loading, setLoading] = useState(true);

  const counterpartId = match.lost_report_id === sourceId ? match.found_report_id : match.lost_report_id;
  const needsReview = match.status === 'NEEDS_DISAMBIGUATION' || match.status === 'needs_disambiguation';
  const pct = match.raw_score != null ? Math.round(match.raw_score * 100) : null;

  useEffect(() => {
    let cancelled = false;
    getReport(counterpartId)
      .then((r) => {
        if (!cancelled) setCounterpart(r);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [counterpartId]);

  return (
    <div
      className={`thread-row ${needsReview ? 'thread-row--review' : ''}`}
      style={{ '--card-index': index }}
    >
      {loading ? (
        <div className="thread-loading status-pulse">Loading counterpart report…</div>
      ) : counterpart ? (
        <NoticeCard report={counterpart} compact />
      ) : (
        <div className="thread-loading">Couldn't load that report.</div>
      )}

      <div className="thread-connector">
        <span className={`score-pill ${needsReview ? 'score-pill--warn' : ''} mono`}>
          {needsReview ? 'Needs review' : pct != null ? `${pct}%` : '—'}
        </span>
        {match.used_signals?.length > 0 && (
          <span className="signals">{match.used_signals.join(', ')}</span>
        )}
      </div>
    </div>
  );
}

export default function Matches() {
  const { reportId } = useParams();
  const [sourceReport, setSourceReport] = useState(null);
  const [matches, setMatches] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    getReport(reportId)
      .then((r) => {
        if (!cancelled) setSourceReport(r);
      })
      .catch(() => {});

    findMatches(reportId)
      .then((data) => {
        if (!cancelled) setMatches(data ?? []);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not run the matching engine.');
        }
      });

    return () => {
      cancelled = true;
    };
  }, [reportId]);

  return (
    <div className="matches-page">
      <Link to="/" className="back-link">
        ← Back
      </Link>

      <h1 className={`matches-heading ${sourceReport ? '' : 'status-pulse'}`}>
        {sourceReport ? <>Matches for “{sourceReport.title}”</> : 'Finding matches…'}
      </h1>

      {sourceReport && (
        <div className="source-card-wrap">
          <NoticeCard report={sourceReport} />
        </div>
      )}

      {error && <p className="matches-status matches-status--error">{error}</p>}

      {matches === null && !error && (
        <p className="matches-status status-pulse">Running the matching engine…</p>
      )}

      {matches && matches.length === 0 && (
        <p className="matches-status">
          No candidate matches yet — check back once more reports come in.
        </p>
      )}

      {matches && matches.length > 0 && (
        <div className="thread-list">
          {matches.map((m, i) => (
            <ThreadRow key={m.id} match={m} sourceId={reportId} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}