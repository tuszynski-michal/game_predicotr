import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import {
  parseReplacementRequest,
  replacementCanonicalJson,
  replacementRequestPayload,
  validateReplacementTarget,
  assertCurrentReplacementEntry,
  createReplacementRepair,
  deriveReplacementFilledGaps,
  deriveReplacementStagingSelection,
  validateReplacementRepair,
} from '../src/replacement-repair.ts';
import {
  validateRepairManifest,
  validateLegacyRepairManifest,
  validateFilledGapsManifest,
} from '../src/repair.ts';

const fixture = JSON.parse(
  readFileSync(
    new URL(
      '../../admin-api-client/test/fixtures/source-replacement-request-v1.json',
      import.meta.url,
    ),
  ),
);
const current = (request = fixture) => ({
  id: request.entries[0].entryId,
  phase: 'gap_open',
  revision: request.entries[0].revision,
  scopeDigest: request.entries[0].digest,
  sourceSha256: request.entries[0].sourceSha256,
  sequenceNumbers: request.entries[0].sequenceNumbers,
  rangeStart: request.allowedRanges[0].sequenceStart,
  rangeEnd: request.allowedRanges[0].sequenceEnd,
});
const entry = fixture.entries[0].entryId;

test('actual PG wire fixture has Python-compatible canonical digest and accepts reordered keys', () => {
  const parsed = parseReplacementRequest(fixture);
  assert.equal(
    createHash('sha256')
      .update(replacementCanonicalJson(replacementRequestPayload(parsed)))
      .digest('hex'),
    fixture.digest,
  );
  assert.deepEqual(
    parseReplacementRequest({
      origin: 'https://untrusted.invalid',
      ...fixture,
    }),
    fixture,
  );
  assert.deepEqual(
    parseReplacementRequest(
      Object.fromEntries(Object.entries(fixture).reverse()),
    ),
    fixture,
  );
});

test('exact ranges, selected scope, contiguous safe integer seq and duplicate entries fail closed', () => {
  validateReplacementTarget(fixture, entry, 'seq_1-9.jpeg');
  for (const name of ['seq_1-8.jpg', 'seq_2-9.jpg', 'seq_1-10.jpg'])
    assert.throws(
      () => validateReplacementTarget(fixture, entry, name),
      /RANGE/,
    );
  assert.throws(
    () => validateReplacementTarget(fixture, 'other', 'seq_1-9.jpg'),
    /ENTRY_NOT_SELECTED/,
  );
  assert.throws(
    () =>
      parseReplacementRequest({
        ...fixture,
        entries: [fixture.entries[0], fixture.entries[0]],
        allowedRanges: [fixture.allowedRanges[0], fixture.allowedRanges[0]],
      }),
    /INVALID_ENTRY|INVALID_RANGE/,
  );
  assert.throws(
    () =>
      parseReplacementRequest({
        ...fixture,
        entries: [{ ...fixture.entries[0], sequenceNumbers: [1, 3] }],
        allowedRanges: [{ ...fixture.allowedRanges[0], sequenceEnd: 2 }],
      }),
    /INVALID_SEQUENCE/,
  );
  const short = {
    ...fixture,
    entries: [{ ...fixture.entries[0], sequenceNumbers: [101, 102] }],
    allowedRanges: [
      { ...fixture.allowedRanges[0], sequenceStart: 101, sequenceEnd: 102 },
    ],
  };
  validateReplacementTarget(
    parseReplacementRequest(short),
    entry,
    'seq_101-102.jpg',
  );
});

test('only target entry exact identity authorizes new local writes', () => {
  assertCurrentReplacementEntry(fixture, entry, current());
  for (const patch of [
    { phase: 'planned' },
    { phase: 'restored' },
    { revision: 3 },
    { scopeDigest: 'b'.repeat(64) },
    { rangeEnd: 8 },
    { sequenceNumbers: [1, 2] },
    { sourceSha256: 'b'.repeat(64) },
  ])
    assert.throws(
      () =>
        assertCurrentReplacementEntry(fixture, entry, {
          ...current(),
          ...patch,
        }),
      /ENTRY_STALE/,
    );
  assert.throws(
    () => assertCurrentReplacementEntry(fixture, entry, undefined),
    /ENTRY_STALE/,
  );
});

