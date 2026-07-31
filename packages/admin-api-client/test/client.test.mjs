import assert from 'node:assert/strict';
import test from 'node:test';

import { createAdminApiClient } from '../src/index.ts';

test('generated client calls the typed health operation', async () => {
  const requests = [];
  const mockFetch = async (request) => {
    requests.push(request);
    return new Response(
      JSON.stringify({
        status: 'ok',
        version: '0.1.0',
      }),
      {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      },
    );
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const result = await client.getHealth();

  assert.deepEqual(result.data, { status: 'ok', version: '0.1.0' });
  assert.equal(result.error, undefined);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, 'http://127.0.0.1:8000/api/v1/health');
});

test('generated client selects a folder and creates its image import', async () => {
  const requests = [];
  const gameId = '11111111-1111-4111-8111-111111111111';
  const mockFetch = async (request) => {
    requests.push(request);
    const path = new URL(request.url).pathname;
    if (path.endsWith('/folder-selection')) {
      return Response.json({
        expiresAt: '2026-07-31T12:15:00Z',
        path: 'C:\\photos',
        selectionToken: 'approved-token',
        status: 'selected',
        supportedFileCount: 2,
      });
    }
    return Response.json(
      {
        job: {
          id: '22222222-2222-4222-8222-222222222222',
          jobType: 'import',
          gameId,
          status: 'created',
          inputPayload: {
            schemaVersion: 1,
            importKind: 'image_directory',
            sourceSelectionId: '33333333-3333-4333-8333-333333333333',
            sourceDirectory: 'C:\\photos',
            sourceDisplayName: 'photos',
            pipelineFingerprint: 'a'.repeat(64),
          },
          progress: {
            current: 0,
            total: null,
            stage: null,
            succeeded: 0,
            failed: 0,
            review: 0,
          },
          error: null,
          workerVersion: null,
          attemptCount: 0,
          heartbeatAt: null,
          leaseExpiresAt: null,
          createdAt: '2026-07-31T12:00:00Z',
          updatedAt: '2026-07-31T12:00:00Z',
          startedAt: null,
          finishedAt: null,
          cancelRequestedAt: null,
        },
      },
      { status: 201 },
    );
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  await client.selectLocalImageFolder();
  await client.createImageFolderImport({
    gameId,
    selectionToken: 'approved-token',
  });

  assert.deepEqual(
    requests.map((request) => [request.method, new URL(request.url).pathname]),
    [
      ['POST', '/api/v1/admin/image-imports/folder-selection'],
      ['POST', '/api/v1/admin/image-imports'],
    ],
  );
  assert.equal(
    requests[0].headers.get('X-Admin-Target'),
    'image-folder:select',
  );
  assert.equal(
    requests[1].headers.get('X-Admin-Target'),
    `image-import:${gameId}`,
  );
});

test('generated client reads completeness and controls a sequence source override', async () => {
  const requests = [];
  const gameId = '11111111-1111-4111-8111-111111111111';
  const reviewItemId = '22222222-2222-4222-8222-222222222222';
  const mockFetch = async (request) => {
    requests.push(request);
    const path = new URL(request.url).pathname;
    if (path.includes('dataset-completeness')) {
      return Response.json({
        acceptedBoardCount: 2,
        completionPercentage: 1,
        duplicateSequenceCount: 0,
        expectedLayoutCount: 200,
        gameId,
        manualOverrideCount: 0,
        missingSequenceCount: 198,
        missingSequenceNumbers: [3, 4],
        missingSequenceNumbersTruncated: true,
        outOfRangeSequenceCount: 0,
        uniqueSequenceCount: 2,
      });
    }
    return Response.json({
      candidates: [],
      gameId,
      manualOverrideReviewItemId: path.endsWith('/override')
        ? reviewItemId
        : null,
      overrideRevision: path.endsWith('/override') ? 1 : 0,
      sequenceNumber: 7,
    });
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  await client.getImageDatasetCompleteness(gameId);
  await client.getImageSequenceSourceSelection(gameId, 7);
  await client.selectImageSequenceSource(gameId, 7, {
    reviewItemId,
    selectedBy: 'local-owner',
  });

  assert.deepEqual(
    requests.map((request) => [request.method, new URL(request.url).pathname]),
    [
      [
        'GET',
        `/api/v1/admin/image-review-items/dataset-completeness/${gameId}`,
      ],
      [
        'GET',
        `/api/v1/admin/image-review-items/sequence-sources/${gameId}/7`,
      ],
      [
        'POST',
        `/api/v1/admin/image-review-items/sequence-sources/${gameId}/7/override`,
      ],
    ],
  );
  assert.equal(
    requests[2].headers.get('X-Admin-Target'),
    `image-sequence-source:${gameId}:7`,
  );
});

test('generated client controls only the explicit Reviewer ingress target', async () => {
  const requests = [];
  const status = {
    publicOrigin: 'https://safe-name.trycloudflare.com',
    reviewerReady: true,
    startedAt: '2026-07-31T10:00:00Z',
    state: 'running',
    target: 'http://127.0.0.1:3001',
  };
  const mockFetch = async (request) => {
    requests.push(request);
    return Response.json(
      request.url.endsWith('/stop')
        ? {
            ...status,
            publicOrigin: null,
            startedAt: null,
            state: 'stopped',
          }
        : status,
    );
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });
  const command = { confirmed: true, target: 'remote-reviewer' };

  await client.getReviewerIngressStatus();
  await client.startReviewerIngress(command);
  await client.stopReviewerIngress(command);

  assert.deepEqual(
    requests.map((request) => [request.method, new URL(request.url).pathname]),
    [
      ['GET', '/api/v1/admin/reviewer-ingress'],
      ['POST', '/api/v1/admin/reviewer-ingress/start'],
      ['POST', '/api/v1/admin/reviewer-ingress/stop'],
    ],
  );
  assert.deepEqual(await requests[1].clone().json(), command);
  assert.deepEqual(await requests[2].clone().json(), command);
  for (const request of requests.slice(1)) {
    assert.equal(request.headers.get('X-Admin-Intent'), 'local-owner');
    assert.equal(request.headers.get('X-Admin-Confirmation'), 'confirmed');
    assert.equal(request.headers.get('X-Admin-Target'), 'remote-reviewer');
  }
});

test('generated client sends typed game and symbol requests', async () => {
  const requests = [];
  const gameId = '11111111-1111-4111-8111-111111111111';
  const symbolId = '22222222-2222-4222-8222-222222222222';
  const mockFetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname.endsWith('/games')) {
      return Response.json(
        {
          id: gameId,
          code: 'game-1',
          name: 'Game 1',
          status: 'draft',
          createdAt: '2026-07-26T10:00:00Z',
          updatedAt: '2026-07-26T10:00:00Z',
        },
        { status: 201 },
      );
    }
    if (request.method === 'POST' && url.pathname.endsWith('/symbols')) {
      return Response.json(
        {
          id: symbolId,
          gameId,
          mobileCode: 1,
          code: 'S1',
          name: 'Symbol 1',
          imagePath: null,
          isWildcard: false,
          displayOrder: 0,
          status: 'active',
        },
        { status: 201 },
      );
    }
    throw new Error(`Unexpected request: ${request.method} ${url.pathname}`);
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const game = await client.createGame({ code: 'game-1', name: 'Game 1' });
  const symbol = await client.createSymbol(gameId, {
    mobileCode: 1,
    code: 'S1',
    name: 'Symbol 1',
    displayOrder: 0,
  });

  assert.equal(game.data?.id, gameId);
  assert.equal(symbol.data?.id, symbolId);
  assert.equal(requests.length, 2);
  assert.deepEqual(await requests[0].clone().json(), {
    code: 'game-1',
    name: 'Game 1',
  });
  assert.equal(
    new URL(requests[1].url).pathname,
    `/api/v1/admin/games/${gameId}/symbols`,
  );
});

