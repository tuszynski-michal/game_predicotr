import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const gatePath = new URL(
  '../src/features/access/reviewer-access-gate.tsx',
  import.meta.url,
);
const pagePath = new URL('../src/app/page.tsx', import.meta.url);

test('access gate describes both local and HTTPS private sessions accurately', async () => {
  const source = await readFile(gatePath, 'utf8');

  assert.match(source, /Prywatna sesja zatwierdzania/);
  assert.match(source, /Dostęp ograniczony kodem, grą i wybranym importem/);
  assert.doesNotMatch(source, /serwer dostępny wyłącznie na tym komputerze/);
});

test('loopback local mode opens the selected scope without an access code', async () => {
  const gate = await readFile(gatePath, 'utf8');
  const page = await readFile(pagePath, 'utf8');

  assert.match(gate, /localScope !== null/);
  assert.match(gate, /gameId={localScope\.gameId}/);
  assert.match(page, /isLoopbackReviewerHost/);
  assert.match(page, /value\(params\.mode\) === 'local'/);
  assert.match(page, /resolveLocalAdminApiBaseUrl/);
  assert.match(page, /UUID\.test\(gameId\)/);
  assert.match(page, /UUID\.test\(importJobId\)/);
});