test('v3 does not enter v1/v2, and an intent never creates filled-gaps or a staging receipt', () => {
  const manifest = createReplacementRepair(fixture, 'repair', 'output', 'now');
  const write = {
    id: 'operation',
    entryId: entry,
    fileName: 'seq_1-9.jpg',
    checksumSha256: 'b'.repeat(64),
    size: 10,
    sourcePath: 'seq_1-9.jpeg',
    sourceIndex: null,
    occurredAt: 'then',
    state: 'intent',
  };
  const pending = { ...manifest, journal: [write] };
  assert.throws(() => validateRepairManifest(pending), /INVALID_REPAIR/);
  assert.throws(() => validateLegacyRepairManifest(pending), /INVALID_REPAIR/);
  assert.equal(deriveReplacementFilledGaps(pending, []).entries.length, 0);
  assert.throws(
    () => deriveReplacementStagingSelection(pending, [], [entry]),
    /NOT_COMMITTED/,
  );
  const committed = { ...pending, journal: [{ ...write, state: 'committed' }] };
  assert.throws(() => deriveReplacementFilledGaps(committed, []), /UNVERIFIED/);
  const verified = [
    {
      fileName: write.fileName,
      checksumSha256: write.checksumSha256,
      size: write.size,
    },
  ];
  const handoff = validateFilledGapsManifest(
    deriveReplacementFilledGaps(committed, verified),
  );
  assert.deepEqual(
    Object.keys(handoff.entries[0]).sort(),
    [
      'checksumSha256',
      'end',
      'fileName',
      'fillOperationId',
      'filledAt',
      'sourceIndex',
      'sourcePath',
      'start',
    ].sort(),
  );
  assert.equal(handoff.entries[0].sourcePath, write.sourcePath);
  assert.equal(handoff.entries[0].fillOperationId, write.id);
  assert.throws(
    () =>
      validateReplacementRepair({
        ...pending,
        journal: [write, { ...write, id: 'other' }],
      }),
    /INVALID_JOURNAL/,
  );
});

test('partial output A keeps original request A+B but stages only selected verified committed A', () => {
  const b = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
  const request = parseReplacementRequest({
    ...fixture,
    entries: [
      ...fixture.entries,
      { ...fixture.entries[0], entryId: b, sequenceNumbers: [19, 20] },
    ],
    allowedRanges: [
      ...fixture.allowedRanges,
      { entryId: b, sequenceStart: 19, sequenceEnd: 20 },
    ],
  });
  const write = {
    id: 'operation-A',
    entryId: entry,
    fileName: 'seq_1-9.jpg',
    checksumSha256: 'b'.repeat(64),
    size: 10,
    sourcePath: 'seq_1-9.jpeg',
    sourceIndex: null,
    occurredAt: 'then',
    state: 'committed',
  };
  const manifest = {
    ...createReplacementRepair(request, 'repair', 'output', 'now'),
    journal: [write],
  };
  const verified = [
    {
      fileName: write.fileName,
      checksumSha256: write.checksumSha256,
      size: write.size,
    },
  ];
  const result = deriveReplacementStagingSelection(manifest, verified, [entry]);
  assert.equal(result.request.entries.length, 2);
  assert.equal(result.request.entries[0].digest, fixture.entries[0].digest);
  assert.deepEqual(result.selectedEntryIds, [entry]);
  assert.equal(result.files.length, 1);
  assert.equal(result.files[0].operationId, write.id);
  assert.throws(
    () => deriveReplacementStagingSelection(manifest, verified, [b]),
    /NOT_COMMITTED/,
  );
  assert.throws(
    () => deriveReplacementStagingSelection(manifest, verified, [entry, entry]),
    /INVALID_SELECTION/,
  );
});