test('generated client sends typed job, filters, details, cancel and retry requests', async () => {
  const requests = [];
  const gameId = '11111111-1111-4111-8111-111111111111';
  const datasetVersionId = '66666666-6666-4666-8666-666666666666';
  const jobId = '77777777-7777-4777-8777-777777777777';
  const responseBody = {
    id: jobId,
    jobType: 'validate',
    gameId,
    status: 'created',
    inputPayload: { schemaVersion: 1, datasetVersionId },
    progress: {
      current: 0,
      total: null,
      stage: null,
      succeeded: 0,
      failed: 0,
      review: 0,
    },
    error: null,
    workerVersion: null,
    attemptCount: 0,
    heartbeatAt: null,
    leaseExpiresAt: null,
    createdAt: '2026-07-27T10:00:00Z',
    updatedAt: '2026-07-27T10:00:00Z',
    startedAt: null,
    finishedAt: null,
    cancelRequestedAt: null,
  };
  const mockFetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);
    if (request.method === 'GET' && url.pathname.endsWith('/jobs')) {
      return Response.json([responseBody]);
    }
    return Response.json(responseBody, {
      status:
        request.method === 'POST' && url.pathname.endsWith('/jobs') ? 201 : 200,
    });
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const created = await client.createJob({
    jobType: 'validate',
    gameId,
    inputPayload: {
      schemaVersion: 1,
      datasetVersionId,
    },
  });
  await client.listJobs({
    status: 'created',
    jobType: 'validate',
    gameId,
    limit: 25,
  });
  await client.getJob(jobId);
  await client.cancelJob(jobId);
  await client.retryJob(jobId);

  assert.equal(created.data?.id, jobId);
  assert.deepEqual(await requests[0].clone().json(), {
    jobType: 'validate',
    gameId,
    inputPayload: {
      schemaVersion: 1,
      datasetVersionId,
    },
  });
  assert.equal(
    new URL(requests[1].url).search,
    `?status=created&job_type=validate&game_id=${gameId}&limit=25`,
  );
  assert.equal(
    new URL(requests[2].url).pathname,
    `/api/v1/admin/jobs/${jobId}`,
  );
  assert.equal(
    new URL(requests[3].url).pathname,
    `/api/v1/admin/jobs/${jobId}/cancel`,
  );
  assert.equal(
    new URL(requests[4].url).pathname,
    `/api/v1/admin/jobs/${jobId}/retry`,
  );
});

