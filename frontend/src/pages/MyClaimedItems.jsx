import { useEffect, useState } from 'react';
import { listCustodyRecords } from '../api/client';

function formatDate(dateString) {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

// Non-admin "Claimed items" view. Shows every handover (same source as the
// admin page), just with the identity columns (claimant name/contact/
// notes) dropped -- regular users don't need to see who claimed what,
// only what's been claimed, who verified it, and where to collect it.
export default function MyClaimedItems() {
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
                <th>Match ID</th>
                <th>Item</th>
                <th>Verified by</th>
                <th>Handed over</th>
                <th>Collection point</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id}>
                  <td className="mono" title={r.match_id}>{r.match_id.slice(0, 8)}</td>
                  <td>{r.item_name}</td>
                  <td>{r.verifier_name}</td>
                  <td className="mono">{formatDate(r.handover_datetime)}</td>
                  <td>{r.collection_point || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}