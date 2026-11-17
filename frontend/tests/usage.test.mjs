import assert from 'node:assert/strict';
import { test } from 'node:test';
import { barHeights, formatCost, formatPercent, isUsagePath } from '../src/usage.js';

test('the Usage dashboard has its own address', () => {
  assert.equal(isUsagePath('/usage'), true);
  assert.equal(isUsagePath('/usage/'), true);
  assert.equal(isUsagePath('/'), false);
  assert.equal(isUsagePath('/usage/5'), false);
  assert.equal(isUsagePath(undefined), false);
});

test('cost shows unavailable, marks estimates and keeps small amounts readable', () => {
  assert.equal(formatCost(null), 'Unavailable');
  assert.equal(formatCost(0.0123), '$0.0123');
  assert.equal(formatCost(12.345, true), '~$12.35');
});

test('failure rate is a percentage and a dash when nothing ran', () => {
  assert.equal(formatPercent(null), '—');
  assert.equal(formatPercent(0.25), '25%');
  assert.equal(formatPercent(0.025), '2.5%');
});

test('bars scale to the busiest day and tiny days stay visible', () => {
  const daily = [{ date: 'a', total_tokens: 1000 }, { date: 'b', total_tokens: 5 }, { date: 'c', total_tokens: 0 }, { date: 'd', total_tokens: 500 }];
  assert.deepEqual(barHeights(daily, 'total_tokens').map(bar => bar.height), [100, 2, 0, 50]);
  assert.deepEqual(barHeights([{ date: 'a', cost_usd: null }], 'cost_usd').map(bar => bar.height), [0]);
});
