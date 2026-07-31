import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const gatePath = new URL(
  '../src/features/access/reviewer-access-gate.tsx',
  import.meta.url,
);

test('access gate describes both local and HTTPS private sessions accurately', async () => {
  const source = await readFile(gatePath, 'utf8');

  assert.match(source, /Prywatna sesja zatwierdzania/);
  assert.match(source, /Dostęp ograniczony kodem, grą i wybranym importem/);
  assert.doesNotMatch(source, /serwer dostępny wyłącznie na tym komputerze/);
});
