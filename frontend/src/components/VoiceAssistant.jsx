import { useEffect, useRef, useState } from 'react';
import { extractVoiceFields, ApiError } from '../api/client';
import { useSpeechRecognition, canSpeak, speak, stopSpeaking } from '../hooks/useSpeechRecognition';
import {
  FIELD_LABELS,
  followUpQuestion,
  getMissingFields,
  mergeVoiceFields,
  noteMessage,
  pickVoiceFields,
  requiredKeys,
  toLocalInputValue,
} from '../utils/voiceForm';
import MicIcon from './MicIcon';

const SPEECH_ERRORS = {
  permission:
    "Microphone access was blocked. Allow the microphone in your browser's site settings, or fill in the form below by hand.",
  'no-mic': "I couldn't find a microphone. You can fill in the form below by hand.",
  network:
    "Your browser's speech service couldn't be reached. Check your connection, or fill in the form below by hand.",
  'no-speech': "I didn't hear anything. Tap the microphone and try again.",
  unsupported: "This browser can't recognise English speech here. Please fill in the form below by hand.",
  other: 'Speech recognition stopped unexpectedly. Try again, or fill in the form below by hand.',
};

/**
 * "Fill by Voice" panel. English only.
 *
 * It listens (browser Web Speech API), sends the transcript to the backend's
 * /voice-form/extract, and writes the answers into the SAME form state the
 * user can edit by hand (via onApply). It never submits anything: the form's
 * own "Submit report" button is still the only way to save a report.
 */
