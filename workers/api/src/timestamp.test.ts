import { describe, expect, it } from 'vitest';
import { timestampForOffset } from './timestamp';

const withMap = {
  cueMap: [
    [0, 100],
    [40, 112.5],
    [80, 125],
  ] as [number, number][],
  endS: 140,
  startS: 100,
  text: 'x'.repeat(120),
};

describe('timestampForOffset', () => {
  it('picks the cue that was being spoken at the quote', () => {
    expect(timestampForOffset(withMap, 0)).toBe(100);
    expect(timestampForOffset(withMap, 39)).toBe(100);
    expect(timestampForOffset(withMap, 40)).toBe(112.5);
    expect(timestampForOffset(withMap, 119)).toBe(125);
  });

  it('falls back to the segment start when the offset is unknown', () => {
    expect(timestampForOffset(withMap, null)).toBe(100);
    expect(timestampForOffset(withMap, -5)).toBe(100);
  });

  it('interpolates across segments captured before cue maps existed', () => {
    const legacy = { cueMap: null, endS: 200, startS: 100, text: 'y'.repeat(100) };
    expect(timestampForOffset(legacy, 0)).toBe(100);
    expect(timestampForOffset(legacy, 50)).toBe(150);
    expect(timestampForOffset(legacy, 100)).toBe(200);
  });

  it('never runs past the end of the segment', () => {
    const legacy = { cueMap: null, endS: 200, startS: 100, text: 'y'.repeat(100) };
    expect(timestampForOffset(legacy, 400)).toBe(200);
  });

  it('keeps the segment start when the segment has no measurable span', () => {
    const flat = { cueMap: null, endS: 100, startS: 100, text: '' };
    expect(timestampForOffset(flat, 10)).toBe(100);
  });
});