test('generated client reads image operations and retries one exact failed stage', async () => {
  const requests = [];
  const jobId = '77777777-7777-4777-8777-777777777777';
  const fileExecutionKey = 'a'.repeat(64);
  const responseBody = {
    jobId,
    pipelineFingerprint: 'b'.repeat(64),
    total: 1,
    current: 1,
    succeeded: 0,
    failed: 1,
    review: 0,
    waiting: 0,
    elapsedSeconds: 10,
    filesPerMinute: 6,
    stageCounts: [{ stage: 'normalization', count: 1 }],
    files: [],
    fileLimit: 25,
    hasMoreFiles: false,
  };
  const mockFetch = async (request) => {
    requests.push(request);
    return Response.json(responseBody);
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  await client.getImageJobOperations(jobId, 25);
  await client.retryImageJobFile(
    jobId,
    fileExecutionKey,
    { expectedStage: 'normalization' },
    25,
  );

  assert.equal(
    new URL(requests[0].url).pathname,
    `/api/v1/admin/image-jobs/${jobId}/operations`,
  );
  assert.equal(new URL(requests[0].url).search, '?file_limit=25');
  assert.equal(
    new URL(requests[1].url).pathname,
    `/api/v1/admin/image-jobs/${jobId}/files/${fileExecutionKey}/retry`,
  );
  assert.equal(new URL(requests[1].url).search, '?file_limit=25');
  assert.deepEqual(await requests[1].clone().json(), {
    expectedStage: 'normalization',
  });
});

test('generated client inventories storage and manages immutable diagnostic exports', async () => {
  const requests = [];
  const jobId = '88888888-8888-4888-8888-888888888888';
  const checksum = 'c'.repeat(64);
  const diagnosticExport = {
    checksumSha256: checksum,
    errorCount: 2,
    exportedErrorCount: 2,
    jobId,
    relativePath: `data/exports/image-jobs/${jobId}/${checksum}/diagnostics.json`,
    sizeBytes: 128,
    sourceUpdatedAt: '2026-07-29T12:00:00Z',
    truncated: false,
  };
  const mockFetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);
    if (url.pathname === '/api/v1/admin/image-storage') {
      return Response.json({
        automaticDeletion: false,
        namespaces: [],
        rootName: 'data',
        totalFileCount: 0,
        totalSizeBytes: 0,
      });
    }
    if (url.pathname.endsWith('/download')) {
      return new Response('{"schema":"image-job-diagnostics-v1"}\n', {
        headers: { 'content-type': 'application/octet-stream' },
      });
    }
    return Response.json(
      request.method === 'POST'
        ? { created: true, export: diagnosticExport }
        : [diagnosticExport],
      { status: request.method === 'POST' ? 201 : 200 },
    );
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const inventory = await client.getImageStorageInventory();
  const created = await client.createImageDiagnosticExport(jobId);
  const listed = await client.listImageDiagnosticExports(jobId);
  const downloaded = await client.downloadImageDiagnosticExport(
    jobId,
    checksum,
  );

  assert.equal(inventory.data?.automaticDeletion, false);
  assert.equal(created.data?.export.checksumSha256, checksum);
  assert.equal(listed.data?.[0]?.jobId, jobId);
  assert.equal(downloaded.data instanceof Blob, true);
  assert.deepEqual(
    requests.map((request) => ({
      method: request.method,
      path: new URL(request.url).pathname,
    })),
    [
      { method: 'GET', path: '/api/v1/admin/image-storage' },
      {
        method: 'POST',
        path: `/api/v1/admin/image-jobs/${jobId}/diagnostic-exports`,
      },
      {
        method: 'GET',
        path: `/api/v1/admin/image-jobs/${jobId}/diagnostic-exports`,
      },
      {
        method: 'GET',
        path: `/api/v1/admin/image-jobs/${jobId}/diagnostic-exports/${checksum}/download`,
      },
    ],
  );
});

