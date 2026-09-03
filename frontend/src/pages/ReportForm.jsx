import { useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { createReport, uploadPhotos, ApiError } from '../api/client';

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

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

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
      setError(`${tooBig.name} is over 8MB — pick a smaller photo.`);
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
        setError('Could not read your location — enter it manually below.');
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
    if (isFound && !form.collection_point.trim()) {
      setError('Tell us where admin will be holding this item so the owner knows where to collect it.');
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
        item_datetime: form.item_datetime ? new Date(form.item_datetime).toISOString() : null,
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
          <span>Title</span>
          <input
            required
            value={form.title}
            onChange={(e) => update('title', e.target.value)}
            placeholder={isFound ? 'e.g. Black wallet' : 'e.g. Black wallet near library'}
          />
        </label>

        <label className="field">
          <span>Description</span>
          <textarea
            required
            rows={3}
            value={form.description}
            onChange={(e) => update('description', e.target.value)}
            placeholder="Details that would help someone recognize it"
          />
        </label>

        <div className="field photo-field">
          <span>Photos (optional, up to {MAX_PHOTOS})</span>
          <p className="photo-hint">
            A clear photo makes matching much more reliable — the system compares
            photos across reports, not just descriptions.
          </p>

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
            <span>Category</span>
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
          <span>Where</span>
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

        <label className="field">
          <span>{isFound ? 'When you found it' : 'When you lost it'}</span>
          <input
            type="datetime-local"
            required
            value={form.item_datetime}
            onChange={(e) => update('item_datetime', e.target.value)}
          />
        </label>

        {isFound && (
          <div className="verification-block">
            <p className="verification-note">
              Ask something only the real owner would know — this is used to confirm a claim before handoff.
            </p>
            <label className="field">
              <span>Verification question *</span>
              <input
                required
                value={form.hidden_question}
                onChange={(e) => update('hidden_question', e.target.value)}
                placeholder="e.g. What's inside the wallet's front pocket?"
              />
            </label>
            <label className="field">
              <span>Expected answer (optional, kept private)</span>
              <input
                value={form.hidden_answer}
                onChange={(e) => update('hidden_answer', e.target.value)}
              />
            </label>
            <label className="field">
              <span>Where will you hand this item over to admin? *</span>
              <input
                required
                value={form.collection_point}
                onChange={(e) => update('collection_point', e.target.value)}
                placeholder="e.g. Main Gate security desk"
              />
              <p className="photo-hint">
                Once handed over, the owner will be told to collect it from here.
              </p>
            </label>
          </div>
        )}

        {error && <p className="form-error">{error}</p>}
        {uploadStatus === 'failed' && (
          <p className="form-warning">
            Report saved, but photo upload failed — you can still find matches on the
            description alone.
          </p>
        )}

        <button type="submit" className="submit-btn" disabled={submitting}>
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