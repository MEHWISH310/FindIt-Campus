import { useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { createReport, ApiError } from '../api/client';

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
};

export default function ReportForm() {
  const { type } = useParams(); // 'lost' | 'found'
  const isFound = type === 'found';
  const navigate = useNavigate();

  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [locating, setLocating] = useState(false);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
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
      };
      const report = await createReport(payload);
      navigate(`/matches/${report.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong submitting the report.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="report-page">
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
          </div>
        )}

        {error && <p className="form-error">{error}</p>}

        <button type="submit" className="submit-btn" disabled={submitting}>
          {submitting ? 'Submitting…' : 'Submit report'}
        </button>
      </form>
    </div>
  );
}