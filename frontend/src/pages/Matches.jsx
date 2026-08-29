import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getReport, findMatches, claimMatch, ApiError } from '../api/client';
import NoticeCard from '../components/NoticeCard';

/**
 * Inline claim/verification form. Only ever shown for a FOUND counterpart
 * report -- the claimant is proving the item is theirs by answering the
 * finder's hidden_question (asymmetric verification, per the abstract).
 */
function ClaimForm({ match, foundReport, onClaimed }) {
  const [open, setOpen] = useState(false);
  const [claimantName, setClaimantName] = useState('');
  const [claimantContact, setClaimantContact] = useState('');
  const [hiddenAnswer, setHiddenAnswer] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // { verified, message } | null
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res = await claimMatch(match.id, {
        claimant_name: claimantName.trim(),
        claimant_contact: claimantContact.trim() || null,
        hidden_answer: hiddenAnswer,
      });
      setResult(res);
      if (res.verified) {
        onClaimed?.();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not submit the claim.');
    } finally {
      setSubmitting(false);
    }
  }

  if (result?.verified) {
    return (
      <div className="claim-form claim-form--success">
        <p>✅ {result.message}</p>
      </div>
    );
  }

  if (!open) {
    return (
      <button type="button" className="notice-footer-link claim-toggle" onClick={() => setOpen(true)}>
        Claim this item →
      </button>
    );
  }

  return (
    <form className="claim-form" onSubmit={handleSubmit}>
      <p className="claim-form-question">
        <strong>Verification question:</strong> {foundReport.hidden_question || 'No question set for this report.'}
      </p>

      <label>
        Your name
        <input
          type="text"
          value={claimantName}
          onChange={(e) => setClaimantName(e.target.value)}
          required
        />
      </label>

      <label>
        Contact (phone/email, optional)
        <input
          type="text"
          value={claimantContact}
          onChange={(e) => setClaimantContact(e.target.value)}
        />
      </label>

      <label>
        Your answer
        <input
          type="text"
          value={hiddenAnswer}
          onChange={(e) => setHiddenAnswer(e.target.value)}
          required
        />
      </label>

      {result && !result.verified && (
        <p className="claim-form-error">{result.message}</p>
      )}
      {error && <p className="claim-form-error">{error}</p>}

      <div className="claim-form-actions">
        <button type="submit" disabled={submitting}>
          {submitting ? 'Checking…' : 'Submit answer'}
        </button>
        <button type="button" className="claim-form-cancel" onClick={() => setOpen(false)} disabled={submitting}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function ThreadRow({ match, sourceId, index, onClaimed }) {
  const [counterpart, setCounterpart] = useState(null);
  const [loading, setLoading] = useState(true);

  const counterpartId = match.lost_report_id === sourceId ? match.found_report_id : match.lost_report_id;
  const needsReview = match.status === 'NEEDS_DISAMBIGUATION' || match.status === 'needs_disambiguation';
  const isConfirmed = match.status === 'CONFIRMED' || match.status === 'confirmed';
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

  // Claiming only makes sense against a FOUND report that's still open --
  // that's the side holding the hidden_question a claimant must answer.
  const claimable = counterpart?.report_type === 'found' && counterpart?.status === 'open' && !isConfirmed;

  return (
    <div
      className={`thread-row ${needsReview ? 'thread-row--review' : ''}`}
      style={{ '--card-index': index }}
    >
      {loading ? (
        <div className="thread-loading status-pulse">Loading counterpart report…</div>
      ) : counterpart ? (
        <>
          <NoticeCard report={counterpart} compact />
          {claimable && <ClaimForm match={match} foundReport={counterpart} onClaimed={onClaimed} />}
          {isConfirmed && <p className="claim-form-success-note">✅ Already claimed and confirmed.</p>}
        </>
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

  // Deliberately only re-fetches sourceReport, NOT findMatches again --
  // findMatches() re-runs the whole matching pipeline and writes fresh
  // Match rows, which would spam duplicate matches every time someone
  // claims an item. The claim form already shows its own inline success
  // state, so this just keeps the source report's status badge current.
  function refreshSourceReport() {
    getReport(reportId)
      .then((r) => setSourceReport(r))
      .catch(() => {});
  }

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
            <ThreadRow key={m.id} match={m} sourceId={reportId} index={i} onClaimed={refreshSourceReport} />
          ))}
        </div>
      )}
    </div>
  );
}