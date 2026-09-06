import { useEffect, useState } from 'react';
import { listCustodyRecords, listMyClaims } from '../api/client';

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

function formatDate(dateString) {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function isWithinLast7Days(dateString) {
  if (!dateString) return false;
  const then = new Date(dateString).getTime();
  return Date.now() - then <= SEVEN_DAYS_MS;
}

// Non-admin "Claimed items" view, split into two sections:
//
//   1. Things I claimed  -- every claim the logged-in user has made, at
//      any stage (pickup pending or already handed over). Comes from
//      /custody/mine/claims.
//   2. Claimed by others  -- every other handover across campus in the
//      last 7 days, with the identity columns (claimant name/contact)
//      dropped since regular users don't need to see who claimed what.
//      Older handovers are hidden here entirely, keeping this feed on
//      recent activity rather than the full log the admin page covers.
export default function MyClaimedItems() {
  const [myClaims, setMyClaims] = useState(null);
  const [allRecords, setAllRecords] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listMyClaims(), listCustodyRecords()])
      .then(([mine, all]) => {
        if (cancelled) return;
        setMyClaims(mine ?? []);
        setAllRecords(all ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loading = !error && (myClaims === null || allRecords === null);

  // Match ids that are the current user's own claims -- used to keep those
  // rows out of the "claimed by others" section so nothing shows twice.
  const myMatchIds = new Set((myClaims ?? []).map((c) => c.match_id));

  const othersRecent = (allRecords ?? []).filter(
    (r) => isWithinLast7Days(r.handover_datetime) && !myMatchIds.has(r.match_id)
  );

  return (
    <div className="page-shell dashboard claimed-items claimed-items--mine">
      <div className="dashboard-head">
        <h1 className="dashboard-title">Claimed items</h1>
      </div>

      <p className="claimed-items-intro">
        Your own claims, plus everything else handed over across campus in the last 7 days. Other people's names and contact details stay hidden.
      </p>

      {error && (
        <p className="dashboard-status dashboard-status--error">Couldn't reach the backend: {error}</p>
      )}
      {loading && <p className="dashboard-status status-pulse">Loading claimed items…</p>}

      {!loading && !error && (
        <>
          <section className="claimed-section">
            <h2 className="claimed-section-title">
              Things I claimed
              <span className="dashboard-count">{myClaims.length}</span>
            </h2>

            {myClaims.length === 0 ? (
              <p className="dashboard-status">You haven't claimed anything yet.</p>
            ) : (
              <div className="custody-table-wrap">
                <table className="custody-table">
                  <thead>
                    <tr>
                      <th>Ref</th>
                      <th>Item</th>
                      <th>Status</th>
                      <th>Handed over</th>
                      <th>Collection point</th>
                    </tr>
                  </thead>
                  <tbody>
                    {myClaims.map((r) => (
                      <tr key={r.id}>
                        <td className="mono" title={r.match_id}>
                          {r.match_id ? r.match_id.slice(0, 8) : '-'}
                        </td>
                        <td>{r.item_name}</td>
                        <td>
                          <span className={`claim-status claim-status--${r.status}`}>
                            {r.status === 'pending' ? 'Pickup pending' : 'Collected'}
                          </span>
                        </td>
                        <td className="mono">
                          {r.status === 'pending' ? '-' : formatDate(r.handover_datetime)}
                        </td>
                        <td>{r.collection_point || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="claimed-section">
            <h2 className="claimed-section-title">
              Things claimed by others in the last 7 days
              <span className="dashboard-count">{othersRecent.length}</span>
            </h2>

            {othersRecent.length === 0 ? (
              <p className="dashboard-status">Nobody else has claimed anything in the last 7 days.</p>
            ) : (
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
                    {othersRecent.map((r) => (
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
          </section>
        </>
      )}
    </div>
  );
}
