import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import sharp from 'sharp';

import {
  orderedNeighbourIndexes,
  runSelectedCropCorrectionPreview,
} from '../preview_selected_crop_corrections.mjs';

test('neighbour search is deterministic and nearest-first', () => {
  assert.deepEqual(orderedNeighbourIndexes(2, 6, 2), [1, 3, 0, 4]);
  assert.deepEqual(orderedNeighbourIndexes(0, 3, 2), [1, 2]);
});

test('preview processes only the persisted automatic correction and resumes safely', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'selected-crop-preview-'));
  const source = path.join(root, 'picked');
  const current = path.join(root, 'picked cut');
  const output = path.join(root, 'picked cut v12 preview');
  const state = path.join(current, '.manual-image-crop-state');
  const results = path.join(state, 'results');
  const fileName = 'seq_1-9.jpg';
  try {
    await mkdir(source);
    await mkdir(results, { recursive: true });
    const jpeg = await sharp({
      create: {
        width: 32,
        height: 32,
        channels: 3,
        background: '#111827',
      },
    })
      .jpeg()
      .toBuffer();
    await writeFile(path.join(source, fileName), jpeg);
    const sourceChecksumSha256 = createHash('sha256')
      .update(jpeg)
      .digest('hex');
    await writeFile(
      path.join(state, 'inventory-v2.json'),
      JSON.stringify({
        schemaVersion: 2,
        sourceDirectoryName: 'picked',
        outputDirectoryName: 'picked cut',
        sourceInventoryChecksumSha256: 'a'.repeat(64),
        entries: [{ fileName, sizeBytes: jpeg.length, lastModifiedMs: 1 }],
      }),
    );
    await writeFile(
      path.join(state, 'review-v2.json'),
      JSON.stringify({
        schemaVersion: 2,
        reviewedFileNames: [],
        correctionFileNames: [fileName],
        acceptedSuggestionFileNames: [],
        correctionCursor: 0,
        correctedFileNames: [],
        completedAt: null,
      }),
    );
    await writeFile(
      path.join(state, 'session-v2.json'),
      JSON.stringify({
        schemaVersion: 2,
        revision: 1,
        currentIndex: 0,
        pendingOperation: null,
        failures: [],
        preparationPolicyVersion:
          'selected-image-board-band-v10-top-board-row-guided',
        updatedAt: '2026-09-14T00:00:00.000Z',
      }),
    );
    await writeFile(
      path.join(results, '000000.json'),
      JSON.stringify({
        schemaVersion: 2,
        shardIndex: 0,
        results: {
          [fileName]: {
            status: 'accepted',
            sourceChecksumSha256,
            outputChecksumSha256: 'b'.repeat(64),
            autoCropProposal: {
              classification: 'high_confidence',
              evidence: { fallbackReason: 'crop_too_short' },
            },
          },
        },
      }),
    );

    const first = await runSelectedCropCorrectionPreview(
      source,
      current,
      output,
    );
    assert.deepEqual(
      {
        total: first.total,
        completed: first.completed,
        automatic: first.automatic,
        manual: first.manual,
        failures: first.failures.length,
      },
      { total: 1, completed: 1, automatic: 0, manual: 1, failures: 0 },
    );
    assert.ok((await readFile(path.join(output, fileName))).length > 0);

    const resumed = await runSelectedCropCorrectionPreview(
      source,
      current,
      output,
    );
    assert.equal(resumed.completed, 1);
    assert.equal(resumed.failures.length, 0);
  } finally {
    const resolved = path.resolve(root);
    assert.ok(resolved.startsWith(path.resolve(os.tmpdir())));
    await rm(resolved, { recursive: true, force: true });
  }
});
