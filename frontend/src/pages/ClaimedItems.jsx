import { useEffect, useState } from 'react';
import { listCustodyRecords } from '../api/client';

function formatDate(dateString) {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export default function ClaimedItems() {
  const [records, setRecords] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    listCustodyRecords()
      .then((data) => {
        if (!cancelled) setRecords(data ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="page-shell dashboard claimed-items">
      <div className="dashboard-head">
        <h1 className="dashboard-title">
          Claimed items
          {records && <span className="dashboard-count">{records.length}</span>}
        </h1>
      </div>

      <p className="dashboard-status" style={{ marginTop: 0 }}>
        Every confirmed handover, most recent first. This is the audit trail written
        when a claimant answers a found report's verification question correctly.
      </p>

      {error && <p className="dashboard-status dashboard-status--error">Couldn't reach the backend: {error}</p>}
      {!records && !error && <p className="dashboard-status status-pulse">Loading claimed items…</p>}
      {records && records.length === 0 && (
        <p className="dashboard-status">Nothing has been claimed yet.</p>
      )}

      {records && records.length > 0 && (
        <div className="custody-table-wrap">
          <table className="custody-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Claimant</th>
                <th>Contact</th>
                <th>Verified by</th>
                <th>Handed over</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id}>
                  <td>{r.item_name}</td>
                  <td>{r.claimant_name}</td>
                  <td>{r.claimant_contact || '-'}</td>
                  <td>{r.verifier_name}</td>
                  <td className="mono">{formatDate(r.handover_datetime)}</td>
                  <td>{r.notes || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}