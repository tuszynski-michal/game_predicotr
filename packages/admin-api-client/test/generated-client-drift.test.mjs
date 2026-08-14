import assert from 'node:assert/strict';
import test from 'node:test';

import { assertSameGeneratedEntries } from '../scripts/generated-client-drift.mjs';

test('generated client drift ignores Windows and Unix line-ending differences', () => {
  const current = new Map([
    ['types.gen.ts', 'export type Health = {\r\n  status: string;\r\n};\r\n'],
  ]);
  const expected = new Map([
    ['types.gen.ts', 'export type Health = {\n  status: string;\n};\n'],
  ]);

  assert.doesNotThrow(() => assertSameGeneratedEntries(current, expected));
});

test('generated client drift still rejects a semantic content change', () => {
  const current = new Map([['types.gen.ts', 'export type Health = "ok";\r\n']]);
  const expected = new Map([
    ['types.gen.ts', 'export type Health = "error";\n'],
  ]);

  assert.throws(
    () => assertSameGeneratedEntries(current, expected),
    /Generated Admin API file is stale: types\.gen\.ts at character 22/,
  );
});