test('generated client sends only the trusted layout import source request', async () => {
  const requests = [];
  const gameId = '11111111-1111-4111-8111-111111111111';
  const jobId = '77777777-7777-4777-8777-777777777777';
  const mockFetch = async (request) => {
    requests.push(request);
    return Response.json(
      {
        id: jobId,
        jobType: 'import',
        gameId,
        status: 'created',
        inputPayload: {
          schemaVersion: 1,
          importKind: 'layout_file',
          sourcePath: 'game-1/layouts.csv',
          sourceChecksum: 'a'.repeat(64),
          sourceSizeBytes: 123,
          fileFormat: 'csv',
          contractVersion: 1,
        },
        progress: {
          current: 0,
          total: null,
          stage: null,
          succeeded: 0,
          failed: 0,
          review: 0,
        },
        error: null,
        workerVersion: null,
        attemptCount: 0,
        heartbeatAt: null,
        leaseExpiresAt: null,
        createdAt: '2026-07-27T10:00:00Z',
        updatedAt: '2026-07-27T10:00:00Z',
        startedAt: null,
        finishedAt: null,
        cancelRequestedAt: null,
      },
      { status: 201 },
    );
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const result = await client.createJob({
    jobType: 'import',
    gameId,
    inputPayload: {
      schemaVersion: 1,
      sourcePath: 'game-1/layouts.csv',
      contractVersion: 1,
    },
  });

  assert.equal(result.data?.inputPayload.sourceChecksum, 'a'.repeat(64));
  assert.deepEqual(await requests[0].clone().json(), {
    jobType: 'import',
    gameId,
    inputPayload: {
      schemaVersion: 1,
      sourcePath: 'game-1/layouts.csv',
      contractVersion: 1,
    },
  });
});

test('generated client sends a rules-bound layout import validation request', async () => {
  const requests = [];
  const gameId = '11111111-1111-4111-8111-111111111111';
  const importJobId = '22222222-2222-4222-8222-222222222222';
  const rulesVersionId = '33333333-3333-4333-8333-333333333333';
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return Response.json(
        {
          id: '44444444-4444-4444-8444-444444444444',
          jobType: 'validate',
          gameId,
          status: 'created',
          inputPayload: {
            schemaVersion: 1,
            validationKind: 'layout_import',
            importJobId,
            rulesVersionId,
          },
          progress: {
            current: 0,
            total: null,
            stage: null,
            succeeded: 0,
            failed: 0,
            review: 0,
          },
          error: null,
          workerVersion: null,
          attemptCount: 0,
          heartbeatAt: null,
          leaseExpiresAt: null,
          createdAt: '2026-07-27T10:00:00Z',
          updatedAt: '2026-07-27T10:00:00Z',
          startedAt: null,
          finishedAt: null,
          cancelRequestedAt: null,
        },
        { status: 201 },
      );
    },
  });

  await client.createJob({
    jobType: 'validate',
    gameId,
    inputPayload: {
      schemaVersion: 1,
      validationKind: 'layout_import',
      importJobId,
      rulesVersionId,
    },
  });

  assert.deepEqual(await requests[0].clone().json(), {
    jobType: 'validate',
    gameId,
    inputPayload: {
      schemaVersion: 1,
      validationKind: 'layout_import',
      importJobId,
      rulesVersionId,
    },
  });
});

