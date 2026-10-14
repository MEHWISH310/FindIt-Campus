/**
 * Single source of truth for the report form's category dropdown. Shared by
 * ReportForm and the voice assistant. backend/app/voice/extraction.py keeps
 * a mirror of this list (a pytest checks the two match).
 */
export const CATEGORIES = [
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
