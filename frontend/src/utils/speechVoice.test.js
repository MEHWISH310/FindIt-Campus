import { describe, expect, it } from 'vitest';
import { pickFemaleVoice } from './speechVoice';

const v = (name, lang = 'en-US') => ({ name, lang });

describe('pickFemaleVoice', () => {
  it('prefers an Indian-English female voice when available', () => {
    const voices = [v('Samantha'), v('Daniel', 'en-GB'), v('Veena', 'en-IN'), v('Karen', 'en-AU')];
    expect(pickFemaleVoice(voices).name).toBe('Veena');
  });

  it('picks a known female voice and never a male one', () => {
    expect(pickFemaleVoice([v('Daniel', 'en-GB'), v('Alex'), v('Samantha')]).name).toBe('Samantha');
    expect(pickFemaleVoice([v('Daniel', 'en-GB'), v('Alex'), v('Fred')])).toBeNull();
  });

  it('works with Windows, Edge and Chrome voice names', () => {
    expect(pickFemaleVoice([v('Microsoft David - English (United States)'), v('Microsoft Zira - English (United States)')]).name).toMatch(/Zira/);
    expect(pickFemaleVoice([v('Microsoft Neerja Online (Natural) - English (India)', 'en-IN'), v('Microsoft Aria Online (Natural)')]).name).toMatch(/Neerja/);
    expect(pickFemaleVoice([v('Google UK English Female', 'en-GB'), v('Google US English')]).name).toBe('Google UK English Female');
  });

  it('ignores non-English voices and handles empty input', () => {
    expect(pickFemaleVoice([v('Samantha', 'hi-IN'), v('Amelie', 'fr-CA')])).toBeNull();
    expect(pickFemaleVoice([])).toBeNull();
    expect(pickFemaleVoice(undefined)).toBeNull();
  });

  it('does not mistake "female" for "male"', () => {
    expect(pickFemaleVoice([v('Some Female Voice')]).name).toBe('Some Female Voice');
  });
});
