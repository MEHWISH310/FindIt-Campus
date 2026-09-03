import { useCallback, useEffect, useState } from 'react';
import { listPendingPickups, confirmHandover, ApiError } from '../api/client';

function formatDate(dateString) {
  if (!dateString) return '—';
  return new Date(dateString).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

/**
 * Admin-only dashboard: the queue of matches where the claimant already
 * answered the verification question correctly (status VERIFIED), but the
 * item is still sitting with admin -- nobody's clicked "handed over" yet.
 *
 * Each row shows the report's unique id (match_id) plus who found it and
 * who's coming to collect it, so admin can look the person up by id when
 * they show up at the collection point, confirm it's really them, and
 * click the button below -- that's the one action that actually resolves
 * the reports, writes the custody record, and emails the finder.
 */
export default function Admin() {
  const [pickups, setPickups] = useState(null);
  const [error, setError] = useState(null);
  const [confirmingId, setConfirmingId] = useState(null);
  const [justConfirmed, setJustConfirmed] = useState(null);

  const reload = useCallback(() => {
    listPendingPickups()
      .then((data) => setPickups(data ?? []))
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load pending pickups.'));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function handleConfirm(matchId) {
    setConfirmingId(matchId);
    setError(null);
    try {
      await confirmHandover(matchId);
      setJustConfirmed(matchId);
      setPickups((current) => current.filter((p) => p.match_id !== matchId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not confirm handover.');
    } finally {
      setConfirmingId(null);
    }
  }

  return (
    <div className="page-shell dashboard">
      <div className="dashboard-head">
        <h1 className="dashboard-title">
          Ready for pickup
          {pickups && <span className="dashboard-count">{pickups.length}</span>}
        </h1>
      </div>

      <p className="dashboard-status" style={{ marginTop: 0 }}>
        Everyone below has already answered their verification question correctly online.
        Check their name against the report's unique id when they arrive, hand over the
        item, then click "Mark handed over" -- that's what actually resolves the reports
        and emails the finder.
      </p>

      {error && <p className="dashboard-status dashboard-status--error">{error}</p>}
      {!pickups && !error && <p className="dashboard-status status-pulse">Loading…</p>}
      {pickups && pickups.length === 0 && (
        <p className="dashboard-status">Nobody's waiting on a pickup right now.</p>
      )}

      {pickups && pickups.length > 0 && (
        <div className="custody-table-wrap">
          <table className="custody-table">
            <thead>
              <tr>
                <th>Report ID</th>
                <th>Item</th>
                <th>Collection point</th>
                <th>Found by</th>
                <th>Collecting owner</th>
                <th>Verified</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {pickups.map((p) => (
                <tr key={p.match_id}>
                  <td className="mono" title={p.match_id}>{p.match_id.slice(0, 8)}</td>
                  <td>
                    {p.item_title}
                    {p.category ? ` (${p.category})` : ''}
                  </td>
                  <td>{p.collection_point || '—'}</td>
                  <td>
                    {p.finder ? (
                      <>
                        {p.finder.name || p.finder.email}
                        <br />
                        <span className="mono">{p.finder.email}</span>
                        {p.finder.phone ? <><br />{p.finder.phone}</> : null}
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    {p.owner ? (
                      <>
                        {p.owner.name || p.owner.email}
                        <br />
                        <span className="mono">{p.owner.email}</span>
                        {p.owner.phone ? <><br />{p.owner.phone}</> : null}
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="mono">{formatDate(p.verified_at)}</td>
                  <td>
                    <button
                      type="button"
                      className="submit-btn"
                      disabled={confirmingId === p.match_id}
                      onClick={() => handleConfirm(p.match_id)}
                    >
                      {confirmingId === p.match_id ? 'Confirming…' : 'Mark handed over'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {justConfirmed && (
        <p className="dashboard-status" style={{ marginTop: 16 }}>
          Handover confirmed — the finder has been emailed.
        </p>
      )}
    </div>
  );
}