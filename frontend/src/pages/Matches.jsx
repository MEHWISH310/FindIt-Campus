import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getReport, getMatch, findMatches, claimMatch, checkClaimAnswer, disambiguateMatch, ApiError } from '../api/client';
import NoticeCard from '../components/NoticeCard';
import Modal from '../components/Modal';
import { useAuth } from '../context/AuthContext';

function isNeedsReview(match) {
  return match.status === 'NEEDS_DISAMBIGUATION' || match.status === 'needs_disambiguation';
}

function isRejected(match) {
  return match.status === 'REJECTED' || match.status === 'rejected';
}

function isVerified(match) {
  return match.status === 'VERIFIED' || match.status === 'verified';
}

// Small red-asterisk marker for required-field labels.
function Required() {
  return <span style={{ color: '#ef4444' }}> *</span>;
}

/**
 * Claim/verification popup. Only ever shown for a FOUND counterpart report
 * -- the claimant is proving the item is theirs by answering the finder's
 * hidden_question (asymmetric verification, per the abstract). Opened via
 * NoticeCard's primaryAction button rather than expanding inline, so it
 * doesn't get squeezed into thread-row's flex layout as its own column.
 *
 * Two steps:
 *   1. "answer" -- just the verification question. Checked via
 *      POST /matches/{id}/check-answer (no state change either way), so a
 *      wrong guess doesn't cost them filling in their name/reg number/etc
 *      first for nothing.
 *   2. "details" -- shown only once step 1 comes back correct. Collects
 *      name/registration number/phone and submits everything (answer
 *      included) to POST /matches/{id}/verify, which is what actually
 *      records the claim -- it re-checks the answer itself too, so step 1
 *      is a UX nicety, not the real security boundary.
 */
