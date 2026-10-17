/**
 * Picks a female English voice for the assistant's spoken replies.
 *
 * The browser's built-in speech synthesis only offers whatever voices the
 * device has installed, and it does not label them male/female, so this goes
 * by well-known voice names (macOS, Windows, Edge, Chrome). If none of them
 * is installed it returns null and the browser's default English voice is
 * used. Which voice you hear therefore depends on the device and browser.
 * Pure function so it can be unit-tested.
 */

// Names that are known to be male: never picked.
const MALE = /\b(daniel|alex|fred|rishi|ravi|david|mark|george|james|guy|ryan|prabhat|thomas|oliver|arthur|aaron|gordon|eddy|male)\b/i;

// Female voices in order of preference. Indian-English voices come first.
const PREFERRED = [
  /veena/i, /neerja/i, /heera/i,
  /google uk english female/i,
  /samantha/i, /karen/i, /moira/i, /tessa/i, /serena/i, /fiona/i,
  /aria/i, /jenny/i, /zira/i, /sonia/i, /libby/i, /hazel/i, /susan/i,
  /kate/i, /victoria/i, /allison/i, /ava/i,
  /female/i,
  /google us english/i,
];

export function pickFemaleVoice(voices) {
  const english = (voices || []).filter((v) => /^en([-_]|$)/i.test(v.lang || ''));
  let best = null;
  let bestScore = Infinity;
  for (const voice of english) {
    const name = voice.name || '';
    if (MALE.test(name)) continue;
    const rank = PREFERRED.findIndex((re) => re.test(name));
    if (rank < 0) continue;
    if (rank < bestScore) {
      best = voice;
      bestScore = rank;
    }
  }
  return best;
}
