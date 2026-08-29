import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listReports, escalateStale } from '../api/client';
import NoticeCard from '../components/NoticeCard';

export default function Dashboard({ reportType }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [escalating, setEscalating] = useState(false);
  const [escalationResult, setEscalationResult] = useState(null);
  const navigate = useNavigate();

  function reload() {
    setLoading(true);
    setError(null);
    listReports(reportType)
      .then((data) => setReports(data ?? []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    let cancelled = false;
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
    setEscalating(true);
    setEscalationResult(null);
    try {
      const escalated = await escalateStale();
      setEscalationResult(
        escalated.length === 0
          ? 'No unclaimed high-risk items past the threshold right now.'
          : `Escalated ${escalated.length} unclaimed high-risk item(s).`
      );
      reload(); // so any newly-escalated cards refresh their badge immediately
    } catch (err) {
      setEscalationResult(`Couldn't run the check: ${err.message}`);
    } finally {
      setEscalating(false);
    }
  }

  const label = reportType === 'lost' ? 'Lost' : 'Found';

  return (
    <div className="page-shell dashboard">
      <div className="dashboard-head">
        <h1 className={`dashboard-title dashboard-title--${reportType}`}>
          {label}
          {!loading && !error && <span className="dashboard-count">{reports.length}</span>}
        </h1>
        {reportType === 'found' && (
          <button
            type="button"
            className="escalation-check-btn"
            onClick={handleEscalationCheck}
            disabled={escalating}
            title="Marks unclaimed ID/phone/document reports older than 7 days as escalated"
          >
            {escalating ? 'Checking…' : 'Run escalation check'}
          </button>
        )}
      </div>

      {escalationResult && <p className="dashboard-status">{escalationResult}</p>}

      {loading && <p className="dashboard-status status-pulse">Loading reports…</p>}
      {error && <p className="dashboard-status dashboard-status--error">Couldn't reach the backend: {error}</p>}
      {!loading && !error && reports.length === 0 && (
        <p className="dashboard-status">
          Nothing reported {reportType} yet. {reportType === 'lost' ? 'Report something lost' : 'Report something found'} to get started.
        </p>
      )}

      <div className="dashboard-grid">
        {reports.map((report, i) => (
          <div key={report.id} style={{ '--card-index': i }}>
            <NoticeCard report={report} onFindMatches={() => navigate(`/matches/${report.id}`)} />
          </div>
        ))}
      </div>
    </div>
  );
}