function ClaimModal({ match, foundReport, onClaimed, onClose }) {
  const { user } = useAuth();
  const [step, setStep] = useState('answer'); // 'answer' | 'details'
  const [claimantName, setClaimantName] = useState('');
  const [registrationNumber, setRegistrationNumber] = useState('');
  const [claimantContact, setClaimantContact] = useState('');
  const [hiddenAnswer, setHiddenAnswer] = useState('');
  const [checking, setChecking] = useState(false);
  const [answerError, setAnswerError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // { verified, message } | null
  const [error, setError] = useState(null);

  async function handleCheckAnswer(e) {
    e.preventDefault();
    setChecking(true);
    setAnswerError(null);
    try {
      const res = await checkClaimAnswer(match.id, hiddenAnswer);
      if (res.correct) {
        setStep('details');
      } else {
        setAnswerError('Wrong answer. You can try again.');
      }
    } catch (err) {
      setAnswerError(err instanceof ApiError ? err.message : 'Could not check the answer.');
    } finally {
      setChecking(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res = await claimMatch(match.id, {
        claimant_name: claimantName.trim(),
        claimant_registration_number: registrationNumber.trim().toUpperCase(),
        claimant_email: user?.email ?? '',
        claimant_contact: claimantContact.trim() || null,
        hidden_answer: hiddenAnswer,
      });
      setResult(res);
      if (res.verified) {
        onClaimed?.();
      } else {
        // The answer was re-checked server-side and somehow came back
        // wrong this time (e.g. the question changed underneath them) --
        // send them back to step 1 rather than stranding them on a details
        // form for an answer that no longer works.
        setStep('answer');
        setAnswerError(res.message || 'That answer no longer matches. Please try again.');
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not submit the claim.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal onClose={onClose} labelledBy="claim-modal-heading">
      <h2 id="claim-modal-heading" className="modal-heading">
        Claim this item
      </h2>

      {result?.verified ? (
        <div className="claim-form claim-form--success">
          <p>{result.message}</p>
          <button type="button" className="claim-form-cancel" onClick={onClose}>
            Close
          </button>
        </div>
      ) : step === 'answer' ? (
        <form className="claim-form" onSubmit={handleCheckAnswer}>
          <p className="claim-form-question">
            <strong>Verification question:</strong> {foundReport.hidden_question || 'No question set for this report.'}
          </p>

          <label>
            <span>Your answer<Required /></span>
            <input
              type="text"
              value={hiddenAnswer}
              onChange={(e) => setHiddenAnswer(e.target.value)}
              required
              autoFocus
            />
          </label>

          {answerError && <p className="claim-form-error">{answerError}</p>}

          <div className="claim-form-actions">
            <button type="submit" disabled={checking}>
              {checking ? 'Checking…' : 'Check answer'}
            </button>
            <button type="button" className="claim-form-cancel" onClick={onClose} disabled={checking}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <form className="claim-form" onSubmit={handleSubmit}>
          <p className="claim-form-question">Answer verified -- now fill in your details to complete the claim.</p>

          <label>
            <span>Your name<Required /></span>
            <input
              type="text"
              value={claimantName}
              onChange={(e) => setClaimantName(e.target.value)}
              required
              autoFocus
            />
          </label>

          <label>
            <span>Registration number<Required /></span>
            <input
              type="text"
              value={registrationNumber}
              onChange={(e) => setRegistrationNumber(e.target.value)}
              placeholder="23BCE0000"
              required
            />
          </label>

          <label>
            <span>Email<Required /></span>
            <input type="email" value={user?.email ?? ''} readOnly disabled />
          </label>

          <label>
            Phone number (optional)
            <input
              type="text"
              value={claimantContact}
              onChange={(e) => setClaimantContact(e.target.value)}
            />
          </label>

          {result && !result.verified && (
            <p className="claim-form-error">{result.message}</p>
          )}
          {error && <p className="claim-form-error">{error}</p>}

          <div className="claim-form-actions">
            <button type="submit" disabled={submitting}>
              {submitting ? 'Submitting…' : 'Submit claim'}
            </button>
            <button
              type="button"
              className="claim-form-cancel"
              onClick={() => setStep('answer')}
              disabled={submitting}
            >
              Back
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

/**
 * One candidate inside a disambiguation cluster (2+ matches that scored
 * too close to auto-rank -- see DISAMBIGUATION_MARGIN in matches.py).
 * Shows the counterpart report plus the backend's generated question, and
 * lets the user forced-choice pick it as theirs -- no freeform answer to
 * interpret, just POST /matches/{id}/disambiguate.
 */
function DisambiguationCandidate({ match, sourceId, onChosen }) {
  const [counterpart, setCounterpart] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const counterpartId = match.lost_report_id === sourceId ? match.found_report_id : match.lost_report_id;

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

  async function handleChoose() {
    setSubmitting(true);
    setError(null);
    try {
      const updatedCluster = await disambiguateMatch(match.id);
      onChosen(updatedCluster);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't record your choice.");
      setSubmitting(false);
    }
  }

  return (
    <div className="disambig-candidate">
      {loading ? (
        <div className="thread-loading status-pulse">Loading…</div>
      ) : counterpart ? (
        <NoticeCard report={counterpart} compact />
      ) : (
        <div className="thread-loading">Couldn't load that report.</div>
      )}
      {match.disambiguation_question && <p className="disambig-question">{match.disambiguation_question}</p>}
      {error && <p className="claim-form-error">{error}</p>}
      <button type="button" className="disambig-choose" onClick={handleChoose} disabled={submitting}>
        {submitting ? 'Confirming…' : 'This one →'}
      </button>
    </div>
  );
}

/** Groups every NEEDS_DISAMBIGUATION match for this source report into one
 * forced-choice prompt, shown above the regular ranked thread-list. */
function DisambiguationPrompt({ matches, sourceId, onResolved }) {
  return (
    <div className="disambig-prompt">
      <p className="disambig-heading">
        A few candidates scored too close to auto-rank. Which one is actually yours?
      </p>
      <div className="disambig-grid">
        {matches.map((m) => (
          <DisambiguationCandidate key={m.id} match={m} sourceId={sourceId} onChosen={onResolved} />
        ))}
      </div>
    </div>
  );
}

function ThreadRow({ match, sourceId, index, onClaimed, isSourceOwner }) {
  const [counterpart, setCounterpart] = useState(null);
  const [loading, setLoading] = useState(true);
  const [claimOpen, setClaimOpen] = useState(false);
  const [gatedInfo, setGatedInfo] = useState(null); // { found_contact, claimant_info } | null

  const counterpartId = match.lost_report_id === sourceId ? match.found_report_id : match.lost_report_id;
  const needsReview = isNeedsReview(match);
  const isConfirmed = match.status === 'CONFIRMED' || match.status === 'confirmed';
  const verifiedPendingPickup = isVerified(match);
  const hasProbability = match.match_probability != null;
  const pct = hasProbability
    ? Math.round(match.match_probability * 100)
    : match.raw_score != null
      ? Math.round(match.raw_score * 100)
      : null;

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

  // Once a match is CONFIRMED, re-fetch it with auth attached -- the
  // backend fills in found_contact (for the lost reporter) or
  // claimant_info (for the found reporter) only for whichever side the
  // logged-in user actually is; everyone else gets both as null, so this
  // is safe to call regardless of who's viewing.
  useEffect(() => {
    if (!isConfirmed) return;
    let cancelled = false;
    getMatch(match.id)
      .then((m) => {
        if (!cancelled) setGatedInfo({ found_contact: m.found_contact, claimant_info: m.claimant_info });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isConfirmed, match.id]);

  // Claiming only makes sense against a FOUND report that's still open --
  // that's the side holding the hidden_question a claimant must answer --
  // AND only for the person who actually filed the LOST report this
  // matches page is for. The backend enforces this too (verify_claim
  // 403s anyone else), but there's no reason to dangle a "Claim this
  // item" button in front of someone who's just browsing another
  // student's matches and let them hit that error.
  const claimable =
    counterpart?.report_type === 'found' &&
    counterpart?.status === 'open' &&
    !isConfirmed &&
    !verifiedPendingPickup &&
    isSourceOwner;

  return (
    <div
      className={`thread-row ${needsReview ? 'thread-row--review' : ''}`}
      style={{ '--card-index': index }}
    >
      <div className="thread-row-content">
        {loading ? (
          <div className="thread-loading status-pulse">Loading counterpart report…</div>
        ) : counterpart ? (
          <>
            <NoticeCard
              report={counterpart}
              compact
              primaryAction={claimable ? { label: 'Claim this item', onClick: () => setClaimOpen(true) } : null}
            />
            {isConfirmed && <p className="claim-form-success-note">Already claimed and confirmed.</p>}
            {verifiedPendingPickup && (
              <p className="claim-form-success-note">
                Verified! Go collect this item from admin
                {counterpart?.collection_point ? ` at ${counterpart.collection_point}` : ''}.
              </p>
            )}
            {isConfirmed && gatedInfo?.found_contact && (
              <div className="claim-form-success-note">
                <strong>Finder's contact:</strong> {gatedInfo.found_contact.name || 'N/A'} ·{' '}
                {gatedInfo.found_contact.email}
                {gatedInfo.found_contact.phone ? ` · ${gatedInfo.found_contact.phone}` : ''}
              </div>
            )}
            {isConfirmed && gatedInfo?.claimant_info && (
              <div className="claim-form-success-note">
                <strong>Claimed by:</strong> {gatedInfo.claimant_info.claimant_name}
                {gatedInfo.claimant_info.claimant_contact ? ` · ${gatedInfo.claimant_info.claimant_contact}` : ''}
              </div>
            )}
          </>
        ) : (
          <div className="thread-loading">Couldn't load that report.</div>
        )}
      </div>

      {claimOpen && (
        // onClaimed only refreshes the source report's status badge -- the
        // modal stays open so the user sees the "Verified!" message and
        // closes it themselves (via the Close button, Escape, or backdrop).
        <ClaimModal match={match} foundReport={counterpart} onClaimed={onClaimed} onClose={() => setClaimOpen(false)} />
      )}

      <div className="thread-connector">
        <span
          className={`score-pill ${needsReview ? 'score-pill--warn' : ''} ${!hasProbability && pct != null ? 'score-pill--estimated' : ''} mono`}
          title={!hasProbability && pct != null ? 'Estimated from raw score, not yet calibrated against confirmed matches' : undefined}
        >
          {needsReview ? 'Needs review' : pct != null ? `${pct}%` : '-'}
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
  const { user } = useAuth();
  const [sourceReport, setSourceReport] = useState(null);
  const [matches, setMatches] = useState(null);
  const [error, setError] = useState(null);

  // Only the person who filed this lost report should see a "Claim this
  // item" button on its matches page -- everyone else is just browsing.
  const isSourceOwner = !!(user && sourceReport && sourceReport.reporter_id === user.id);

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

  // The disambiguate endpoint returns the resolved cluster (chosen ->
  // CANDIDATE, the rest -> REJECTED) -- merge it into local state instead
  // of re-running findMatches, for the same reason refreshSourceReport
  // avoids it (would spam duplicate Match rows).
  function handleDisambiguationResolved(updatedCluster) {
    setMatches((current) =>
      current.map((m) => updatedCluster.find((u) => u.id === m.id) ?? m)
    );
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
        {sourceReport ? <>Matches for "{sourceReport.title}"</> : 'Finding matches…'}
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
          No candidate matches yet. Check back once more reports come in.
        </p>
      )}

      {matches && matches.length > 0 && (() => {
        const disambiguationCluster = matches.filter(isNeedsReview);
        const normalMatches = matches.filter((m) => !isNeedsReview(m) && !isRejected(m));
        return (
          <>
            {disambiguationCluster.length > 0 && (
              <DisambiguationPrompt
                matches={disambiguationCluster}
                sourceId={reportId}
                onResolved={handleDisambiguationResolved}
              />
            )}
            {normalMatches.length > 0 && (
              <div className="thread-list">
                {normalMatches.map((m, i) => (
                  <ThreadRow
                    key={m.id}
                    match={m}
                    sourceId={reportId}
                    index={i}
                    onClaimed={refreshSourceReport}
                    isSourceOwner={isSourceOwner}
                  />
                ))}
              </div>
            )}
          </>
        );
      })()}
    </div>
  );
}