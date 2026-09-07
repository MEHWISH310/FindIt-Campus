// Mirror of backend/app/matching/leak_check.py -- kept in sync deliberately.
// Catches a verification answer that's already sitting in the public text,
// so ReportForm can warn (and block) before the request even goes out. The
// backend runs the same check as the authoritative gate.

const STOP = new Set([
  'the', 'a', 'an', 'is', 'it', 'in', 'on', 'of', 'with', 'and', 'or',
  'to', 'my', 'this', 'that', 'was', 'has', 'have', 'had', 'for', 'near',
  'at', 'by', 'its', 'as', 'be', 'am', 'are', 'no', 'yes', 'not', 'i',
  'found', 'lost', 'item', 'colour', 'color',
]);

function tokens(text) {
  return new Set(
    (text || '')
      .toLowerCase()
      .match(/[a-z0-9]+/g)
      ?.filter((t) => t.length >= 2 && !STOP.has(t)) ?? []
  );
}

/**
 * True when `answer` is substantially recoverable from `publicParts`:
 *   1. the whole answer (>=3 chars) appears verbatim, or
 *   2. >=80% of the answer's meaningful tokens appear in the public text.
 */
export function answerLeaks(answer, ...publicParts) {
  const ans = (answer || '').trim().toLowerCase();
  if (!ans) return false;

  const publicText = publicParts.filter(Boolean).join(' ').toLowerCase();

  if (ans.length >= 3 && publicText.includes(ans)) return true;

  const ansTokens = tokens(ans);
  if (ansTokens.size === 0) return false;

  const publicTokens = tokens(publicText);
  let hits = 0;
  for (const t of ansTokens) if (publicTokens.has(t)) hits += 1;
  return hits / ansTokens.size >= 0.8;
}
