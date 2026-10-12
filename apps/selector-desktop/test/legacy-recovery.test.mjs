import test, { describe } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readFile, readdir, writeFile, utimes } from 'node:fs/promises';
import path from 'node:path';
import { inspectLegacy } from '../src/legacy-adoption/legacy-preview.ts';
import { ProjectStore } from '../src/project/project-store.ts';
import {
  decodeEnvelope,
  encodeEnvelope,
  validateJournal,
} from '../src/project/state-codec.ts';
import { legacyFixture, originalProof, processes } from './legacy-fixture.mjs';
async function twoCopies(f) {
  const d = {
    ...f.manifest.decisions[0],
    operationId: 'second-accepted',
    sourceIndex: 1,
    imagePath: 'photo2.jpeg',
    rangeStart: 28,
    rangeEnd: 36,
    outputName: 'seq_28-36.jpg',
  };
  const { hash } = await import('./legacy-fixture.mjs');
  const bytes = await readFile(path.join(f.sourceRoot, d.imagePath));
  d.imageChecksumSha256 = hash(bytes);
  f.manifest.decisions.push(d);
  await writeFile(path.join(f.oldOutputRoot, d.outputName), bytes);
  await f.save();
}
describe('adoption durable multi-file journal', { concurrency: 6 }, () => {
  for (const phase of [
    'prepare:after',
    'jpeg:chunk',
    'jpeg:replace',
    'import:copy',
    'jpeg:after',
    'state:before',
    'state:after',
    'manifest:before',
    'manifest:after',
    'backup:before',
    'backup:after',
    'finalize:before',
    'finalize:after',
  ])
    test(`adoption recovers exact complete history after ${phase} ENOSPC`, async (t) => {
      const f = await legacyFixture(t);
      await twoCopies(f);
      const proof = await inspectLegacy(f.sourceRoot, f.oldOutputRoot);
      const original = await originalProof(f);
      await assert.rejects(
        ProjectStore.createFromSelection(
          f.input,
          {
            processes,
            checkpoint(point) {
              if (point === phase)
                throw Object.assign(new Error('disk full fixture'), {
                  code: 'ENOSPC',
                });
            },
          },
          proof.seed,
          f.oldOutputRoot,
        ),
        { code: 'DISK_FULL' },
      );
      const store = f.track(
        await ProjectStore.open(f.input.projectRoot, { processes }),
      );
      assert.equal(store.getIssue(), null);
      assert.deepEqual(store.snapshot().decisions, proof.seed.decisions);
      assert.equal(store.snapshot().currentRelativePath, 'photo20.jpg');
      const names = await readdir(f.input.outputRoot);
      assert.deepEqual(names.sort(), [
        'manual-image-selection-output-v1.json',
        'seq_1-9.jpg',
        'seq_28-36.jpg',
      ]);
      assert.ok(
        !(await readdir(f.input.projectRoot)).includes(
          'selector-journal-v1.json',
        ),
      );
      assert.deepEqual(await originalProof(f), original);
      await store.close();
      const reopened = f.track(
        await ProjectStore.open(f.input.projectRoot, { processes }),
      );
      assert.deepEqual(reopened.snapshot(), store.snapshot());
    });
  test('versioned import journal cannot omit a copy or mutate its checksum', async (t) => {
    const f = await legacyFixture(t);
    await twoCopies(f);
    const proof = await inspectLegacy(f.sourceRoot, f.oldOutputRoot);
    await assert.rejects(
      ProjectStore.createFromSelection(
        f.input,
        {
          processes,
          checkpoint(point) {
            if (point === 'prepare:after')
              throw Object.assign(new Error('full'), { code: 'ENOSPC' });
          },
        },
        proof.seed,
        f.oldOutputRoot,
      ),
    );
    const journalPath = path.join(
      f.input.projectRoot,
      'selector-journal-v1.json',
    );
    const journal = decodeEnvelope(await readFile(journalPath));
    assert.equal(journal.schemaVersion, 2);
    const changedHash = structuredClone(journal);
    changedHash.importCopies[0].checksumSha256 = 'a'.repeat(64);
    assert.throws(() => validateJournal(changedHash), {
      code: 'JOURNAL_CORRUPT',
    });
    const malformedCopy = structuredClone(journal);
    malformedCopy.importCopies[0] = null;
    assert.throws(() => validateJournal(malformedCopy), {
      code: 'JOURNAL_CORRUPT',
    });
    journal.importCopies.pop();
    assert.throws(() => validateJournal(journal), { code: 'JOURNAL_CORRUPT' });
    await writeFile(journalPath, encodeEnvelope(journal));
    await assert.rejects(
      ProjectStore.open(f.input.projectRoot, { processes }),
      { code: 'JOURNAL_CORRUPT' },
    );
  });
});
describe('adoption boundary faults', { concurrency: 6 }, () => {
  for (const phase of [
    'prepare:before',
    'selector-journal-v1.json:temp',
    'selector-journal-v1.json:sync',
    'selector-journal-v1.json:replace',
  ])
    test(`unprepared adoption ${phase} leaves no JPEG or resumable intent`, async (t) => {
      const f = await legacyFixture(t);
      const proof = await inspectLegacy(f.sourceRoot, f.oldOutputRoot);
      const original = await originalProof(f);
      await assert.rejects(
        ProjectStore.createFromSelection(
          f.input,
          {
            processes,
            checkpoint(point) {
              if (point === phase)
                throw Object.assign(new Error('full'), { code: 'ENOSPC' });
            },
          },
          proof.seed,
          f.oldOutputRoot,
        ),
        { code: 'DISK_FULL' },
      );
      assert.deepEqual(await readdir(f.input.outputRoot), []);
      assert.deepEqual(await readdir(f.input.projectRoot), []);
      await assert.rejects(
        ProjectStore.open(f.input.projectRoot, { processes }),
        { code: 'PROJECT_FOLDER_FOREIGN' },
      );
      assert.deepEqual(await readdir(f.input.projectRoot), []);
      assert.deepEqual(await originalProof(f), original);
    });
  for (const phase of [
    'selector-project-v1.json:temp',
    'selector-project-v1.json:sync',
    'selector-project-v1.json:replace',
    'manual-image-selection-output-v1.json:temp',
    'manual-image-selection-output-v1.json:sync',
    'manual-image-selection-output-v1.json:replace',
    'selector-project-v1.backup.json:sync',
  ])
    test(`prepared adoption file fault ${phase} completes after reopen`, async (t) => {
      const f = await legacyFixture(t);
      await twoCopies(f);
      const proof = await inspectLegacy(f.sourceRoot, f.oldOutputRoot);
      const original = await originalProof(f);
      await assert.rejects(
        ProjectStore.createFromSelection(
          f.input,
          {
            processes,
            checkpoint(point) {
              if (point === phase)
                throw Object.assign(new Error('full'), { code: 'ENOSPC' });
            },
          },
          proof.seed,
          f.oldOutputRoot,
        ),
        { code: 'DISK_FULL' },
      );
      const store = f.track(
        await ProjectStore.open(f.input.projectRoot, { processes }),
      );
      assert.equal(store.getIssue(), null);
      assert.deepEqual(store.snapshot().decisions, proof.seed.decisions);
      assert.deepEqual(await originalProof(f), original);
    });
  test('recovery rechecks source bytes even when its first imported JPEG already exists', async (t) => {
    const f = await legacyFixture(t);
    await twoCopies(f);
    const proof = await inspectLegacy(f.sourceRoot, f.oldOutputRoot);
    await assert.rejects(
      ProjectStore.createFromSelection(
        f.input,
        {
          processes,
          checkpoint(point) {
            if (point === 'import:copy')
              throw Object.assign(new Error('full'), { code: 'ENOSPC' });
          },
        },
        proof.seed,
        f.oldOutputRoot,
      ),
    );
    const sourcePath = path.join(f.sourceRoot, 'photo1.jpg');
    const bytes = await readFile(sourcePath);
    await writeFile(sourcePath, Buffer.alloc(bytes.length));
    await utimes(sourcePath, 1700000000, 1700000000.123);
    const store = f.track(
      await ProjectStore.open(f.input.projectRoot, { processes }),
    );
    assert.equal(store.getIssue().code, 'SOURCE_CHECKSUM_CONFLICT');
    assert.ok(
      (await readdir(f.input.projectRoot)).includes('selector-journal-v1.json'),
    );
    await assert.rejects(store.execute('new-decision', { kind: 'skip' }), {
      code: 'PROJECT_FROZEN',
    });
    await writeFile(sourcePath, bytes);
    await utimes(sourcePath, 1700000000, 1700000000.123);
    await store.resume();
    assert.equal(store.getIssue(), null);
    assert.deepEqual(store.snapshot().decisions, proof.seed.decisions);
  });
});
function worker(...args) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        '--experimental-strip-types',
        fileURLToPath(new URL('./legacy-worker.mjs', import.meta.url)),
        ...args,
      ],
      { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] },
    );
    let stdout = '',
      stderr = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error('child fixture timeout'));
    }, 45000);
    child.stdout.on('data', (chunk) => {
      stdout += chunk;
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk;
    });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('exit', (code) => {
      clearTimeout(timer);
      resolve({ code, stdout, stderr });
    });
  });
}
describe('adoption actual process loss', { concurrency: 2 }, () => {
  for (const phase of ['import:copy', 'state:after', 'manifest:after'])
    test(`new process recovers lost import response at ${phase}`, async (t) => {
      const f = await legacyFixture(t);
      await twoCopies(f);
      const original = await originalProof(f);
      const crash = await worker(
        'crash',
        JSON.stringify(f.input),
        f.oldOutputRoot,
        phase,
      );
      assert.equal(crash.code, 73, crash.stderr);
      const recovery = await worker('recover', JSON.stringify(f.input));
      assert.equal(recovery.code, 0, recovery.stderr);
      const state = JSON.parse(recovery.stdout);
      assert.equal(state.decisions.length, 3);
      assert.equal(state.revision, 0);
      assert.equal(state.currentRelativePath, 'photo20.jpg');
      assert.deepEqual(await originalProof(f), original);
      const replay = await worker('recover', JSON.stringify(f.input));
      assert.equal(replay.code, 0, replay.stderr);
      assert.deepEqual(JSON.parse(replay.stdout), state);
    });
});
