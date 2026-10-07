import assert from 'node:assert/strict';
import test from 'node:test';

import { localV7PilotHref } from '../src/features/semi-automatic-image-selection/local-v7-pilot-entry.ts';

test('opens the local pilot with only its workspace, without database identities', () => {
  assert.equal(
    localV7PilotHref('http://127.0.0.1:3000'),
    'http://127.0.0.1:3020/?workspace=semi-automatic-image-selection',
  );
  assert.equal(
    localV7PilotHref('http://localhost:3000'),
    'http://localhost:3020/?workspace=semi-automatic-image-selection',
  );
  assert.equal(
    localV7PilotHref('http://[::1]:3000'),
    'http://[::1]:3020/?workspace=semi-automatic-image-selection',
  );
});

test('accepts a configured local origin and rejects a self link', () => {
  assert.equal(
    localV7PilotHref('http://localhost:3000', 'http://127.0.0.1:3030/'),
    'http://127.0.0.1:3030/?workspace=semi-automatic-image-selection',
  );
  assert.equal(localV7PilotHref('http://localhost:3020'), null);
  assert.equal(
    localV7PilotHref('http://localhost:3000', 'http://localhost:3000'),
    null,
  );
});

test('an explicitly empty override disables the entry', () => {
  for (const override of ['', '   ']) {
    assert.equal(localV7PilotHref('http://localhost:3000', override), null);
  }
});

test('never points a remote application to a local pilot', () => {
  for (const origin of [
    'https://example.com',
    'http://192.168.1.2:3000',
    'http://localhost.example.com:3000',
    'https://localhost:3000',
    'invalid',
  ]) {
    assert.equal(localV7PilotHref(origin), null);
    assert.equal(localV7PilotHref(origin, 'http://localhost:3020'), null);
  }
});

test('rejects credentials, non-local targets and extra URL context', () => {
  for (const override of [
    'https://localhost:3020',
    'http://example.com:3020',
    'http://user:password@localhost:3020',
    'http://localhost:3020/another-panel',
    'http://localhost:3020/?game=main-game',
    'http://localhost:3020/#main-run',
    'javascript:alert(1)',
    '/relative',
  ]) {
    assert.equal(localV7PilotHref('http://localhost:3000', override), null);
    assert.equal(localV7PilotHref(override), null);
  }
});
