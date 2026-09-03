import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  listReports,
  listMyCustodyRecords,
  getStoredToken,
  updateMe,
  ApiError,
} from '../api/client';
import { useAuth } from '../context/AuthContext';
import NoticeCard from '../components/NoticeCard';
import ChangePasswordForm from '../components/ChangePasswordForm';
import Modal from '../components/Modal';

function formatDateTime(value) {
  if (!value) return '-';
  return new Date(value).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function PencilIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
      <path
        d="M4 20h4L18.5 9.5a2.12 2.12 0 0 0-3-3L5 17v3Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="M13.5 7.5l3 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export default function Profile() {
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();

  const [reports, setReports] = useState([]);
  const [claimed, setClaimed] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [nameOpen, setNameOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);

  const [name, setName] = useState(user?.name || '');
  const [savingName, setSavingName] = useState(false);
  const [nameError, setNameError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([listReports(), listMyCustodyRecords()])
      .then(([reportData, claimedData]) => {
        setReports(reportData ?? []);
        setClaimed(claimedData ?? []);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function openNameModal() {
    setName(user?.name || '');
    setNameError(null);
    setNameOpen(true);
  }

  async function handleSaveName(e) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || trimmed === (user?.name || '')) return;
    setSavingName(true);
    setNameError(null);
    try {
      await updateMe({ name: trimmed });
      await refreshUser();
      setNameOpen(false);
    } catch (err) {
      setNameError(err instanceof ApiError ? err.message : 'Could not save your name.');
    } finally {
      setSavingName(false);
    }
  }

  // Only the reports this user filed. reporter_id is exposed on ReportOut
  // (see backend/app/routers/schemas.py).
  const mine = reports.filter((r) => user && r.reporter_id === user.id);
  const myLost = mine.filter((r) => r.report_type === 'lost');
  const myFound = mine.filter((r) => r.report_type === 'found');

  // When neither list has more than one card there's a lot of empty space
  // to the right of a single card, so sit the two sections side by side.
  // As soon as either list holds 2+ cards they go back to stacked full-width.
  const compactReports = myLost.length <= 1 && myFound.length <= 1;

  function handleDeleted(id) {
    setReports((prev) => prev.filter((r) => r.id !== id));
  }

  function renderGrid(list, emptyText) {
    if (list.length === 0) {
      return <p className="profile-empty">{emptyText}</p>;
    }
    return (
      <div className="dashboard-grid">
        {list.map((report, i) => (
          <div key={report.id} style={{ '--card-index': i }}>
            <NoticeCard
              report={report}
              currentUserId={user?.id}
              token={getStoredToken()}
              onDeleted={handleDeleted}
              onFindMatches={() => navigate(`/matches/${report.id}`)}
            />
          </div>
        ))}
      </div>
    );
  }

  const displayName = user?.name || user?.email?.split('@')[0] || 'My account';
  const nameUnchanged = name.trim() === (user?.name || '') || !name.trim();

  return (
    <div className="page-shell profile">
      <div className="dashboard-head">
        <div className="profile-identity">
          <div className="profile-name-row">
            <h1 className="profile-name">{displayName}</h1>
            <button
              type="button"
              className="profile-edit-btn"
              onClick={openNameModal}
              aria-label="Edit name"
              title="Edit name"
            >
              <PencilIcon />
            </button>
          </div>
          {user?.email && <p className="profile-email">{user.email}</p>}
        </div>

        <button type="button" className="header-btn" onClick={() => setPwOpen(true)}>
          Reset password
        </button>
      </div>

      {loading && <p className="profile-empty">Loading your activity…</p>}
      {error && (
        <p className="profile-empty profile-empty--error">Couldn't load your activity: {error}</p>
      )}

      {!loading && !error && (
        <>
          <div className={`profile-reports${compactReports ? ' profile-reports--split' : ''}`}>
            <section className="profile-section">
              <h2 className="profile-section-title profile-section-title--lost">
                Things I reported as lost
                <span className="dashboard-count">{myLost.length}</span>
              </h2>
              {renderGrid(myLost, "You haven't reported anything lost yet.")}
            </section>

            <section className="profile-section">
              <h2 className="profile-section-title profile-section-title--found">
                Things I found
                <span className="dashboard-count">{myFound.length}</span>
              </h2>
              {renderGrid(myFound, "You haven't reported anything found yet.")}
            </section>
          </div>

          <section className="profile-section">
            <h2 className="profile-section-title">
              Things I claimed
              <span className="dashboard-count">{claimed.length}</span>
            </h2>
            {claimed.length === 0 ? (
              <p className="profile-empty">You haven't claimed anything yet.</p>
            ) : (
              <div className="custody-table-wrap">
                <table className="custody-table">
                  <thead>
                    <tr>
                      <th>Item</th>
                      <th>Handed over</th>
                      <th>Contact given</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {claimed.map((r) => (
                      <tr key={r.id}>
                        <td>{r.item_name}</td>
                        <td className="mono">{formatDateTime(r.handover_datetime)}</td>
                        <td>{r.claimant_contact || '-'}</td>
                        <td>{r.notes || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {nameOpen && (
        <Modal onClose={() => setNameOpen(false)} labelledBy="name-modal-heading">
          <h2 id="name-modal-heading" className="modal-heading">
            Edit name
          </h2>
          <form className="stacked-form" onSubmit={handleSaveName}>
            <label className="field">
              <span>Display name</span>
              <input
                type="text"
                value={name}
                placeholder="Add your name"
                autoFocus
                required
                maxLength={100}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            {!name.trim() && <p className="field-note">Name can't be empty.</p>}
            {nameError && <p className="form-error">{nameError}</p>}
            <div className="modal-actions">
              <button
                type="button"
                className="claim-form-cancel"
                onClick={() => setNameOpen(false)}
              >
                Cancel
              </button>
              <button type="submit" className="submit-btn" disabled={savingName || nameUnchanged}>
                {savingName ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {pwOpen && (
        <Modal onClose={() => setPwOpen(false)} labelledBy="pw-modal-heading">
          <h2 id="pw-modal-heading" className="modal-heading">
            Reset password
          </h2>
          <ChangePasswordForm
            bare
            onCancel={() => setPwOpen(false)}
            onSuccess={() => setTimeout(() => setPwOpen(false), 900)}
          />
        </Modal>
      )}
    </div>
  );
}
