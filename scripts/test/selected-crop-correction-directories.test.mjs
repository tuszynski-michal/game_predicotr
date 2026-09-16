import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  auditSelectedCropCorrectionDirectories,
  runSelectedCropCorrectionDirectoryBatch,
} from '../preview_selected_crop_correction_directories.mjs';

const FILE_NAME = 'seq_1-9.jpg';

async function state(root, name, options = {}) {
  const sourceName = name.slice(0, -4);
  const cut = path.join(root, name);
  const stateDirectory = path.join(cut, '.manual-image-crop-state');
  const resultsDirectory = path.join(stateDirectory, 'results');
  if (options.source !== false) await mkdir(path.join(root, sourceName));
  await mkdir(resultsDirectory, { recursive: true });
  const inventory = {
    schemaVersion: 2,
    sourceDirectoryName: sourceName,
    outputDirectoryName: name,
    sourceInventoryChecksumSha256: 'a'.repeat(64),
    entries: [{ fileName: FILE_NAME, sizeBytes: 1, lastModifiedMs: 1 }],
  };
  const review = {
    schemaVersion: 2,
    reviewedFileNames: [],
    correctionFileNames: options.operatorOnly ? [FILE_NAME] : [],
    acceptedSuggestionFileNames: [],
    correctionCursor: 0,
    correctedFileNames: [],
    completedAt: options.accepted ? '2026-09-14T00:00:00.000Z' : null,
  };
  const session = {
    schemaVersion: 2,
    revision: 1,
    currentIndex: 0,
    pendingOperation: options.pending ? { fileName: FILE_NAME } : null,
    failures: options.failure ? [{ fileName: FILE_NAME }] : [],
    preparationPolicyVersion:
      'selected-image-board-band-v10-top-board-row-guided',
    updatedAt: '2026-09-14T00:00:00.000Z',
  };
  const proposal = options.operatorOnly
    ? { classification: 'high_confidence', evidence: {} }
    : {
        classification: 'high_confidence',
        evidence: { fallbackReason: 'crop_too_short' },
      };
  await Promise.all([
    writeFile(
      path.join(stateDirectory, 'inventory-v2.json'),
      JSON.stringify(inventory),
    ),
    writeFile(
      path.join(stateDirectory, 'review-v2.json'),
      JSON.stringify(review),
    ),
    writeFile(
      path.join(stateDirectory, 'session-v2.json'),
      JSON.stringify(session),
    ),
  ]);
  if (!options.missingResult)
    await writeFile(
      path.join(resultsDirectory, '000000.json'),
      JSON.stringify({
        schemaVersion: 2,
        shardIndex: 0,
        results: {
          [FILE_NAME]: {
            status: 'accepted',
            sourceChecksumSha256: 'b'.repeat(64),
            outputChecksumSha256: 'c'.repeat(64),
            autoCropProposal: proposal,
          },
        },
      }),
    );
}

test('audit classifies every cut directory and keeps natural order', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'crop-directory-audit-'));
  try {
    await state(root, '10 - 20 cut');
    await state(root, '2 - 9 cut', { accepted: true });
    await state(root, '21 - 30 cut', { missingResult: true });
    await state(root, '31 - 40 cut', { operatorOnly: true });
    await state(root, '41 - 50 cut', { source: false });
    const audit = await auditSelectedCropCorrectionDirectories(root);
    assert.deepEqual(
      audit.directories.map((item) => [item.cutName, item.eligibility]),
      [
        ['2 - 9 cut', 'accepted'],
        ['10 - 20 cut', 'eligible'],
        ['21 - 30 cut', 'incomplete'],
        ['31 - 40 cut', 'operator_only'],
        ['41 - 50 cut', 'source_missing'],
      ],
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('batch runs only eligible directories into separate preview paths', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'crop-directory-batch-'));
  const calls = [];
  try {
    await state(root, '10 - 20 cut');
    await state(root, '2 - 9 cut');
    await state(root, '21 - 30 cut', { accepted: true });
    const report = await runSelectedCropCorrectionDirectoryBatch(root, {
      writeReport: false,
      runPreview: async (source, cut, output) => {
        calls.push({ source, cut, output });
        return {
          total: 1,
          completed: 1,
          automatic: 1,
          structural: 1,
          registered: 0,
          boardBuffered: 1,
          manual: 0,
          failures: [],
        };
      },
    });
    assert.deepEqual(
      calls.map((item) => path.basename(item.cut)),
      ['2 - 9 cut', '10 - 20 cut'],
    );
    assert.ok(
      calls.every((item) =>
        item.output.endsWith(' cut v12 board-buffer preview'),
      ),
    );
    assert.deepEqual(
      report.directories.map((item) => item.runStatus ?? null),
      ['completed', 'completed', null],
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
