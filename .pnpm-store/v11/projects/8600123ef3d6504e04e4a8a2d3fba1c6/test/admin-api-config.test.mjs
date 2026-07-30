import assert from 'node:assert/strict';
import test from 'node:test';

import {
  AdminConfigurationError,
  resolveAdminApiBaseUrl,
} from '../src/config/admin-api.ts';

test('uses a loopback default for the local Admin API', () => {
  assert.equal(resolveAdminApiBaseUrl(undefined), 'http://127.0.0.1:8000');
});

test('normalizes an allowed localhost URL', () => {
  assert.equal(
    resolveAdminApiBaseUrl(' http://localhost:8080/ '),
    'http://localhost:8080',
  );
});

test('rejects a non-loopback Admin API URL', () => {
  assert.throws(
    () => resolveAdminApiBaseUrl('https://admin.example.com'),
    AdminConfigurationError,
  );
});

test('rejects credentials and API paths in the base URL', () => {
  assert.throws(
    () => resolveAdminApiBaseUrl('http://user:pass@127.0.0.1:8000/api'),
    AdminConfigurationError,
  );
});
