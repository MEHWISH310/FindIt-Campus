/**
 * Pure helpers for the "Fill by Voice" flow -- no React, no browser APIs, so
 * they can be unit-tested (see voiceForm.test.js).
 *
 * Voice only ever produces a *patch* for the existing form state. Nothing
 * here submits anything.
 */
import { CATEGORIES } from './categories';

// Fields the voice assistant may send to the server (and therefore to
// Gemini). hidden_answer is deliberately NOT in this list: the verification
// answer is typed, never spoken and never sent.
const COMMON_KEYS = ['title', 'description', 'category', 'color', 'brand', 'location_name'];
export function voiceKeys(type) {
  return type === 'lost'
    ? [...COMMON_KEYS, 'item_datetime']
    : [...COMMON_KEYS, 'collection_point', 'hidden_question'];
}

// Required fields the assistant will ask about, in the order it asks.
export function requiredKeys(type) {
  const common = ['title', 'description', 'category', 'location_name'];
  return type === 'lost' ? [...common, 'item_datetime'] : [...common, 'collection_point', 'hidden_question'];
}

/** Only whitelisted, string-valued fields -- what gets sent to the server. */
export function pickVoiceFields(form, type) {
  const out = {};
  for (const key of voiceKeys(type)) {
    if (typeof form[key] === 'string' && form[key].trim() !== '') out[key] = form[key];
  }
  return out;
}

/** Required keys that are still empty, in asking order. */
export function getMissingFields(type, form) {
  return requiredKeys(type).filter((key) => !String(form[key] ?? '').trim());
}

const QUESTIONS = {
  title: 'What is the item? For example, a black wallet.',
  description: 'Can you describe it a little more, like marks, brand or condition?',
  category: `Which category fits best: ${CATEGORIES.join(', ')}?`,
  item_datetime: "Roughly when did you lose it? For example, yesterday afternoon. It has to be within the last two weeks.",
  collection_point: 'Where can the owner collect it: PRP, SJT or TT?',
  hidden_question:
    'What question could only the real owner answer, like what is inside the wallet? Please do not say the answer out loud. You will type it into the form.',
};

/** The follow-up question for a missing field (English only). */
export function followUpQuestion(key, type) {
  if (key === 'location_name') {
    return type === 'lost' ? 'Where do you think you lost it?' : 'Where did you find it?';
  }
  return QUESTIONS[key] || null;
}

const NOTE_MESSAGES = {
  'item_datetime:assumed_time': "I only heard the day, so I set a time. Please adjust it if it's wrong.",
  'item_datetime:future': "That time is in the future. Please tell me when you lost it again.",
  'item_datetime:too_old':
    'Items must be reported within the last two weeks. For an older loss, please contact the lost & found desk.',
  'item_datetime:invalid': "I couldn't work out the date. Please say it again, or set it in the form.",
  'category:invalid': "I couldn't match that to a category. Please pick one from the list.",
  'collection_point:invalid': 'The collection point must be PRP, SJT or TT.',
};

export function noteMessage(note) {
  return NOTE_MESSAGES[`${note.field}:${note.code}`] || null;
}

/**
 * Decide what the extracted values may change.
 *
 * A spoken value is applied when the field is empty, when it still holds
 * what the voice assistant put there earlier, or when the speaker explicitly
 * asked to change that field ("change the title to ..." -> `explicit`).
 * Text the user typed or edited themselves is otherwise left alone and
 * reported in `kept`. `voiceFilled` maps field -> last value the assistant
 * wrote.
 */
export function mergeVoiceFields(form, extracted, voiceFilled = {}, explicit = []) {
  const patch = {};
  const applied = [];
  const kept = [];
  const nextVoiceFilled = { ...voiceFilled };

  for (const [key, value] of Object.entries(extracted || {})) {
    if (typeof value !== 'string' || value.trim() === '') continue;
    const current = String(form[key] ?? '');
    if (current === value) continue;
    const untouched = current.trim() === '' || current === voiceFilled[key] || explicit.includes(key);
    if (untouched) {
      patch[key] = value;
      applied.push(key);
      nextVoiceFilled[key] = value;
    } else {
      kept.push(key);
    }
  }
  return { patch, applied, kept, nextVoiceFilled };
}