test('generated client sends server-versioned rules draft requests', async () => {
  const requests = [];
  const gameId = '11111111-1111-4111-8111-111111111111';
  const rulesVersionId = '33333333-3333-4333-8333-333333333333';
  const responseBody = {
    columns: 5,
    createdAt: '2026-07-27T10:00:00Z',
    gameId,
    id: rulesVersionId,
    publishedAt: null,
    rows: 3,
    spinCost: 10,
    status: 'draft',
    version: 1,
  };
  const mockFetch = async (request) => {
    requests.push(request);
    return Response.json(responseBody, {
      status: request.method === 'POST' ? 201 : 200,
    });
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const created = await client.createRulesVersion(gameId, {
    columns: 5,
    rows: 3,
    spinCost: 10,
  });
  const updated = await client.updateRulesVersion(rulesVersionId, {
    spinCost: 20,
  });

  assert.equal(created.data?.version, 1);
  assert.equal(updated.data?.id, rulesVersionId);
  assert.equal(
    new URL(requests[0].url).pathname,
    `/api/v1/admin/games/${gameId}/rules-versions`,
  );
  assert.equal(
    new URL(requests[1].url).pathname,
    `/api/v1/admin/rules-versions/${rulesVersionId}`,
  );
  assert.deepEqual(await requests[0].clone().json(), {
    columns: 5,
    rows: 3,
    spinCost: 10,
  });
});

test('generated client sends zero-based payline CRUD requests', async () => {
  const requests = [];
  const rulesVersionId = '33333333-3333-4333-8333-333333333333';
  const paylineId = '44444444-4444-4444-8444-444444444444';
  const responseBody = {
    code: 'line-v',
    displayOrder: 10,
    id: paylineId,
    isActive: true,
    name: 'V',
    rowPath: [0, 1, 2, 1, 0],
    rulesVersionId,
  };
  const mockFetch = async (request) => {
    requests.push(request);
    if (request.method === 'DELETE') {
      return new Response(null, { status: 204 });
    }
    return Response.json(responseBody, {
      status: request.method === 'POST' ? 201 : 200,
    });
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const created = await client.createPayline(rulesVersionId, {
    code: 'line-v',
    displayOrder: 10,
    name: 'V',
    rowPath: [0, 1, 2, 1, 0],
  });
  await client.updatePayline(rulesVersionId, paylineId, {
    displayOrder: 5,
  });
  await client.archivePayline(rulesVersionId, paylineId);

  assert.equal(created.data?.id, paylineId);
  assert.equal(
    new URL(requests[0].url).pathname,
    `/api/v1/admin/rules-versions/${rulesVersionId}/paylines`,
  );
  assert.equal(
    new URL(requests[1].url).pathname,
    `/api/v1/admin/rules-versions/${rulesVersionId}/paylines/${paylineId}`,
  );
  assert.equal(requests[2].method, 'DELETE');
  assert.deepEqual(await requests[0].clone().json(), {
    code: 'line-v',
    displayOrder: 10,
    name: 'V',
    rowPath: [0, 1, 2, 1, 0],
  });
});

test('generated client sends symbol minimum and payout rule requests', async () => {
  const requests = [];
  const rulesVersionId = '33333333-3333-4333-8333-333333333333';
  const symbolId = '22222222-2222-4222-8222-222222222222';
  const payoutRuleId = '55555555-5555-4555-8555-555555555555';
  const mockFetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);
    if (request.method === 'DELETE') return new Response(null, { status: 204 });
    if (url.pathname.endsWith(`/symbols/${symbolId}`)) {
      return Response.json({
        isActive: true,
        minimumMatchLength: 2,
        rulesVersionId,
        symbolId,
      });
    }
    return Response.json(
      {
        id: payoutRuleId,
        isActive: true,
        matchLength: 2,
        payoutCredits: 10,
        rulesVersionId,
        symbolId,
      },
      { status: request.method === 'POST' ? 201 : 200 },
    );
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  await client.updateRulesVersionSymbol(rulesVersionId, symbolId, {
    minimumMatchLength: 2,
  });
  const created = await client.createPayoutRule(rulesVersionId, {
    matchLength: 2,
    payoutCredits: 10,
    symbolId,
  });
  await client.updatePayoutRule(rulesVersionId, payoutRuleId, {
    payoutCredits: 20,
  });
  await client.archivePayoutRule(rulesVersionId, payoutRuleId);

  assert.equal(created.data?.id, payoutRuleId);
  assert.equal(
    new URL(requests[0].url).pathname,
    `/api/v1/admin/rules-versions/${rulesVersionId}/symbols/${symbolId}`,
  );
  assert.equal(
    new URL(requests[1].url).pathname,
    `/api/v1/admin/rules-versions/${rulesVersionId}/payout-rules`,
  );
  assert.deepEqual(await requests[0].clone().json(), {
    minimumMatchLength: 2,
  });
  assert.equal(requests[3].method, 'DELETE');
});

test('generated client sends rules publication workflow requests', async () => {
  const requests = [];
  const rulesVersionId = '33333333-3333-4333-8333-333333333333';
  const rulesVersion = {
    columns: 5,
    createdAt: '2026-07-27T10:00:00Z',
    gameId: '11111111-1111-4111-8111-111111111111',
    id: rulesVersionId,
    publishedAt: '2026-07-27T11:00:00Z',
    rows: 3,
    spinCost: 10,
    status: 'published',
    version: 1,
  };
  const mockFetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);
    if (request.method === 'DELETE') {
      return new Response(null, { status: 204 });
    }
    if (url.pathname.endsWith('/publication-readiness')) {
      return Response.json({
        issues: [],
        ready: true,
        rulesVersionId,
      });
    }
    return Response.json(rulesVersion);
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const readiness = await client.getRulesPublicationReadiness(rulesVersionId);
  const published = await client.publishRulesVersion(rulesVersionId);
  await client.archiveRulesVersion(rulesVersionId);

  assert.equal(readiness.data?.ready, true);
  assert.equal(published.data?.status, 'published');
  assert.deepEqual(
    requests.map((request) => [request.method, new URL(request.url).pathname]),
    [
      [
        'GET',
        `/api/v1/admin/rules-versions/${rulesVersionId}/publication-readiness`,
      ],
      ['POST', `/api/v1/admin/rules-versions/${rulesVersionId}/publish`],
      ['DELETE', `/api/v1/admin/rules-versions/${rulesVersionId}`],
    ],
  );
});

