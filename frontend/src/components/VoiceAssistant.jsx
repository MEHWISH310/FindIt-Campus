import { useEffect, useRef, useState } from 'react';
import { extractVoiceFields, ApiError } from '../api/client';
import { useSpeechRecognition, canSpeak, speak, stopSpeaking } from '../hooks/useSpeechRecognition';
import {
  FIELD_LABELS,
  buildReply,
  getMissingFields,
  greeting,
  mergeVoiceFields,
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
  unsupported: "This browser can't recognise English speech here. Please fill in the form below by hand.",
  other: 'Speech recognition stopped unexpectedly. Try again, or fill in the form below by hand.',
};

/**
 * "Fill by Voice" panel. English only, mostly hands-free.
 *
 * Opening it speaks a greeting and then listens. After every spoken reply
 * the assistant listens again, as long as required details are still
 * missing. Once the form is complete it stops listening by itself; tap the
 * microphone to change anything else by voice.
 *
 * It only ever writes into the same form state the user can edit by hand
 * (via onApply). It never submits: the form's own "Submit report" button is
 * the only way to save a report, and a spoken "submit" just gets a reminder.
 */
export default function VoiceAssistant({ type, form, onApply, onClose }) {
  const isFound = type === 'found';
  const [messages, setMessages] = useState([]);
  const [caption, setCaption] = useState('');
  const [showTranscript, setShowTranscript] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [readAloud, setReadAloud] = useState(true);

  const nextId = useRef(1);
  const aliveRef = useRef(false);
  const formRef = useRef(form);
  formRef.current = form;
  const voiceFilledRef = useRef({}); // field -> last value the assistant wrote
  const askingRef = useRef(null); // field (or 'several') the last question was about
  const readAloudRef = useRef(readAloud);
  readAloudRef.current = readAloud;
  const startRef = useRef(() => {});
  const listEnd = useRef(null);

  // Show the reply as a caption, keep it for the optional transcript, speak
  // it, and (when asked) start listening as soon as the speaking ends.
  function say(text, { listenAfter = false } = {}) {
    setMessages((m) => [...m, { id: nextId.current++, role: 'assistant', text }]);
    setCaption(text);
    if (readAloudRef.current && canSpeak()) {
      setSpeaking(true);
      speak(text, () => {
        if (!aliveRef.current) return;
        setSpeaking(false);
        if (listenAfter) startRef.current();
      });
    }
  }

  async function handleTranscript(text) {
    setMessages((m) => [...m, { id: nextId.current++, role: 'user', text }]);
    setThinking(true);
    try {
      const res = await extractVoiceFields({
        report_type: type,
        transcript: text,
        current_fields: pickVoiceFields(formRef.current, type),
        asking_for: askingRef.current,
        client_now: toLocalInputValue(new Date()),
      });

      const explicit = res.explicit || [];
      const { patch, applied, kept, nextVoiceFilled } = mergeVoiceFields(
        formRef.current,
        res.fields,
        voiceFilledRef.current,
        explicit
      );
      voiceFilledRef.current = nextVoiceFilled;
      if (applied.length > 0) onApply(patch);

      const merged = { ...formRef.current, ...patch };
      const reply = buildReply({
        type,
        notes: res.notes || [],
        applied,
        kept,
        explicit,
        submitRequested: Boolean(res.submit_requested),
        missing: getMissingFields(type, merged),
        answerTyped: String(merged.hidden_answer || '').trim() !== '',
      });
      askingRef.current = reply.asking;
      say(reply.text, { listenAfter: reply.listenAfter });
    } catch (err) {
      let msg;
      if (err instanceof ApiError && err.status === 401) {
        msg = 'Your session has expired. Please log in again.';
      } else if (err instanceof ApiError) {
        msg = err.message;
      } else {
        msg = "I couldn't reach the server. You can fill in the form below by hand.";
      }
      say(msg); // no auto-listen after a failure: the user decides when to retry
    } finally {
      setThinking(false);
    }
  }

  const { supported, listening, interim, error, start, stop } = useSpeechRecognition({
    onFinal: handleTranscript,
  });
  startRef.current = start;

  // Greet out loud as soon as the panel opens (the click on "Fill by Voice"
  // allows audio), then listen.
  useEffect(() => {
    aliveRef.current = true;
    setMessages([]);
    if (supported) say(greeting(type), { listenAfter: true });
    return () => {
      aliveRef.current = false;
      stopSpeaking();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Silence: say so once and wait for a tap instead of listening forever.
  useEffect(() => {
    if (error === 'no-speech') say("I didn't hear anything. Tap the microphone when you're ready.");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [error]);

  useEffect(() => {
    listEnd.current?.scrollIntoView?.({ block: 'nearest' });
  }, [messages, showTranscript]);

  function toggleMic() {
    if (listening) {
      stop();
    } else {
      if (speaking) {
        stopSpeaking(); // skip the rest of the sentence; don't let the mic hear it
        setSpeaking(false);
      }
      start();
    }
  }

  const checklist = requiredKeys(type).map((key) => ({
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

  const micLabel = listening
    ? 'Listening… tap to stop'
    : thinking
      ? 'Working…'
      : speaking
        ? 'Speaking… tap to skip'
        : 'Tap to speak';

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
          <p className="voice-caption" aria-live="polite">
            {caption}
          </p>
          {interim && <p className="voice-caption voice-caption--user">{interim}…</p>}

          {error && error !== 'no-speech' && (
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
              {micLabel}
            </button>
            <button
              type="button"
              className="voice-link-btn"
              onClick={() => setShowTranscript((v) => !v)}
              aria-expanded={showTranscript}
            >
              {showTranscript ? 'Hide transcript' : 'Show transcript'}
            </button>
            {canSpeak() && (
              <label className="voice-toggle">
                <input
                  type="checkbox"
                  checked={readAloud}
                  onChange={(e) => {
                    setReadAloud(e.target.checked);
                    if (!e.target.checked) {
                      stopSpeaking();
                      setSpeaking(false);
                    }
                  }}
                />
                Speak replies
              </label>
            )}
          </div>

          {showTranscript && (
            <div className="voice-messages" aria-label="Transcript">
              {messages.map((m) => (
                <p key={m.id} className={`voice-bubble voice-bubble--${m.role}`}>
                  {m.text}
                </p>
              ))}
              <div ref={listEnd} />
            </div>
          )}

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

      <details className="voice-privacy">
        <summary>Privacy and browser notes</summary>
        <p>
          Speech is turned into text by your browser's speech service. In Chrome this usually sends your
          audio to Google, so it needs an internet connection and isn't guaranteed to be private or
          offline. The text is then sent to this app's server and to Gemini to fill the form, and is not
          stored. The voice you hear depends on your device and browser. Never say your verification
          answer out loud. You can edit every field, and nothing is submitted until you press "Submit
          report".
        </p>
      </details>
    </section>
  );
}
