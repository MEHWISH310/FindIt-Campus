import { useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { createReport, uploadPhotos, checkVerificationQuestion, ApiError } from '../api/client';
import { answerLeaks } from '../utils/leakCheck';

const ANSWER_LEAK_MESSAGE =
  'That answer is visible in your description. Pick something only the owner would know.';

const LOST_WINDOW_MS = 14 * 24 * 60 * 60 * 1000;

// datetime-local inputs want a "YYYY-MM-DDTHH:mm" string in *local* time.
function toLocalInput(d) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

const MAX_PHOTOS = 5;
const MAX_FILE_SIZE = 8 * 1024 * 1024; // 8MB, matches backend's MAX_FILE_SIZE_BYTES

const CATEGORIES = [
  'Wallet',
  'Phone',
  'Laptop',
  'ID Card',
  'Keys',
  'Bag',
  'Bottle',
  'Earbuds',
  'Books',
  'Other',
];

const emptyForm = {
  title: '',
  description: '',
  category: '',
  color: '',
  brand: '',
  location_name: '',
  latitude: '',
  longitude: '',
  item_datetime: '',
  hidden_question: '',
  hidden_answer: '',
  collection_point: '',
};

export default function ReportForm() {
  const { type } = useParams(); // 'lost' | 'found'
  const isFound = type === 'found';
  const navigate = useNavigate();

  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [locating, setLocating] = useState(false);

  const [photos, setPhotos] = useState([]); // File[]
  const [previews, setPreviews] = useState([]); // object URLs for the thumbnails
  const [uploadStatus, setUploadStatus] = useState(null); // null | 'uploading' | 'failed'

  // Verification-question leak checks (found reports only):
  //  - localLeak: instant, deterministic -- the answer literally appears in
  //    the public fields. This blocks submission (same rule server-side).
  //  - verifyWarning: the backend's advisory pass (string + LLM). Overridable
  //    -- shown as a soft warning, doesn't block.
  const [verifyWarning, setVerifyWarning] = useState(null); // { reason } | null
  const [showPreview, setShowPreview] = useState(false);

  // "When you lost it" is capped to the last 14 days (and can't be future).
  const nowLocal = toLocalInput(new Date());
  const weekAgoLocal = toLocalInput(new Date(Date.now() - LOST_WINDOW_MS));

  const publicParts = [
    form.title,
    form.description,
    form.color,
    form.brand,
    form.category,
    form.location_name,
  ];
  const localLeak =
    isFound &&
    form.hidden_answer.trim() !== '' &&
    answerLeaks(form.hidden_answer, ...publicParts);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  // Debounced advisory check -- runs once the finder has filled in a
  // description, question and answer. Skipped when localLeak already fired
  // (the inline error covers that case, no need to spend an LLM call).
  useEffect(() => {
    if (!isFound) return undefined;
    const q = form.hidden_question.trim();
    const a = form.hidden_answer.trim();
    const d = form.description.trim();
    if (!q || !a || !d || localLeak) {
      setVerifyWarning(null);
      return undefined;
    }

    let cancelled = false;
    const t = setTimeout(() => {
      checkVerificationQuestion({
        title: form.title,
        description: form.description,
        category: form.category,
        color: form.color,
        brand: form.brand,
        location_name: form.location_name,
        hidden_question: form.hidden_question,
        hidden_answer: form.hidden_answer,
      })
        .then((res) => {
          if (!cancelled) setVerifyWarning(res?.leaked ? { reason: res.reason } : null);
        })
        .catch(() => {
          if (!cancelled) setVerifyWarning(null); // advisory only -- fail open
        });
    }, 700);

    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [
    isFound,
    localLeak,
    form.title,
    form.description,
    form.category,
    form.color,
    form.brand,
    form.location_name,
    form.hidden_question,
    form.hidden_answer,
  ]);

  // Revoke object URLs when they're replaced/unmounted -- otherwise each
  // selected photo leaks memory for the life of the tab.
  useEffect(() => {
    return () => previews.forEach((url) => URL.revokeObjectURL(url));
  }, [previews]);

  function handlePhotoSelect(e) {
    const picked = Array.from(e.target.files || []);
    e.target.value = ''; // allow re-selecting the same file after removing it

    const room = MAX_PHOTOS - photos.length;
    if (room <= 0) {
      setError(`You can attach up to ${MAX_PHOTOS} photos.`);
      return;
    }

    const tooBig = picked.find((f) => f.size > MAX_FILE_SIZE);
    if (tooBig) {
      setError(`${tooBig.name} is over 8MB. Pick a smaller photo.`);
      return;
    }

    const accepted = picked.slice(0, room);
    setPhotos((p) => [...p, ...accepted]);
    setPreviews((p) => [...p, ...accepted.map((f) => URL.createObjectURL(f))]);
    setError(null);
  }

  function removePhoto(index) {
    URL.revokeObjectURL(previews[index]);
    setPhotos((p) => p.filter((_, i) => i !== index));
    setPreviews((p) => p.filter((_, i) => i !== index));
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      setError('Location is not available in this browser.');
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        update('latitude', pos.coords.latitude.toFixed(6));
        update('longitude', pos.coords.longitude.toFixed(6));
        setLocating(false);
      },
      () => {
        setError('Could not read your location. Enter it manually below.');
        setLocating(false);
      }
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (isFound && !form.hidden_question.trim()) {
      setError('A verification question is required for found reports.');
      return;
    }
    if (isFound && !form.hidden_answer.trim()) {
      setError('The expected answer is required too -- without it, nobody could ever pass verification.');
      return;
    }
    if (isFound && !form.collection_point.trim()) {
      setError('Tell us where admin will be holding this item so the owner knows where to collect it.');
      return;
    }
    if (!isFound) {
      if (!form.item_datetime) {
        setError('Tell us roughly when you lost it.');
        return;
      }
      const when = new Date(form.item_datetime).getTime();
      if (when > Date.now()) {
        setError("The date you lost it can't be in the future.");
        return;
      }
      if (when < Date.now() - LOST_WINDOW_MS) {
        setError('Please report items lost within the last two weeks. For an older loss, contact the lost & found desk.');
        return;
      }
    }
    if (localLeak) {
      setError(ANSWER_LEAK_MESSAGE);
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        report_type: type,
        title: form.title,
        description: form.description,
        category: form.category,
        color: form.color,
        brand: form.brand,
        location_name: form.location_name,
        latitude: form.latitude ? parseFloat(form.latitude) : null,
        longitude: form.longitude ? parseFloat(form.longitude) : null,
        // Found reports don't ask -- the backend stamps them with the
        // submission time. Lost reports send the owner's chosen time.
        item_datetime:
          isFound || !form.item_datetime ? null : new Date(form.item_datetime).toISOString(),
        hidden_question: form.hidden_question,
        hidden_answer: form.hidden_answer,
        collection_point: form.collection_point,
      };
      const report = await createReport(payload);

      // Photos are uploaded as a second step, after the report exists --
      // if this fails, the report itself is still saved (text-only match
      // is still useful), so we warn instead of blocking navigation.
      if (photos.length > 0) {
        setUploadStatus('uploading');
        try {
          await uploadPhotos(report.id, photos);
        } catch (uploadErr) {
          setUploadStatus('failed');
          console.error('Photo upload failed:', uploadErr);
        }
      }

      navigate(`/matches/${report.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong submitting the report.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="report-page report-page--wide">
      <Link to="/" className="back-link">
        ← Back
      </Link>

      <form
        className={`report-card ${isFound ? 'report-card--found' : 'report-card--lost'}`}
        onSubmit={handleSubmit}
      >
        <span className={`report-tag ${isFound ? 'report-tag--found' : 'report-tag--lost'}`}>
          {isFound ? 'Found item' : 'Lost item'}
        </span>
        <h1 className="report-heading">
          {isFound ? 'Report what you found' : 'Report what you lost'}
        </h1>

        <label className="field">
          <span>Title *</span>
          <input
            required
            value={form.title}
            onChange={(e) => update('title', e.target.value)}
            placeholder={isFound ? 'e.g. Black wallet' : 'e.g. Black wallet near library'}
          />
        </label>

        <label className="field">
          <span>{isFound ? 'Public description' : 'Description'} *</span>
          <textarea
            required
            rows={3}
            value={form.description}
            onChange={(e) => update('description', e.target.value)}
            placeholder="Details to help someone recognize it"
          />
          {isFound && (
            <p className="field-callout">
              Public. Keep it general, and don't reveal your verification answer here.
            </p>
          )}
        </label>

        <div className="field photo-field">
          <span>Photos (optional, up to {MAX_PHOTOS})</span>
          <p className="photo-hint">A clear photo improves matching.</p>

          {previews.length > 0 && (
            <div className="photo-preview-grid">
              {previews.map((url, i) => (
                <div className="photo-thumb" key={url}>
                  <img src={url} alt={`Selected photo ${i + 1}`} />
                  <button
                    type="button"
                    className="photo-thumb-remove"
                    onClick={() => removePhoto(i)}
                    aria-label={`Remove photo ${i + 1}`}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          {photos.length < MAX_PHOTOS && (
            <label className="photo-picker-btn">
              + Add photo
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp,image/heic"
                multiple
                onChange={handlePhotoSelect}
                hidden
              />
            </label>
          )}
        </div>

        <div className="field-row">
          <label className="field">
            <span>Category *</span>
            <select
              required
              value={form.category}
              onChange={(e) => update('category', e.target.value)}
            >
              <option value="" disabled>
                Choose one
              </option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Color</span>
            <input value={form.color} onChange={(e) => update('color', e.target.value)} />
          </label>

          <label className="field">
            <span>Brand</span>
            <input value={form.brand} onChange={(e) => update('brand', e.target.value)} />
          </label>
        </div>

        <label className="field">
          <span>Where *</span>
          <input
            required
            value={form.location_name}
            onChange={(e) => update('location_name', e.target.value)}
            placeholder="e.g. Central Library"
          />
        </label>

        <div className="field-row">
          <label className="field">
            <span>Latitude</span>
            <input
              type="number"
              step="any"
              value={form.latitude}
              onChange={(e) => update('latitude', e.target.value)}
            />
          </label>
          <label className="field">
            <span>Longitude</span>
            <input
              type="number"
              step="any"
              value={form.longitude}
              onChange={(e) => update('longitude', e.target.value)}
            />
          </label>
          <button type="button" className="locate-btn" onClick={useMyLocation} disabled={locating}>
            {locating ? 'Locating…' : 'Use my location'}
          </button>
        </div>

        {!isFound && (
          <label className="field">
            <span>When you lost it *</span>
            <input
              type="datetime-local"
              required
              min={weekAgoLocal}
              max={nowLocal}
              value={form.item_datetime}
              onChange={(e) => update('item_datetime', e.target.value)}
            />
            <p className="photo-hint">
              Within the last two weeks. For an older loss, contact the lost &amp; found desk.
            </p>
          </label>
        )}

        {isFound && (
          <div className="verification-block">
            <p className="field-callout">
              <strong>Private.</strong> Ask something only the owner would know,
              not something from the description.
            </p>
            <label className="field">
              <span>Verification question *</span>
              <input
                required
                value={form.hidden_question}
                onChange={(e) => update('hidden_question', e.target.value)}
                placeholder="e.g. What's inside the front pocket?"
              />
            </label>
            <label className="field">
              <span>Expected answer *</span>
              <input
                required
                className={localLeak ? 'input-invalid' : ''}
                value={form.hidden_answer}
                onChange={(e) => update('hidden_answer', e.target.value)}
                placeholder="Never shown to claimants"
              />
              {localLeak ? (
                <p className="form-error">{ANSWER_LEAK_MESSAGE}</p>
              ) : verifyWarning ? (
                <p className="form-warning">
                  {verifyWarning.reason ||
                    'A claimant could answer this from your description.'}{' '}
                  A stronger question is safer.
                </p>
              ) : null}
            </label>
            <label className="field">
              <span>Where you'll hand it to admin *</span>
              <input
                required
                value={form.collection_point}
                onChange={(e) => update('collection_point', e.target.value)}
                placeholder="e.g. Main Gate security desk"
              />
              <p className="photo-hint">The owner collects it from here.</p>
            </label>

            <button
              type="button"
              className="preview-toggle"
              onClick={() => setShowPreview((v) => !v)}
              aria-expanded={showPreview}
            >
              {showPreview ? 'Hide preview' : 'Preview what claimants see'}
            </button>
            {showPreview && (
              <div className="claimant-preview">
                <p className="claimant-preview-label">Publicly visible</p>
                <p className="claimant-preview-title">{form.title || 'Untitled item'}</p>
                {form.description && <p>{form.description}</p>}
                <dl className="claimant-preview-meta">
                  {form.category && (
                    <div><dt>Category</dt><dd>{form.category}</dd></div>
                  )}
                  {form.color && <div><dt>Color</dt><dd>{form.color}</dd></div>}
                  {form.brand && <div><dt>Brand</dt><dd>{form.brand}</dd></div>}
                  {form.location_name && (
                    <div><dt>Where</dt><dd>{form.location_name}</dd></div>
                  )}
                </dl>
                <p className="claimant-preview-label">They're asked</p>
                <p>{form.hidden_question || '(no question yet)'}</p>
                <p className="claimant-preview-hidden">
                  If you can guess this from the text above, so can a stranger.
                </p>
              </div>
            )}
          </div>
        )}

        {error && <p className="form-error">{error}</p>}
        {uploadStatus === 'failed' && (
          <p className="form-warning">Report saved, but photo upload failed.</p>
        )}

        <button type="submit" className="submit-btn" disabled={submitting || localLeak}>
          {submitting
            ? uploadStatus === 'uploading'
              ? 'Uploading photos…'
              : 'Submitting…'
            : 'Submit report'}
        </button>
      </form>
    </div>
  );
}