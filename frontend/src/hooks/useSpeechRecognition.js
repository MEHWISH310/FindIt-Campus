import { useCallback, useEffect, useRef, useState } from 'react';
import { pickFemaleVoice } from '../utils/speechVoice';

// English only. Change this one constant for another English variant
// (e.g. 'en-US', 'en-GB'). No other languages are supported on purpose.
export const SPEECH_LOCALE = 'en-IN';

export function getSpeechRecognitionClass() {
  if (typeof window === 'undefined') return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

// SpeechRecognition error codes -> something we can explain to the user.
function classifyError(code) {
  switch (code) {
    case 'not-allowed':
    case 'service-not-allowed':
      return 'permission';
    case 'audio-capture':
      return 'no-mic';
    case 'network':
      return 'network';
    case 'no-speech':
      return 'no-speech';
    case 'language-not-supported':
      return 'unsupported';
    default:
      return 'other';
  }
}

/**
 * Thin wrapper over the browser's Web Speech API (no API key, no extra
 * dependency). Support and behaviour depend on the browser: Chrome/Edge
 * work best, and Chrome sends the audio to Google's speech service.
 *
 * onFinal(text) is called once per utterance with the final transcript.
 * `error` is null or one of: permission | no-mic | network | no-speech |
 * unsupported | other.
 */
export function useSpeechRecognition({ onFinal }) {
  const Recognition = getSpeechRecognitionClass();
  const supported = Boolean(Recognition);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState(null);
  const recRef = useRef(null);
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;

  const stop = useCallback(() => {
    try {
      recRef.current?.stop();
    } catch {
      /* already stopped */
    }
  }, []);

  const start = useCallback(() => {
    if (!Recognition || recRef.current) return;
    setError(null);
    setInterim('');
    const rec = new Recognition();
    rec.lang = SPEECH_LOCALE;
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;

    let finalText = '';
    rec.onstart = () => setListening(true);
    rec.onresult = (event) => {
      let live = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) finalText += `${result[0].transcript} `;
        else live += result[0].transcript;
      }
      setInterim(live);
    };
    rec.onerror = (event) => {
      if (event.error !== 'aborted') setError(classifyError(event.error));
    };
    rec.onend = () => {
      setListening(false);
      setInterim('');
      recRef.current = null;
      const text = finalText.trim();
      if (text) onFinalRef.current?.(text);
    };

    recRef.current = rec;
    try {
      rec.start();
    } catch {
      recRef.current = null;
      setError('other');
    }
  }, [Recognition]);

  // Stop the microphone if the panel is closed or the page navigates away.
  useEffect(() => {
    return () => {
      try {
        recRef.current?.abort();
      } catch {
        /* ignore */
      }
    };
  }, []);

  return { supported, listening, interim, error, start, stop };
}

/** Spoken replies use the browser's built-in speech synthesis (free, no key). */
export function canSpeak() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
}

// Chrome fills its voice list asynchronously after the first request, so ask
// once when this file loads. By the time someone opens the panel the list is
// ready and the female voice can be chosen for the very first sentence.
if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
  window.speechSynthesis.getVoices();
}

// Each speak() call gets a number; a cancelled or replaced utterance must not
// fire its onEnd callback (that would start the microphone at the wrong time).
let speakToken = 0;

/**
 * Speaks `text` in a female English voice when the device has one (see
 * utils/speechVoice.js). `onEnd` is called once when speaking finishes, or
 * after a safety timeout because some browsers never report the end.
 */
export function speak(text, onEnd) {
  const token = ++speakToken;
  if (!canSpeak()) {
    onEnd?.();
    return;
  }
  let finished = false;
  let timer = null;
  const finish = () => {
    if (finished || token !== speakToken) return;
    finished = true;
    clearTimeout(timer);
    onEnd?.();
  };

  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = SPEECH_LOCALE;
  const voice = pickFemaleVoice(window.speechSynthesis.getVoices());
  if (voice) {
    utterance.voice = voice;
    utterance.lang = voice.lang;
  }
  utterance.rate = 1;
  utterance.pitch = 1.05;
  utterance.onend = finish;
  utterance.onerror = finish;
  timer = setTimeout(finish, Math.max(3000, text.length * 90 + 2000));
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking() {
  speakToken += 1; // invalidates any pending onEnd
  if (canSpeak()) window.speechSynthesis.cancel();
}