export default function VoiceAssistant({ type, form, onApply, onClose }) {
  const isFound = type === 'found';
  const [messages, setMessages] = useState(() => [
    {
      id: 0,
      role: 'assistant',
      text: isFound
        ? 'Tap the microphone and tell me about the item you found, in English. For example: "I found a black wallet near the library."'
        : 'Tap the microphone and tell me about the item you lost, in English. For example: "I lost a blue bottle in the canteen yesterday afternoon."',
    },
  ]);
  const [thinking, setThinking] = useState(false);
  const [readAloud, setReadAloud] = useState(true);

  const nextId = useRef(1);
  const formRef = useRef(form);
  formRef.current = form;
  const voiceFilledRef = useRef({}); // field -> last value the assistant wrote
  const askingRef = useRef(null); // field the last question was about
  const readAloudRef = useRef(readAloud);
  readAloudRef.current = readAloud;
  const listEnd = useRef(null);

  function addMessage(role, text, { speakIt = false } = {}) {
    setMessages((m) => [...m, { id: nextId.current++, role, text }]);
    if (speakIt && readAloudRef.current) speak(text);
  }

  async function handleTranscript(text) {
    addMessage('user', text);
    setThinking(true);
    try {
      const res = await extractVoiceFields({
        report_type: type,
        transcript: text,
        current_fields: pickVoiceFields(formRef.current, type),
        asking_for: askingRef.current,
        client_now: toLocalInputValue(new Date()),
      });

      const { patch, applied, kept, nextVoiceFilled } = mergeVoiceFields(
        formRef.current,
        res.fields,
        voiceFilledRef.current
      );
      voiceFilledRef.current = nextVoiceFilled;
      if (applied.length > 0) onApply(patch);

      const parts = [];
      if (applied.length > 0) parts.push(`Filled in: ${applied.map((k) => FIELD_LABELS[k]).join(', ')}.`);
      if (kept.length > 0) {
        parts.push(`I left what you typed in ${kept.map((k) => FIELD_LABELS[k]).join(', ')} unchanged.`);
      }
      (res.notes || []).forEach((n) => {
        const msg = noteMessage(n);
        if (msg) parts.push(msg);
      });
      if (applied.length === 0 && kept.length === 0 && parts.length === 0) {
        parts.push("I didn't catch any details in that.");
      }

      const missing = getMissingFields(type, { ...formRef.current, ...patch });
      if (missing.length > 0) {
        askingRef.current = missing[0];
        parts.push(followUpQuestion(missing[0], type));
      } else {
        askingRef.current = null;
        const typedAnswerNeeded = isFound && !String(formRef.current.hidden_answer || '').trim();
        parts.push(
          typedAnswerNeeded
            ? 'The spoken details are done. Please type the verification answer in the form, review every field, and press "Submit report" when you are ready.'
            : 'Everything required is filled in. Please review every field and press "Submit report" when you are ready.'
        );
      }
      addMessage('assistant', parts.join(' '), { speakIt: true });
    } catch (err) {
      let text;
      if (err instanceof ApiError && err.status === 401) {
        text = 'Your session has expired. Please log in again.';
      } else if (err instanceof ApiError) {
        text = err.message;
      } else {
        text = "I couldn't reach the server. You can fill in the form below by hand.";
      }
      addMessage('assistant', text);
    } finally {
      setThinking(false);
    }
  }

  const { supported, listening, interim, error, start, stop } = useSpeechRecognition({
    onFinal: handleTranscript,
  });

  function toggleMic() {
    if (listening) {
      stop();
    } else {
      stopSpeaking(); // don't let the mic hear the assistant
      start();
    }
  }

  // Stop reading aloud when the panel closes.
  useEffect(() => stopSpeaking, []);
  useEffect(() => {
    listEnd.current?.scrollIntoView?.({ block: 'nearest' });
  }, [messages, interim]);

  const required = requiredKeys(type);
  const checklist = required.map((key) => ({
    key,
    label: FIELD_LABELS[key],
    done: String(form[key] ?? '').trim() !== '',
  }));
  if (isFound) {
    checklist.push({
      key: 'hidden_answer',
      label: 'Verification answer (type it in the form)',
      done: String(form.hidden_answer ?? '').trim() !== '',
    });
  }

  return (
    <section className={`voice-panel voice-panel--${type}`} aria-label="Fill by voice">
      <header className="voice-panel__head">
        <h2>
          <MicIcon size={16} /> Fill by Voice <span className="voice-panel__lang">English only</span>
        </h2>
        <button type="button" className="voice-panel__close" onClick={onClose}>
          Close
        </button>
      </header>

      {!supported ? (
        <p className="voice-notice" role="alert">
          Voice input isn't supported in this browser. Chrome or Edge work best. You can fill in the
          form below by hand.
        </p>
      ) : (
        <>
          <div className="voice-messages" aria-live="polite">
            {messages.map((m) => (
              <p key={m.id} className={`voice-bubble voice-bubble--${m.role}`}>
                {m.text}
              </p>
            ))}
            {interim && <p className="voice-bubble voice-bubble--user voice-bubble--interim">{interim}…</p>}
            {thinking && <p className="voice-bubble voice-bubble--assistant status-pulse">Working on it…</p>}
            <div ref={listEnd} />
          </div>

          {error && (
            <p className="voice-notice" role="alert">
              {SPEECH_ERRORS[error] || SPEECH_ERRORS.other}
            </p>
          )}

          <div className="voice-controls">
            <button
              type="button"
              className={`voice-mic${listening ? ' voice-mic--on' : ''}`}
              onClick={toggleMic}
              disabled={thinking}
              aria-pressed={listening}
            >
              <MicIcon size={18} />
              {listening ? 'Listening… tap to stop' : thinking ? 'Working…' : 'Tap to speak'}
            </button>
            {canSpeak() && (
              <label className="voice-toggle">
                <input type="checkbox" checked={readAloud} onChange={(e) => setReadAloud(e.target.checked)} />
                Read questions aloud
              </label>
            )}
          </div>

          <ul className="voice-checklist" aria-label="Required details">
            {checklist.map((c) => (
              <li key={c.key} className={c.done ? 'voice-check voice-check--done' : 'voice-check'}>
                <span aria-hidden="true">{c.done ? '✓' : '○'}</span> {c.label}
                <span className="sr-only">{c.done ? ' (filled)' : ' (missing)'}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="voice-privacy">
        Speech is turned into text by your browser's speech service. In Chrome this usually sends your
        audio to Google, so it needs an internet connection and isn't guaranteed to be private or
        offline. The text is then sent to this app's server and to Gemini to fill the form, and is not
        stored. Never say your verification answer out loud. You can edit every field and nothing is
        submitted until you press "Submit report".
      </p>
    </section>
  );
}