test('generated client sends bounded mock dataset staging requests', async () => {
  const requests = [];
  const gameId = '11111111-1111-4111-8111-111111111111';
  const rulesVersionId = '33333333-3333-4333-8333-333333333333';
  const datasetVersionId = '66666666-6666-4666-8666-666666666666';
  const responseBody = {
    columns: 5,
    createdAt: '2026-07-27T10:00:00Z',
    gameId,
    generationSeed: 71401,
    generatorVersion: 'mock-v1',
    id: datasetVersionId,
    layoutCount: 1000,
    publishedAt: null,
    rows: 3,
    signatureCellWidth: 2,
    sourceJobId: null,
    status: 'staging',
    version: 1,
  };
  const validationBody = {
    actualLayoutCount: 1000,
    checks: [
      {
        code: 'DUPLICATE_SIGNATURE',
        issueCount: 6,
        message: 'Duplicate layout signatures are allowed and were found.',
        mobileCodes: [],
        sequenceNumbers: [],
        status: 'warning',
        truncated: false,
      },
    ],
    datasetVersion: 1,
    datasetVersionId,
    declaredLayoutCount: 1000,
    duplicateSignatureAffectedLayoutCount: 12,
    duplicateSignatureExcessLayoutCount: 6,
    duplicateSignatureGroupCount: 6,
    duplicateSignatures: [],
    duplicateSignaturesTruncated: false,
    maxSequenceNumber: 1000,
    minSequenceNumber: 1,
    readyForPublication: true,
  };
  const layoutsBody = {
    columns: 5,
    datasetVersion: 1,
    datasetVersionId,
    items: [
      {
        cells: Array(15).fill(1),
        sequenceNumber: 13,
        signature: '01'.repeat(15),
        sourceBoardId: null,
      },
    ],
    nextAfterSequenceNumber: 13,
    rows: 3,
  };
  const mockFetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);
    if (request.method === 'DELETE') {
      return new Response(null, { status: 204 });
    }
    if (url.pathname.endsWith('/validation-report')) {
      return Response.json(validationBody);
    }
    if (url.pathname.endsWith('/layouts')) {
      return Response.json(layoutsBody);
    }
    return Response.json(
      request.method === 'GET' && url.pathname.endsWith('/dataset-versions')
        ? [responseBody]
        : url.pathname.endsWith('/publish')
          ? {
              ...responseBody,
              publishedAt: '2026-07-27T12:00:00Z',
              status: 'published',
            }
          : responseBody,
      { status: request.method === 'POST' ? 201 : 200 },
    );
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const created = await client.generateMockDataset(gameId, {
    rulesVersionId,
    seed: 71401,
  });
  const listed = await client.listDatasetVersions(gameId);
  const loaded = await client.getDatasetVersion(datasetVersionId);
  const validation = await client.getDatasetValidationReport(datasetVersionId);
  const layouts = await client.listDatasetLayouts(datasetVersionId, 12, 1);
  const published = await client.publishDatasetVersion(datasetVersionId);
  await client.archiveDatasetVersion(datasetVersionId);

  assert.equal(created.data?.layoutCount, 1000);
  assert.equal(listed.data?.length, 1);
  assert.equal(loaded.data?.id, datasetVersionId);
  assert.equal(validation.data?.duplicateSignatureGroupCount, 6);
  assert.equal(layouts.data?.items[0]?.sequenceNumber, 13);
  assert.equal(published.data?.status, 'published');
  assert.equal(new URL(requests[4].url).searchParams.get('limit'), '1');
  assert.equal(
    new URL(requests[4].url).searchParams.get('after_sequence_number'),
    '12',
  );
  assert.deepEqual(await requests[0].clone().json(), {
    rulesVersionId,
    seed: 71401,
  });
  assert.deepEqual(
    requests.map((request) => new URL(request.url).pathname),
    [
      `/api/v1/admin/games/${gameId}/dataset-versions/mock`,
      `/api/v1/admin/games/${gameId}/dataset-versions`,
      `/api/v1/admin/dataset-versions/${datasetVersionId}`,
      `/api/v1/admin/dataset-versions/${datasetVersionId}/validation-report`,
      `/api/v1/admin/dataset-versions/${datasetVersionId}/layouts`,
      `/api/v1/admin/dataset-versions/${datasetVersionId}/publish`,
      `/api/v1/admin/dataset-versions/${datasetVersionId}`,
    ],
  );
});

