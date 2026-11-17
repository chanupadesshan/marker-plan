import assert from 'node:assert/strict';
import { test } from 'node:test';
import { nestingErrors, nestingPayload, nestingSizes } from '../src/nesting.js';
test('verified nesting requires verified whole ratios within table length', () => {
  const marker = { label: 'Manual 1', length_m: '7.30', verified: true,
    size_rows: [{ size: 'S', quantity: '2' }, { size: 'M', quantity: '2' }] };
  assert.deepEqual(nestingErrors([marker], '8', ['S','M']), []);
  for (const patch of [{ verified: false }, { length_m: '8.01' }, { size_rows: [{ size: 'S', quantity: '1.5' }] },
    { size_rows: [{ size: 'Unknown', quantity: '1' }] }]) assert.ok(nestingErrors([{ ...marker, ...patch }], '8', ['S','M']).length);
  assert.deepEqual(nestingPayload([marker])[0].size_rows, [{ size: 'S', quantity: 2 }, { size: 'M', quantity: 2 }]);
  assert.deepEqual(nestingSizes([{ size_rows: [{ size: ' S ' }, { size: 'M' }, { size: 's' }] }]), ['S','M']);
});
