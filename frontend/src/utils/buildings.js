/**
 * Single source of truth for the lost & found collection points --
 * mirrors app/models/building.py's Building enum on the backend. Every
 * report/admin ties to one of these short codes ("PRP"/"SJT"/"TT"); the
 * human-readable label lives only here so ReportForm's dropdown and
 * Admin's pickup table can never drift into showing different text for
 * the same code.
 */
export const COLLECTION_POINTS = [
  { value: 'PRP', label: 'PRP Lost and Found Office' },
  { value: 'SJT', label: 'SJT Lost and Found Office' },
  { value: 'TT', label: 'TT Lost and Found Office' },
];

const LABEL_BY_VALUE = Object.fromEntries(COLLECTION_POINTS.map((cp) => [cp.value, cp.label]));

/** "PRP" -> "PRP Lost and Found Office". Falls back to the raw code
 * (rather than blanking it) if a value ever shows up that isn't PRP/SJT/TT --
 * safer than silently hiding data admin might need to see. */
export function collectionPointLabel(value) {
  if (!value) return null;
  return LABEL_BY_VALUE[value] || value;
}