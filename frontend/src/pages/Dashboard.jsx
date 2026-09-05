import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { listReports, escalateStale, showToast } from '../api/client';
import { useAuth } from '../context/AuthContext';
import NoticeCard from '../components/NoticeCard';

// A report counts as "past the threshold" once it's high-risk, still
// unclaimed (not resolved), and the item itself has been missing for more
// than 7 days. That age is measured from `item_datetime` (when it was
// found/lost), NOT `created_at` (when the report was filed) -- someone can
// report today an ID card they found two weeks ago, and the backend's
// escalate-stale sweep keys off item_datetime for exactly this reason.
const STALE_THRESHOLD_MS = 7 * 24 * 60 * 60 * 1000;

function selectStaleHighRisk(list) {
  const cutoff = Date.now() - STALE_THRESHOLD_MS;
  return list.filter(
    (r) =>
      r.is_high_risk &&
      r.status !== 'resolved' &&
      r.item_datetime &&
      new Date(r.item_datetime).getTime() < cutoff
  );
}

export default function Dashboard({ reportType }) {
  const { user } = useAuth();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [escalating, setEscalating] = useState(false);
  // The escalation check is a toggle:
  //   off (default) -> the grid shows every report, as normal
  //   on            -> the grid shows ONLY high-risk found items unclaimed
  //                    for over 7 days. Turning it on with nothing past the
  //                    threshold just fires a toast and stays off.
  const [escalationOn, setEscalationOn] = useState(false);
  const navigate = useNavigate();

  function reload() {
    setLoading(true);
    setError(null);
    return listReports(reportType)
      .then((data) => {
        const list = data ?? [];
        setReports(list);
        return list;
      })
      .catch((err) => {
        setError(err.message);
        return [];
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    let cancelled = false;
    setEscalationOn(false); // don't carry the filter across a Lost/Found switch
    setLoading(true);
    setError(null);
    listReports(reportType)
      .then((data) => {
        if (!cancelled) setReports(data ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reportType]);

  async function handleEscalationCheck() {
    // Already filtered -> this press just turns the filter back off.
    if (escalationOn) {
      setEscalationOn(false);
      return;
    }
    setEscalating(true);
    try {
      await escalateStale();
      // reload so any newly-escalated cards refresh their badge immediately,
      // then work from the fresh list rather than the stale `reports` state.
      const fresh = await reload();
      const stale = selectStaleHighRisk(fresh);
      if (stale.length === 0) {
        showToast('No unclaimed high-risk items past the threshold right now.');
        setEscalationOn(false);
      } else {
        setEscalationOn(true);
      }
    } catch (err) {
      setEscalationOn(false);
      showToast(`Couldn't run the escalation check: ${err.message}`);
    } finally {
      setEscalating(false);
    }
  }

  const label = reportType === 'lost' ? 'Lost' : 'Found';
  const visibleReports = escalationOn ? selectStaleHighRisk(reports) : reports;

  return (
    <div className="page-shell dashboard">
      <div className="dashboard-head">
        <h1 className={`dashboard-title dashboard-title--${reportType}`}>
          {label}
          {!loading && !error && <span className="dashboard-count">{visibleReports.length}</span>}
        </h1>
        <div className="dashboard-head-actions">
          {reportType === 'found' && (
            <button
              type="button"
              className={`escalation-check-btn${escalationOn ? ' escalation-check-btn--on' : ''}`}
              onClick={handleEscalationCheck}
              disabled={escalating}
              aria-pressed={escalationOn}
              title="Shows only unclaimed high-risk items older than 7 days; press again to show everything"
            >
              {escalating ? 'Checking…' : escalationOn ? 'Show all found' : 'Run escalation check'}
            </button>
          )}
          <Link to={`/report/${reportType}`} className={`header-btn header-btn--${reportType}`}>
            Report {reportType}
          </Link>
        </div>
      </div>

      {escalationOn && (
        <p className="dashboard-status dashboard-status--filter">
          Showing only high-risk found items unclaimed for over 7 days.
        </p>
      )}

      {loading && <p className="dashboard-status status-pulse">Loading reports…</p>}
      {error && <p className="dashboard-status dashboard-status--error">Couldn't reach the backend: {error}</p>}
      {!loading && !error && reports.length === 0 && (
        <p className="dashboard-status">
          Nothing reported {reportType} yet. {reportType === 'lost' ? 'Report something lost' : 'Report something found'} to get started.
        </p>
      )}

      <div className="dashboard-grid">
        {visibleReports.map((report, i) => (
          <div key={report.id} style={{ '--card-index': i }}>
            {/*
              Deliberately NOT passing currentUserId/token here: on the
              shared Lost/Found tabs, nobody should see a report's id just
              because they filed it -- that's reserved for their own
              Profile page. Only isAdmin is passed, so NoticeCard's
              canSeeReportId (isAdmin || isOwner) only ever resolves true
              here for an admin, regardless of who reported it.
            */}
            <NoticeCard
              report={report}
              onFindMatches={() => navigate(`/matches/${report.id}`)}
              isAdmin={user?.is_admin}
            />
          </div>
        ))}
      </div>
    </div>
  );
}