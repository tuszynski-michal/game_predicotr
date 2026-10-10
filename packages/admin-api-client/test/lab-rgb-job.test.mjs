import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('browser import and job wrappers preserve the lab RGB crop snapshot', async () => {
  const gameId = '11111111-1111-4111-8111-111111111111';
  const uploadId = '22222222-2222-4222-8222-222222222222';
  const jobId = '33333333-3333-4333-8333-333333333333';
  const fingerprint = 'a'.repeat(64);
  const job = {
    id: jobId,
    gameId,
    jobType: 'import',
    status: 'created',
    inputPayload: {
      schemaVersion: 7,
      importKind: 'image_directory',
      symbolModel: {
        modelVersion: 'lab-rgb-symbol-onnx-v1',
        inputSize: 64,
        cropSize: 96,
        inferenceFingerprint: fingerprint,
      },
    },
  };
  const requests = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      const pathname = new URL(request.url).pathname;
      if (request.method === 'POST') {
        return Response.json({ created: true, job }, { status: 201 });
      }
      return Response.json(pathname.endsWith('/jobs') ? [job] : job);
    },
  });
  const body = {
    gameId,
    manifestChecksumSha256: 'b'.repeat(64),
    preflightChecksumSha256: 'c'.repeat(64),
    startMode: 'reuse_exact',
  };
  const started = await api.startReadyBrowserImageImport(uploadId, body);
  const fetched = await api.getJob(jobId);
  const listed = await api.listJobs({ gameId, jobType: 'import' });
  for (const returned of [started.data?.job, fetched.data, listed.data?.[0]]) {
    assert.equal(returned?.inputPayload.symbolModel.cropSize, 96);
    assert.equal(returned?.inputPayload.symbolModel.inputSize, 64);
    assert.equal(
      returned?.inputPayload.symbolModel.inferenceFingerprint,
      fingerprint,
    );
  }
  assert.deepEqual(await requests[0].clone().json(), body);
  assert.equal(
    new URL(requests[0].url).pathname,
    `/api/v1/admin/image-imports/browser-selections/${uploadId}/start`,
  );
});
