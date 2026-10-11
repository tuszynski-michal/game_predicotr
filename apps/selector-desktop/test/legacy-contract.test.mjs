import test, { describe } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { writeFile, readFile, utimes, unlink, mkdir } from 'node:fs/promises';
import { buildRemoteSourceManifestV1 } from '@game-predictor/manual-image-selection-core';
import { inspectLegacy } from '../src/legacy-adoption/legacy-preview.ts';
import { ProjectStore } from '../src/project/project-store.ts';
import { ProjectController } from '../src/native/project-controller.ts';
import { SourceRegistry } from '../src/native/source-registry.ts';
import { legacyFixture, originalProof, processes } from './legacy-fixture.mjs';
describe('read-only legacy contract', { concurrency: 6 }, () => {
  for (const schemaVersion of [1, 2])
    for (const direction of ['ascending', 'descending'])
      test(`v${schemaVersion} ${direction} preserves corrected ranges, skipped null fields and saved cursor`, async (t) => {
        const f = await legacyFixture(t, { schemaVersion, direction });
        const original = await originalProof(f);
        const proof = await inspectLegacy(f.sourceRoot, f.oldOutputRoot);
        assert.equal(proof.seed.currentRelativePath, 'photo20.jpg');
        assert.equal(proof.seed.selectionGeneration, 7);
        const store = f.track(
          await ProjectStore.createFromSelection(
            f.input,
            { processes },
            proof.seed,
            f.oldOutputRoot,
          ),
        );
        const state = store.snapshot();
        assert.deepEqual(state.decisions, proof.seed.decisions);
        assert.equal(state.firstLayout, f.manifest.firstLayout);
        assert.equal(state.nextRangeStart, f.manifest.nextRangeStart);
        assert.equal(state.currentRelativePath, 'photo20.jpg');
        await store.close();
        const opened = f.track(
          await ProjectStore.open(f.input.projectRoot, { processes }),
        );
        assert.equal(opened.getIssue(), null);
        assert.deepEqual(opened.snapshot().decisions, state.decisions);
        assert.deepEqual(await originalProof(f), original);
        const output = JSON.parse(
          await readFile(
            path.join(
              f.input.outputRoot,
              'manual-image-selection-output-v1.json',
            ),
            'utf8',
          ),
        );
        assert.equal(output.schemaVersion, 2);
        assert.equal(output.sourceTraversalSemantics, 'natural_v2');
        assert.notEqual(output.sessionId, f.manifest.sessionId);
      });
  test('descending legacy cursor anchors to last accepted ordinal, ignores skipped and saved cursor', async (t) => {
    const f = await legacyFixture(t, {
      direction: 'descending',
      traversal: null,
    });
    assert.equal(
      (await inspectLegacy(f.sourceRoot, f.oldOutputRoot)).seed
        .currentRelativePath,
      'photo2.jpeg',
    );
    f.manifest.decisions.shift();
    await unlink(path.join(f.oldOutputRoot, 'seq_28-36.jpg'));
    await f.save();
    assert.equal(
      (await inspectLegacy(f.sourceRoot, f.oldOutputRoot)).seed
        .currentRelativePath,
      'photo1.jpg',
    );
  });
  test('terminal v2 preserves partial final range and generation', async (t) => {
    const f = await legacyFixture(t, { terminal: true });
    const proof = await inspectLegacy(f.sourceRoot, f.oldOutputRoot);
    const store = f.track(
      await ProjectStore.createFromSelection(
        f.input,
        { processes },
        proof.seed,
        f.oldOutputRoot,
      ),
    );
    assert.equal(store.snapshot().selectionComplete, true);
    assert.equal(store.snapshot().sequenceUpperBound, 40);
    assert.equal(store.snapshot().decisions.at(-1).activeBoardCount, 4);
  });
  test('terminal v1 descending cannot silently change incomplete flag', async (t) => {
    const f = await legacyFixture(t, {
      schemaVersion: 1,
      direction: 'descending',
      terminal: true,
    });
    const original = await originalProof(f);
    await assert.rejects(inspectLegacy(f.sourceRoot, f.oldOutputRoot), {
      code: 'LEGACY_STATE_CONFLICT',
    });
    assert.deepEqual(await originalProof(f), original);
  });
  test('historical browser MIME checksum difference is rejected without guessing metadata', async (t) => {
    const f = await legacyFixture(t);
    const proof = await inspectLegacy(f.sourceRoot, f.oldOutputRoot);
    const historical = await buildRemoteSourceManifestV1(
      proof.seed.inventory.map((item) => ({
        ...item,
        mimeType: 'image/pjpeg',
      })),
      'directory_handle',
    );
    f.manifest.sourceManifestChecksumSha256 = historical.manifestChecksumSha256;
    await f.save();
    const original = await originalProof(f);
    await assert.rejects(inspectLegacy(f.sourceRoot, f.oldOutputRoot), {
      code: 'LEGACY_SOURCE_CONFLICT',
    });
    assert.deepEqual(await originalProof(f), original);
  });
  const invalid = [
    [
      'core items',
      (m) => {
        m.storageMode = 'core_items';
        m.items = [];
      },
      'LEGACY_UNSUPPORTED',
    ],
    [
      'unknown schema',
      (m) => {
        m.schemaVersion = 3;
      },
      'LEGACY_UNSUPPORTED',
    ],
    [
      'missing fingerprint',
      (m) => {
        delete m.sourceManifestChecksumSha256;
      },
      'LEGACY_MISSING_PROOF',
    ],
    [
      'missing count',
      (m) => {
        delete m.fileCount;
      },
      'LEGACY_MISSING_PROOF',
    ],
    [
      'missing first',
      (m) => {
        delete m.firstLayout;
      },
      'LEGACY_MISSING_PROOF',
    ],
    [
      'missing direction',
      (m) => {
        delete m.direction;
      },
      'LEGACY_MISSING_PROOF',
    ],
    [
      'wrong name',
      (m) => {
        m.sourceDirectoryName = 'another';
      },
      'LEGACY_SOURCE_CONFLICT',
    ],
    [
      'wrong count',
      (m) => {
        m.fileCount++;
      },
      'LEGACY_SOURCE_CONFLICT',
    ],
    [
      'changed fingerprint',
      (m) => {
        m.sourceManifestChecksumSha256 = 'a'.repeat(64);
      },
      'LEGACY_SOURCE_CONFLICT',
    ],
    [
      'ordinal/path mismatch',
      (m) => {
        m.decisions[0].sourceIndex = 1;
      },
      'LEGACY_STATE_CONFLICT',
    ],
    [
      'skipped nonnull',
      (m) => {
        m.decisions[1].imagePath = 'photo1.jpg';
      },
      'LEGACY_STATE_CONFLICT',
    ],
    [
      'wrong active count',
      (m) => {
        m.decisions[0].activeBoardCount = 8;
      },
      'LEGACY_INVALID',
    ],
    [
      'invalid range',
      (m) => {
        m.decisions[0].rangeEnd = 8;
        m.decisions[0].activeBoardCount = 8;
      },
      'LEGACY_STATE_CONFLICT',
    ],
  ];
  for (const [name, change, code] of invalid)
    test(`rejects ${name} without original mutation`, async (t) => {
      const f = await legacyFixture(t);
      change(f.manifest);
      await f.save();
      const original = await originalProof(f);
      await assert.rejects(inspectLegacy(f.sourceRoot, f.oldOutputRoot), {
        code,
      });
      assert.deepEqual(await originalProof(f), original);
    });
  test('mtime mismatch, foreign/missing output and source/output byte drift all reject', async (t) => {
    const f = await legacyFixture(t);
    await utimes(
      path.join(f.sourceRoot, 'photo20.jpg'),
      1700000001,
      1700000001,
    );
    await assert.rejects(inspectLegacy(f.sourceRoot, f.oldOutputRoot), {
      code: 'LEGACY_SOURCE_CONFLICT',
    });
    await utimes(
      path.join(f.sourceRoot, 'photo20.jpg'),
      1700000000,
      1700000000.123,
    );
    await writeFile(path.join(f.oldOutputRoot, 'foreign.jpg'), 'foreign');
    await assert.rejects(inspectLegacy(f.sourceRoot, f.oldOutputRoot), {
      code: 'LEGACY_OUTPUT_CONFLICT',
    });
    await unlink(path.join(f.oldOutputRoot, 'foreign.jpg'));
    const target = path.join(f.oldOutputRoot, 'seq_1-9.jpg');
    const original = await readFile(target);
    await writeFile(target, 'different');
    await assert.rejects(inspectLegacy(f.sourceRoot, f.oldOutputRoot), {
      code: 'LEGACY_CHECKSUM_CONFLICT',
    });
    await unlink(target);
    await assert.rejects(inspectLegacy(f.sourceRoot, f.oldOutputRoot), {
      code: 'LEGACY_OUTPUT_CONFLICT',
    });
    await writeFile(target, original);
    await writeFile(
      path.join(f.sourceRoot, 'photo1.jpg'),
      Buffer.alloc(original.length),
    );
    await utimes(
      path.join(f.sourceRoot, 'photo1.jpg'),
      1700000000,
      1700000000.123,
    );
    await assert.rejects(inspectLegacy(f.sourceRoot, f.oldOutputRoot), {
      code: 'LEGACY_CHECKSUM_CONFLICT',
    });
  });
  test('new roots cannot overlap old output or use nonempty destination', async (t) => {
    const f = await legacyFixture(t);
    const proof = await inspectLegacy(f.sourceRoot, f.oldOutputRoot);
    const original = await originalProof(f);
    await assert.rejects(
      ProjectStore.createFromSelection(
        { ...f.input, projectRoot: path.join(f.oldOutputRoot, 'nested') },
        { processes },
        proof.seed,
        f.oldOutputRoot,
      ),
      { code: 'OVERLAPPING_ROOTS' },
    );
    await assert.rejects(
      ProjectStore.createFromSelection(
        { ...f.input, outputRoot: f.oldOutputRoot },
        { processes },
        proof.seed,
        f.oldOutputRoot,
      ),
      { code: 'OVERLAPPING_ROOTS' },
    );
    assert.deepEqual(await originalProof(f), original);
    await mkdir(f.input.outputRoot);
    const foreign = path.join(f.input.outputRoot, 'foreign.jpg');
    await writeFile(foreign, 'foreign');
    await assert.rejects(
      ProjectStore.createFromSelection(
        f.input,
        { processes },
        proof.seed,
        f.oldOutputRoot,
      ),
      { code: 'FOREIGN_CONTENT' },
    );
    assert.equal(await readFile(foreign, 'utf8'), 'foreign');
    assert.deepEqual(await originalProof(f), original);
  });
  test('syntactically resumable repeated source photo is explicitly unsupported and original stays intact', async (t) => {
    const f = await legacyFixture(t);
    f.manifest.decisions.push({
      ...f.manifest.decisions[0],
      operationId: 'duplicate-accepted',
      rangeStart: 28,
      rangeEnd: 36,
      outputName: 'seq_28-36.jpg',
    });
    await writeFile(
      path.join(f.oldOutputRoot, 'seq_28-36.jpg'),
      await readFile(path.join(f.sourceRoot, 'photo1.jpg')),
    );
    await f.save();
    const original = await originalProof(f);
    await assert.rejects(inspectLegacy(f.sourceRoot, f.oldOutputRoot), {
      code: 'LEGACY_UNSUPPORTED_HISTORY',
    });
    assert.deepEqual(await originalProof(f), original);
  });
  test('native tokens reject paths, revalidate preview and preserve active source URLs on cancellation', async (t) => {
    const f = await legacyFixture(t);
    const directories = [f.sourceRoot, f.oldOutputRoot, null];
    const registry = new SourceRegistry();
    const indexed = await registry.register(f.sourceRoot);
    const controller = new ProjectController(
      path.join(f.root, 'user-data'),
      registry,
      {
        directory: async () => directories.shift(),
        confirm: async () => false,
        openFolder: async () => {},
      },
    );
    t.after(() => controller.close());
    const preview = await controller.legacyPreview();
    assert.equal(registry.getRoot(indexed.id), f.sourceRoot);
    assert.ok(!JSON.stringify(preview).includes(f.root));
    await assert.rejects(controller.legacyAdopt('../source'), {
      code: 'INVALID_ARGUMENT',
    });
    assert.equal(await controller.legacyAdopt(preview.previewToken), null);
    assert.equal(registry.getRoot(indexed.id), f.sourceRoot);
    directories.push(f.input.projectRoot, f.input.outputRoot);
    controller['dialogs'].confirm = async () => true;
    f.manifest.currentIndex = 2;
    await f.save();
    await assert.rejects(controller.legacyAdopt(preview.previewToken), {
      code: 'LEGACY_CHANGED',
    });
  });
});
