import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('job wrappers preserve the optional source relocation receipt', async () => {
  const receipt = {
    contractVersion: 1,
    previous: 'C:/old/source',
    current: 'D:/new/source',
  };
  const job = {
    id: '11111111-1111-4111-8111-111111111111',
    inputPayload: {
      schemaVersion: 1,
      importKind: 'image_directory',
      sourceDirectory: receipt.current,
      sourceDirectoryRelocation: receipt,
    },
  };
  const paths = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      const path = new URL(request.url).pathname;
      paths.push(path);
      return Response.json(path.endsWith('/jobs') ? [job] : job);
    },
  });
  assert.deepEqual(
    (await api.getJob(job.id)).data?.inputPayload.sourceDirectoryRelocation,
    receipt,
  );
  assert.deepEqual(
    (await api.listJobs()).data?.[0].inputPayload.sourceDirectoryRelocation,
    receipt,
  );
  assert.deepEqual(paths, [
    `/api/v1/admin/jobs/${job.id}`,
    '/api/v1/admin/jobs',
  ]);
});
