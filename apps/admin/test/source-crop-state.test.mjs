import assert from 'node:assert/strict';
import test from 'node:test';

import { jobTypeLabel } from '../src/features/jobs/job-state.ts';
import {
  EMPTY_SCOPE_DRAFT,
  buildScope,
  canStartRun,
  exclusionLabel,
  exclusionRows,
  isStartable,
  needsPolling,
  outcomeRows,
  parseChecksumList,
  pickResumableRun,
  progressPercent,
  scopeLabel,
  selectableGames,
  sourceCropErrorMessage,
  statusLabel,
} from '../src/features/storage/source-crop-state.ts';

const sha = (char) => char.repeat(64);

function run(overrides = {}) {
  return {
    candidateBytes: 0,
    checkpointIndex: 0,
    createdAt: '2026-10-17T10:00:00Z',
    eligibleCount: 0,
    errorCode: null,
    errorMessage: null,
    estimatedSavedBytes: 0,
    excludedCount: 0,
    exclusionCounts: {},
    failedCount: 0,
    failures: [],
    finishedAt: null,
    id: 'run-1',
    jobId: null,
    kind: 'crop',
    manifestChecksumSha256: null,
    outcomeCounts: {},
    planJobId: 'job-1',
    previewToken: null,
    processedCount: 0,
    savedBytes: 0,
    scope: {},
    skippedCount: 0,
    startedAt: null,
    status: 'planning',
    succeededCount: 0,
    updatedAt: null,
    ...overrides,
  };
}

test('builds the whole-catalog scope without null placeholders', () => {
  assert.deepEqual(buildScope(EMPTY_SCOPE_DRAFT), { ok: true, scope: {} });
});

test('builds game scope and optional limit, and requires a game', () => {
  assert.deepEqual(
    buildScope({
      ...EMPTY_SCOPE_DRAFT,
      gameId: ' game-1 ',
      limitText: '250',
      mode: 'game',
    }),
    { ok: true, scope: { gameId: 'game-1', limit: 250 } },
  );
  const missing = buildScope({ ...EMPTY_SCOPE_DRAFT, mode: 'game' });
  assert.equal(missing.ok, false);
  assert.match(missing.error, /Wybierz grę/);
});

test('normalizes, deduplicates and validates the checksum list', () => {
  const upper = sha('a').toUpperCase();
  assert.deepEqual(parseChecksumList(`${upper}\n${sha('a')},  ${sha('b')};`), [
    sha('a'),
    sha('b'),
  ]);
  assert.deepEqual(
    buildScope({
      ...EMPTY_SCOPE_DRAFT,
      checksumsText: `${upper}\n${sha('b')}`,
      mode: 'checksums',
    }),
    { ok: true, scope: { onlyChecksums: [sha('a'), sha('b')] } },
  );
  const empty = buildScope({ ...EMPTY_SCOPE_DRAFT, mode: 'checksums' });
  assert.equal(empty.ok, false);
  const bad = buildScope({
    ...EMPTY_SCOPE_DRAFT,
    checksumsText: 'not-a-hash',
    mode: 'checksums',
  });
  assert.equal(bad.ok, false);
  assert.match(bad.error, /SHA-256/);
  const many = Array.from({ length: 501 }, (_, index) =>
    index.toString(16).padStart(64, '0'),
  ).join('\n');
  const tooMany = buildScope({
    ...EMPTY_SCOPE_DRAFT,
    checksumsText: many,
    mode: 'checksums',
  });
  assert.equal(tooMany.ok, false);
  assert.match(tooMany.error, /500/);
});

test('rejects a limit outside 1..1000000', () => {
  for (const limitText of ['0', '-3', '1.5', 'abc', '1000001']) {
    assert.equal(buildScope({ ...EMPTY_SCOPE_DRAFT, limitText }).ok, false);
  }
  assert.equal(
    buildScope({ ...EMPTY_SCOPE_DRAFT, limitText: '1000000' }).ok,
    true,
  );
});

test('labels scope and statuses in Polish', () => {
  assert.equal(scopeLabel({}), 'wszystkie gry');
  assert.equal(scopeLabel({ gameId: 'g', limit: 5 }), 'gra g · limit 5');
  assert.equal(statusLabel('previewed'), 'Podgląd gotowy');
  assert.equal(statusLabel('processing'), 'W toku');
});

test('polls only while planning or executing', () => {
  for (const status of ['planning', 'created', 'processing']) {
    assert.equal(needsPolling(run({ status })), true, status);
  }
  for (const status of ['previewed', 'completed', 'failed', 'cancelled']) {
    assert.equal(needsPolling(run({ status })), false, status);
  }
});

test('start needs a previewed run with checksum, token and eligible originals', () => {
  const base = run({
    eligibleCount: 3,
    manifestChecksumSha256: sha('c'),
    previewToken: 'token',
    status: 'previewed',
  });
  assert.equal(isStartable(base), true);
  assert.equal(canStartRun(base, false), true);
  assert.equal(canStartRun({ ...base, eligibleCount: 0 }, true), false);
  assert.equal(canStartRun({ ...base, previewToken: null }, true), false);
  assert.equal(canStartRun({ ...base, status: 'planning' }, true), false);
});