// datetime-local inputs want "YYYY-MM-DDTHH:mm" in *local* time (same
// format ReportForm uses). The server also receives this as the user's
// "now" so words like "yesterday" resolve in their own timezone.
export function toLocalInputValue(d) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const FIELD_LABELS = {
  title: 'Title',
  description: 'Description',
  category: 'Category',
  color: 'Colour',
  brand: 'Brand',
  location_name: 'Location',
  item_datetime: 'Date and time',
  collection_point: 'Collection point',
  hidden_question: 'Verification question',
};

// --- Spoken wording (English only) ---------------------------------------

export function greeting(type) {
  return type === 'found'
    ? 'Hi! Tell me about the item you found. What is it, and where did you find it?'
    : 'Hi! Tell me about the item you lost. What is it, where did you lose it, and when?';
}

export const SUBMIT_REFUSAL =
  "I can't submit the report for you. Please review the form and press Submit report yourself.";

function phrase(key, type) {
  switch (key) {
    case 'title': return 'what the item is';
    case 'description': return 'a short description';
    case 'category': return 'the category';
    case 'location_name': return type === 'lost' ? 'where you lost it' : 'where you found it';
    case 'item_datetime': return 'roughly when you lost it';
    case 'collection_point': return 'the collection point: PRP, SJT or TT';
    case 'hidden_question': return "a verification question only the owner could answer. Please don't say the answer out loud";
    default: return FIELD_LABELS[key] || key;
  }
}

export function joinList(items) {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** One spoken request for everything still missing (2 or more fields). */
export function combinedFollowUp(keys, type) {
  return `Please tell me ${joinList(keys.map((k) => phrase(k, type)))}.`;
}

export function completionMessage(type, answerTyped) {
  const typeIt = type === 'found' && !answerTyped ? ' Please type the verification answer yourself.' : '';
  return `All set.${typeIt} Review the form and press Submit report when you're ready. You can still tap the microphone to change anything.`;
}

/**
 * Builds the assistant's reply after one spoken turn. Pure, so it is tested
 * without a browser. `listenAfter` is true only while details are missing,
 * so the microphone never stays open on its own once the form is complete.
 */
export function buildReply({ type, notes = [], applied = [], kept = [], explicit = [], submitRequested = false, missing = [], answerTyped = false }) {
  const parts = [];
  if (submitRequested) parts.push(SUBMIT_REFUSAL);

  const updated = applied.filter((k) => explicit.includes(k));
  if (updated.length > 0) parts.push(`Updated ${joinList(updated.map((k) => FIELD_LABELS[k].toLowerCase()))}.`);

  if (kept.length > 0) {
    const label = FIELD_LABELS[kept[0]].toLowerCase();
    parts.push(`I kept what you typed in ${joinList(kept.map((k) => FIELD_LABELS[k].toLowerCase()))}. Say change the ${label}, if you want me to replace it.`);
  }

  let noteSpoken = false;
  notes.forEach((n) => {
    const msg = noteMessage(n);
    if (msg) {
      parts.push(msg);
      noteSpoken = true;
    }
  });

  if (applied.length === 0 && kept.length === 0 && !submitRequested && !noteSpoken) {
    parts.push(
      missing.length === 0
        ? "I didn't catch a change. Tell me what to change, for example, change the colour to blue."
        : "I didn't catch any details."
    );
  }

  let asking = null;
  if (missing.length === 1) {
    asking = missing[0];
    parts.push(followUpQuestion(missing[0], type));
  } else if (missing.length > 1) {
    asking = 'several';
    parts.push(combinedFollowUp(missing, type));
  } else if (!submitRequested) {
    parts.push(completionMessage(type, answerTyped));
  } else if (type === 'found' && !answerTyped) {
    parts.push('Remember to type the verification answer yourself.');
  }

  return { text: parts.join(' '), asking, listenAfter: missing.length > 0 };
}