test('generated client sends layout import report and row filters', async () => {
  const requests = [];
  const validationJobId = '11111111-1111-4111-8111-111111111111';
  const mockFetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);
    if (url.pathname.endsWith('/rows')) {
      return Response.json({
        columns: 5,
        importJobId: '22222222-2222-4222-8222-222222222222',
        items: [
          {
            cells: [1, 99],
            errorCode: 'import_symbol_not_in_rules',
            errorMessage: 'Foreign symbol.',
            lineNumber: 5,
            sequenceNumber: 3,
            signature: null,
          },
        ],
        nextAfterLineNumber: null,
        rows: 3,
        rulesVersionId: '33333333-3333-4333-8333-333333333333',
        validationJobId,
      });
    }
    if (url.pathname.endsWith('/staging')) {
      return Response.json({
        deletedNormalizedRowCount: 6,
        deletedRawRowCount: 6,
        importJobId: '22222222-2222-4222-8222-222222222222',
        validationJobId,
      });
    }
    if (url.pathname.endsWith('/publish')) {
      return Response.json({
        columns: 5,
        createdAt: '2026-07-28T12:00:00Z',
        gameId: '44444444-4444-4444-8444-444444444444',
        generationSeed: 0,
        generatorVersion: 'layout-import-v1',
        id: '55555555-5555-4555-8555-555555555555',
        layoutCount: 6,
        publishedAt: '2026-07-28T12:00:00Z',
        rows: 3,
        signatureCellWidth: 1,
        sourceJobId: validationJobId,
        status: 'published',
        version: 1,
      });
    }
    return Response.json({
      actualRowCount: 6,
      checks: [],
      columns: 5,
      duplicateSequenceAffectedRowCount: 0,
      duplicateSequenceExcessRowCount: 0,
      duplicateSequenceGroupCount: 0,
      duplicateSequences: [],
      duplicateSequencesTruncated: false,
      duplicateSignatureAffectedRowCount: 0,
      duplicateSignatureExcessRowCount: 0,
      duplicateSignatureGroupCount: 0,
      duplicateSignatures: [],
      duplicateSignaturesTruncated: false,
      errorCodeCounts: [],
      expectedRowCount: 6,
      importJobId: '22222222-2222-4222-8222-222222222222',
      invalidRowCount: 0,
      maxSequenceNumber: 6,
      minSequenceNumber: 1,
      missingSequenceCount: 0,
      missingSequenceNumbers: [],
      missingSequenceNumbersTruncated: false,
      readyForPublication: true,
      rows: 3,
      rulesVersionId: '33333333-3333-4333-8333-333333333333',
      uniqueSequenceCount: 6,
      validRowCount: 6,
      validationJobId,
    });
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const report = await client.getLayoutImportIntegrityReport(validationJobId);
  const rows = await client.listLayoutImportNormalizedRows(validationJobId, {
    afterLineNumber: 4,
    errorCode: 'import_symbol_not_in_rules',
    limit: 1,
    status: 'invalid',
  });
  const published = await client.publishLayoutImportDataset(validationJobId);
  const rejection = await client.rejectLayoutImportStaging(validationJobId);

  assert.equal(report.data?.readyForPublication, true);
  assert.equal(rows.data?.items[0]?.lineNumber, 5);
  assert.equal(published.data?.sourceJobId, validationJobId);
  assert.equal(rejection.data?.deletedRawRowCount, 6);
  assert.deepEqual(
    requests.map((request) => new URL(request.url).pathname),
    [
      `/api/v1/admin/layout-import-validations/${validationJobId}/integrity-report`,
      `/api/v1/admin/layout-import-validations/${validationJobId}/rows`,
      `/api/v1/admin/layout-import-validations/${validationJobId}/publish`,
      `/api/v1/admin/layout-import-validations/${validationJobId}/staging`,
    ],
  );
  const query = new URL(requests[1].url).searchParams;
  assert.equal(query.get('after_line_number'), '4');
  assert.equal(query.get('limit'), '1');
  assert.equal(query.get('status'), 'invalid');
  assert.equal(query.get('error_code'), 'import_symbol_not_in_rules');
});

test('generated client sends immutable mobile release requests', async () => {
  const requests = [];
  const releaseId = '11111111-1111-4111-8111-111111111111';
  const gameId = '22222222-2222-4222-8222-222222222222';
  const datasetVersionId = '33333333-3333-4333-8333-333333333333';
  const rulesVersionId = '44444444-4444-4444-8444-444444444444';
  const responseBody = {
    algorithmVersion: 'payout-v2',
    apk: null,
    buildJobId: null,
    createdAt: '2026-07-27T12:00:00Z',
    games: [
      {
        columns: 5,
        datasetVersion: 1,
        datasetVersionId,
        gameCode: 'game-1',
        gameId,
        layoutCount: 1000,
        rows: 3,
        rulesVersion: 1,
        rulesVersionId,
      },
    ],
    id: releaseId,
    readyAt: null,
    snapshot: null,
    snapshotSchemaVersion: 2,
    status: 'draft',
    version: 'm3.4.1',
  };
  const mockFetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);
    if (url.pathname.endsWith('/apk')) {
      return new Response(new Blob(['verified-apk']), {
        headers: {
          'content-type': 'application/vnd.android.package-archive',
        },
        status: 200,
      });
    }
    return Response.json(
      url.pathname.endsWith('/build')
        ? { jobId: '00000000-0000-0000-0000-000000000104', status: 'created' }
        : request.method === 'GET' &&
            url.pathname === '/api/v1/admin/mobile-releases'
          ? [responseBody]
          : responseBody,
      { status: request.method === 'POST' ? 201 : 200 },
    );
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const created = await client.createMobileRelease({
    games: [{ datasetVersionId, gameId, rulesVersionId }],
    version: 'm3.4.1',
  });
  const listed = await client.listMobileReleases();
  const loaded = await client.getMobileRelease(releaseId);
  const downloaded = await client.downloadMobileReleaseApk(releaseId);
  const build = await client.buildMobileRelease(releaseId);

  assert.equal(created.data?.algorithmVersion, 'payout-v2');
  assert.equal(listed.data?.[0]?.id, releaseId);
  assert.equal(loaded.data?.games[0]?.layoutCount, 1000);
  assert.equal(downloaded.data instanceof Blob, true);
  assert.equal(build.data?.status, 'created');
  assert.deepEqual(await requests[0].clone().json(), {
    games: [{ datasetVersionId, gameId, rulesVersionId }],
    version: 'm3.4.1',
  });
  assert.deepEqual(
    requests.map((request) => new URL(request.url).pathname),
    [
      '/api/v1/admin/mobile-releases',
      '/api/v1/admin/mobile-releases',
      `/api/v1/admin/mobile-releases/${releaseId}`,
      `/api/v1/admin/mobile-releases/${releaseId}/apk`,
      `/api/v1/admin/mobile-releases/${releaseId}/build`,
    ],
  );
});