test('deletion start requires the irreversibility acknowledgement', () => {
  const deletion = run({
    eligibleCount: 3,
    kind: 'original_deletion',
    manifestChecksumSha256: sha('c'),
    previewToken: 'token',
    status: 'previewed',
  });
  assert.equal(canStartRun(deletion, false), false);
  assert.equal(canStartRun(deletion, true), true);
});

test('shows exclusion reasons with readable labels and raw codes', () => {
  const value = run({
    exclusionCounts: {
      ALREADY_CROPPED: 4,
      GRID_ISSUE: 0,
      ORIGINAL_MISSING: 9,
      UNKNOWN_NEW_CODE: 2,
    },
  });
  assert.deepEqual(exclusionRows(value), [
    ['ORIGINAL_MISSING', 9],
    ['ALREADY_CROPPED', 4],
    ['UNKNOWN_NEW_CODE', 2],
  ]);
  assert.equal(
    exclusionLabel('ALREADY_CROPPED'),
    'Już przycięte (ALREADY_CROPPED)',
  );
  assert.equal(exclusionLabel('UNKNOWN_NEW_CODE'), 'UNKNOWN_NEW_CODE');
});

test('lists every deletion outcome, including zero counts, and unknown ones', () => {
  const rows = outcomeRows(
    run({
      kind: 'original_deletion',
      outcomeCounts: { cropChanged: 1, deleted: 7, futureOutcome: 2 },
    }),
  );
  assert.deepEqual(
    rows.map(([code]) => code),
    [
      'deleted',
      'notCropped',
      'alreadyDeleted',
      'cropChanged',
      'notEligible',
      'failed',
      'futureOutcome',
    ],
  );
  assert.deepEqual(
    rows.find(([code]) => code === 'deleted'),
    ['deleted', 7],
  );
  assert.deepEqual(
    rows.find(([code]) => code === 'notCropped'),
    ['notCropped', 0],
  );
});

test('computes bounded progress percent', () => {
  assert.equal(progressPercent(run({ eligibleCount: 0 })), 0);
  assert.equal(
    progressPercent(
      run({ eligibleCount: 200, processedCount: 50, status: 'processing' }),
    ),
    25,
  );
  assert.equal(
    progressPercent(
      run({ eligibleCount: 10, processedCount: 99, status: 'processing' }),
    ),
    100,
  );
  assert.equal(
    progressPercent(run({ eligibleCount: 0, status: 'completed' })),
    100,
  );
});

test('maps the run error codes to Polish messages and keeps the code', () => {
  for (const code of [
    'SOURCE_CROP_RUN_ACTIVE',
    'SOURCE_CROP_PREVIEW_STALE',
    'SOURCE_CROP_CONFIRMATION_REQUIRED',
    'SOURCE_ORIGINAL_DELETION_ACKNOWLEDGEMENT_REQUIRED',
    'SOURCE_CROP_SCOPE_INVALID',
  ]) {
    const message = sourceCropErrorMessage({ code, message: 'english' }, 'fb');
    assert.ok(message.endsWith(`(${code})`), message);
    assert.doesNotMatch(message, /english/);
  }
  assert.equal(
    sourceCropErrorMessage({ code: 'OTHER', message: 'Coś innego' }, 'fb'),
    'Coś innego (OTHER)',
  );
  assert.equal(sourceCropErrorMessage(undefined, 'fb'), 'fb');
});

test('resumes the newest non-superseded run of the same kind', () => {
  const runs = [
    run({
      createdAt: '2026-10-17T09:00:00Z',
      id: 'old',
      kind: 'crop',
      status: 'completed',
    }),
    run({
      createdAt: '2026-10-17T12:00:00Z',
      errorCode: 'SOURCE_CROP_PREVIEW_SUPERSEDED',
      id: 'superseded',
      kind: 'crop',
      status: 'cancelled',
    }),
    run({
      createdAt: '2026-10-17T11:00:00Z',
      id: 'newest',
      kind: 'crop',
      status: 'previewed',
    }),
    run({
      createdAt: '2026-10-17T13:00:00Z',
      id: 'deletion',
      kind: 'original_deletion',
    }),
  ];
  assert.equal(pickResumableRun(runs, 'crop')?.id, 'newest');
  assert.equal(pickResumableRun(runs, 'original_deletion')?.id, 'deletion');
  assert.equal(pickResumableRun([], 'crop'), null);
});

test('labels the crop and original deletion job types in the jobs list', () => {
  assert.equal(jobTypeLabel('source_crop'), 'Przycinanie oryginalnych zdjęć');
  assert.equal(
    jobTypeLabel('source_original_deletion'),
    'Usuwanie oryginałów przyciętych zdjęć',
  );
});

test('game scope offers active and draft games only, with equal names kept apart', () => {
  const games = [
    { id: '4', code: 'mumie', name: 'Mumie a1', status: 'active' },
    { id: '3', code: '777v2', name: '777 a2', status: 'archived' },
    { id: '2', code: '777a2', name: '777 a2', status: 'active' },
    { id: '1', code: '7', name: '777 a1', status: 'active' },
    { id: '5', code: 'new', name: 'Nowa', status: 'draft' },
  ];
  assert.deepEqual(
    selectableGames(games).map((game) => game.code),
    ['7', '777a2', 'mumie', 'new'],
  );
  assert.equal(games.length, 5);
});
