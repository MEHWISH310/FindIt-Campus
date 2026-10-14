import { describe, expect, it } from 'vitest';
import { CATEGORIES } from './categories';
import {
  FIELD_LABELS,
  followUpQuestion,
  getMissingFields,
  mergeVoiceFields,
  noteMessage,
  pickVoiceFields,
  requiredKeys,
  toLocalInputValue,
  voiceKeys,
} from './voiceForm';

const blank = {
  title: '', description: '', category: '', color: '', brand: '', location_name: '',
  latitude: '', longitude: '', item_datetime: '', hidden_question: '', hidden_answer: '', collection_point: '',
};

describe('what may be sent to the server', () => {
  it('never includes hidden_answer for either report type', () => {
    expect(voiceKeys('lost')).not.toContain('hidden_answer');
    expect(voiceKeys('found')).not.toContain('hidden_answer');
    const form = { ...blank, title: 'Wallet', hidden_question: 'Lining colour?', hidden_answer: 'TOPSECRET' };
    expect(JSON.stringify(pickVoiceFields(form, 'found'))).not.toContain('TOPSECRET');
  });

  it('only sends non-empty whitelisted fields for the report type', () => {
    const form = { ...blank, title: 'Wallet', color: '  ', collection_point: 'PRP', latitude: '12.3' };
    expect(pickVoiceFields(form, 'found')).toEqual({ title: 'Wallet', collection_point: 'PRP' });
    expect(pickVoiceFields(form, 'lost')).toEqual({ title: 'Wallet' });
  });
});

describe('missing required fields', () => {
  it('lists lost requirements in asking order', () => {
    expect(getMissingFields('lost', blank)).toEqual(['title', 'description', 'category', 'location_name', 'item_datetime']);
  });

  it('lists found requirements, including collection point and question but not date', () => {
    const missing = getMissingFields('found', blank);
    expect(missing).toEqual(['title', 'description', 'category', 'location_name', 'collection_point', 'hidden_question']);
    expect(missing).not.toContain('item_datetime');
    expect(missing).not.toContain('hidden_answer'); // typed, never asked by voice
  });

  it('treats whitespace as missing and drops filled fields', () => {
    const form = { ...blank, title: 'Wallet', description: '   ', category: 'Wallet' };
    expect(getMissingFields('lost', form)).toEqual(['description', 'location_name', 'item_datetime']);
  });

  it('returns nothing when everything required is present', () => {
    const form = { ...blank, title: 'a', description: 'b', category: 'Keys', location_name: 'c', item_datetime: '2026-10-13T10:00' };
    expect(getMissingFields('lost', form)).toEqual([]);
  });
});

describe('follow-up questions', () => {
  it('has a question for every required field of both types', () => {
    for (const type of ['lost', 'found']) {
      for (const key of requiredKeys(type)) {
        expect(followUpQuestion(key, type), `${type}/${key}`).toBeTruthy();
      }
    }
  });

  it('adapts the location question to lost vs found', () => {
    expect(followUpQuestion('location_name', 'lost')).toMatch(/lose|lost/i);
    expect(followUpQuestion('location_name', 'found')).toMatch(/find|found/i);
  });

  it('offers exactly the real collection points and every category', () => {
    const cp = followUpQuestion('collection_point', 'found');
    expect(cp).toMatch(/PRP/);
    expect(cp).toMatch(/SJT/);
    expect(cp).toMatch(/TT/);
    const cat = followUpQuestion('category', 'lost');
    CATEGORIES.forEach((c) => expect(cat).toContain(c));
  });

  it('tells the finder not to say the verification answer aloud', () => {
    expect(followUpQuestion('hidden_question', 'found')).toMatch(/do not say the answer/i);
  });

  it('has a label for every field it can report', () => {
    for (const type of ['lost', 'found']) voiceKeys(type).forEach((k) => expect(FIELD_LABELS[k]).toBeTruthy());
  });
});

describe('merging spoken values into the form', () => {
  it('fills empty fields', () => {
    const r = mergeVoiceFields(blank, { title: 'Black wallet', category: 'Wallet' }, {});
    expect(r.patch).toEqual({ title: 'Black wallet', category: 'Wallet' });
    expect(r.applied).toEqual(['title', 'category']);
    expect(r.kept).toEqual([]);
    expect(r.nextVoiceFilled).toEqual({ title: 'Black wallet', category: 'Wallet' });
  });

  it('never overwrites something the user typed', () => {
    const form = { ...blank, title: 'My own title' };
    const r = mergeVoiceFields(form, { title: 'Voice title', color: 'Black' }, {});
    expect(r.patch).toEqual({ color: 'Black' });
    expect(r.kept).toEqual(['title']);
  });

  it('lets a spoken correction replace a value voice itself wrote', () => {
    const form = { ...blank, color: 'Black' };
    const r = mergeVoiceFields(form, { color: 'Blue' }, { color: 'Black' });
    expect(r.patch).toEqual({ color: 'Blue' });
    expect(r.nextVoiceFilled.color).toBe('Blue');
  });

  it('stops treating a voice-filled value as replaceable once the user edits it', () => {
    const form = { ...blank, color: 'Dark black' }; // user edited what voice wrote ("Black")
    const r = mergeVoiceFields(form, { color: 'Blue' }, { color: 'Black' });
    expect(r.patch).toEqual({});
    expect(r.kept).toEqual(['color']);
  });

  it('ignores empty, identical and non-string values', () => {
    const form = { ...blank, brand: 'Nike' };
    const r = mergeVoiceFields(form, { brand: 'Nike', color: '  ', title: 5, description: null }, {});
    expect(r.patch).toEqual({});
    expect(r.applied).toEqual([]);
    expect(r.kept).toEqual([]);
  });

  it('does not mutate its inputs', () => {
    const form = Object.freeze({ ...blank });
    const filled = Object.freeze({});
    expect(() => mergeVoiceFields(form, { title: 'x' }, filled)).not.toThrow();
  });
});

describe('notes and dates', () => {
  it('turns known server notes into messages and ignores unknown ones', () => {
    expect(noteMessage({ field: 'item_datetime', code: 'too_old' })).toMatch(/two weeks/);
    expect(noteMessage({ field: 'item_datetime', code: 'assumed_time' })).toMatch(/adjust/);
    expect(noteMessage({ field: 'nope', code: 'nope' })).toBeNull();
  });

  it('formats local time the way datetime-local inputs expect', () => {
    expect(toLocalInputValue(new Date(2026, 9, 14, 7, 5))).toBe('2026-10-14T07:05');
  });
});
