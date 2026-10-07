import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('controlled review-folder picker resolves an existing run without a create payload', async () => {
  let sent;
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8020',
    fetch: async (request) => {
      sent = request;
      return Response.json({ status: 'selected', runId: 'existing' });
    },
  });
  const result = await client.openSemiAutomaticImageSelectionReviewFolder();
  assert.equal(result.data.runId, 'existing');
  assert.match(sent.url, /\/review-folder$/);
  assert.equal(sent.method, 'POST');
  assert.equal(await sent.text(), '');
});

test('native output picker and create forward the chosen directory', async () => {
  const sent = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8020',
    fetch: async (request) => {
      sent.push({
        url: request.url,
        headers: request.headers,
        body: request.url.endsWith('/output-folder')
          ? null
          : await request.json(),
      });
      return Response.json({ status: 'selected', path: 'C:\\blazing' });
    },
  });
  const picked = await client.selectSemiAutomaticImageSelectionOutputFolder();
  assert.equal(picked.data.path, 'C:\\blazing');
  assert.match(sent[0].url, /\/output-folder$/);
  await client.createSemiAutomaticImageSelection({
    mode: 'v7_selection',
    selectionToken: 't'.repeat(32),
    firstSequenceNumber: 1,
    lastSequenceNumber: 9,
    v7: { outputBaseDirectory: picked.data.path },
  });
  assert.equal(sent[1].body.v7.outputBaseDirectory, 'C:\\blazing');
});

test('existing run wrapper passes the backend output directory without deriving a sibling', async () => {
  const directory = 'C:\\v7-output\\run-1';
  let requestUrl;
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8020',
    fetch: async (request) => {
      requestUrl = request.url;
      return Response.json({ id: 'run-1', outputDirectory: directory });
    },
  });
  const response = await client.getSemiAutomaticImageSelection('run-1');
  assert.match(requestUrl, /semi-automatic-image-selections\/run-1$/);
  assert.equal(response.data.outputDirectory, directory);
});

test('operator-selected capability and nullable game snapshot pass through the existing client', async () => {
  const sent = [];
  const pilot = {
    sourceGameRef: null,
    sourcePolicy: 'operator_selected_local_folder',
    bindingFingerprint: 'a'.repeat(64),
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8020',
    fetch: async (request) => {
      sent.push({
        url: request.url,
        body: request.method === 'POST' ? await request.clone().json() : null,
      });
      return Response.json(
        request.method === 'POST'
          ? { run: { v7Configuration: { pilot } }, created: true }
          : {
              v7: {
                startEnabled: true,
                sourcePolicy: 'operator_selected_local_folder',
                automaticStartEnabled: false,
              },
            },
      );
    },
  });
  const capability = await client.getSemiAutomaticImageSelectionCapabilities();
  assert.equal(
    capability.data.v7.sourcePolicy,
    'operator_selected_local_folder',
  );
  const body = {
    mode: 'v7_selection',
    selectionToken: 't'.repeat(32),
    firstSequenceNumber: 1,
    lastSequenceNumber: 18,
  };
  const created = await client.createSemiAutomaticImageSelection(body);
  assert.deepEqual(sent[1].body, body);
  assert.deepEqual(created.data.run.v7Configuration.pilot, pilot);
  assert.equal(sent[1].body.sourceGameRef, undefined);
});
test('existing acknowledgement wrapper preserves typed manual command and operation identity', async () => {
  const sent = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8020',
    fetch: async (request) => {
      sent.push({ url: request.url, body: await request.clone().json() });
      return Response.json({
        status: 'proposed',
        outputOperation: { state: 'reserved' },
        outputChecksumSha256: null,
      });
    },
  });
  const body = {
    workflowMode: 'v7_selection',
    operationId: '11111111-1111-4111-8111-111111111111',
    expectedRevision: 3,
    sourceIndex: 2,
    expectedSourceChecksumSha256: 'a'.repeat(64),
    kind: 'manual_no_ocr',
    confirmedRange: { start: 2, end: 8 },
    operatorConfirmedRange: true,
    operatorConfirmedIncompletePage: true,
    correctionReason: 'occlusion',
  };
  await client.acknowledgeSemiAutomaticImageSelectionOutput('run-1', 0, body);
  assert.match(
    sent[0].url,
    /semi-automatic-image-selections\/run-1\/ranges\/0\/output-acknowledgements$/,
  );
  assert.deepEqual(sent[0].body, body);
});

test('historical V7 command without reason retains its body', async () => {
  let sent;
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8020',
    fetch: async (request) => {
      sent = await request.clone().json();
      return Response.json({ outputOperation: { state: 'reserved' } });
    },
  });
  const body = {
    workflowMode: 'v7_selection',
    operationId: '11111111-1111-4111-8111-111111111111',
    expectedRevision: 0,
    sourceIndex: 0,
    expectedSourceChecksumSha256: 'a'.repeat(64),
    kind: 'manual_no_ocr',
    confirmedRange: { start: 1, end: 9 },
    operatorConfirmedRange: true,
  };
  await client.acknowledgeSemiAutomaticImageSelectionOutput('run-1', 0, body);
  assert.deepEqual(sent, body);
  assert.equal(Object.hasOwn(sent, 'correctionReason'), false);
});