test('generated client previews and persists one scope-bound geometry revision', async () => {
  const requests = [];
  const reviewItemId = '11111111-1111-4111-8111-111111111111';
  const context = {
    gameId: '22222222-2222-4222-8222-222222222222',
    importJobId: '33333333-3333-4333-8333-333333333333',
  };
  const previewCommand = {
    corners: [
      { x: 10, y: 10 },
      { x: 510, y: 10 },
      { x: 510, y: 310 },
      { x: 10, y: 310 },
    ],
    expectedGeometryRevision: 0,
    expectedResolutionRevision: 2,
  };
  const mockFetch = async (request) => {
    requests.push(request);
    if (new URL(request.url).pathname.endsWith('/geometry-preview')) {
      return new Response(new Blob(['png']), {
        headers: { 'content-type': 'image/png' },
        status: 200,
      });
    }
    return Response.json(
      { created: true, geometryRevision: {}, item: {} },
      { status: 200 },
    );
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const preview = await client.previewOperationalImageReviewGeometry(
    reviewItemId,
    context,
    previewCommand,
  );
  const saved = await client.createOperationalImageReviewGeometryRevision(
    reviewItemId,
    context,
    {
      ...previewCommand,
      correctedBy: 'local-admin',
      idempotencyKey: '44444444-4444-4444-8444-444444444444',
    },
  );

  assert.equal(preview.data instanceof Blob, true);
  assert.equal(saved.data?.created, true);
  assert.deepEqual(
    requests.map((request) => new URL(request.url).pathname),
    [
      `/api/v1/admin/image-review-items/${reviewItemId}/geometry-preview`,
      `/api/v1/admin/image-review-items/${reviewItemId}/geometry-revisions`,
    ],
  );
  assert.equal(
    new URL(requests[0].url).searchParams.get('gameId'),
    context.gameId,
  );
  assert.deepEqual(await requests[0].clone().json(), previewCommand);
});

test('generated client lists and explicitly freezes verified cohorts in one context', async () => {
  const requests = [];
  const context = {
    gameId: '22222222-2222-4222-8222-222222222222',
    importJobId: '33333333-3333-4333-8333-333333333333',
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return Response.json(
        request.method === 'POST'
          ? { created: true, export: { version: 1 } }
          : [],
        { status: 200 },
      );
    },
  });

  await client.listVerifiedImageReviewCohorts({ ...context, limit: 20 });
  await client.freezeVerifiedImageReviewCohort(context, {
    createdBy: 'local-admin',
  });

  assert.deepEqual(
    requests.map((request) => new URL(request.url).pathname),
    [
      '/api/v1/admin/image-review-cohort-exports',
      '/api/v1/admin/image-review-cohort-exports',
    ],
  );
  assert.equal(requests[0].method, 'GET');
  assert.equal(requests[1].method, 'POST');
  assert.equal(
    new URL(requests[0].url).searchParams.get('importJobId'),
    context.importJobId,
  );
});

test('operational review client forwards resume-at-first-pending in the all queue', async () => {
  const requests = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return Response.json({
        counts: {
          accepted: 0,
          completed: 0,
          corrected: 0,
          pending: 1,
          rejected: 0,
        },
        hasNext: false,
        hasPrevious: false,
        items: [],
        nextCursor: null,
        previousCursor: null,
      });
    },
  });

  await client.listOperationalImageReviewItems({
    gameId: '22222222-2222-4222-8222-222222222222',
    importJobId: '33333333-3333-4333-8333-333333333333',
    limit: 1,
    resumeAtFirstPending: true,
    view: 'all',
  });

  const query = new URL(requests[0].url).searchParams;
  assert.equal(query.get('view'), 'all');
  assert.equal(query.get('limit'), '1');
  assert.equal(query.get('resumeAtFirstPending'), 'true');
});
