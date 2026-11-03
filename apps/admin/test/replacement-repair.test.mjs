import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';
import {
  readFile,
  writeFile,
  mkdir,
  readdir,
  stat,
  mkdtemp,
  rm,
} from 'node:fs/promises';
import { join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { DiskDirectory } from './fixtures/replacement-disk-directory.mjs';
import {
  readReplacementRequest,
  writeReplacementPhoto,
  listReplacementSources,
  inspectReplacementOutput,
  assertSeparateReplacementDirectories,
  REPLACEMENT_REPAIR_NAME,
  authorizeReplacementWrite,
} from '../src/features/manual-image-selection/replacement-repair-storage.ts';
import {
  readActiveFilledGapsManifest,
  readRepairManifest,
} from '../src/features/manual-image-selection/manual-selection-repair-storage.ts';
import {
  replacementCanonicalJson,
  replacementRequestPayload,
} from '../../../packages/manual-image-selection-core/src/replacement-repair.ts';

const fixture = JSON.parse(
  await readFile(
    new URL(
      '../../../packages/admin-api-client/test/fixtures/source-replacement-request-v1.json',
      import.meta.url,
    ),
  ),
);
const jpeg = Buffer.from(
  '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDkaKKK8o/Sz//Z',
  'base64',
);
const handoff = 'manual-image-selection-filled-gaps-v1.json';
const sign = (request) => ({
  ...request,
  digest: createHash('sha256')
    .update(replacementCanonicalJson(replacementRequestPayload(request)))
    .digest('hex'),
});
function current(request = fixture) {
  return {
    id: request.batchId,
    gameId: request.gameId,
    revision: 999,
    entries: request.entries.map((entry) => {
      const range = request.allowedRanges.find(
        (row) => row.entryId === entry.entryId,
      );
      return {
        id: entry.entryId,
        revision: entry.revision,
        phase: 'gap_open',
        scopeDigest: entry.digest,
        sourceSha256: entry.sourceSha256,
        sequenceNumbers: entry.sequenceNumbers,
        rangeStart: range.sequenceStart,
        rangeEnd: range.sequenceEnd,
      };
    }),
  };
}
const api = (data = current()) => ({
  getSourceReplacementBatch: async () => ({ data }),
});

async function environment(t, hook) {
  // cwd is apps/admin, so the short output root stays in this worktree.
  const root = fileURLToPath(
    new URL('../../../artifacts/c1130/', import.meta.url),
  );
  await mkdir(root, { recursive: true });
  const temp = await mkdtemp(join(root, 'fs-'));
  t.after(async () => {
    const target = resolve(temp);
    assert.ok(target.startsWith(resolve(root) + sep));
    await rm(target, { recursive: true, force: true });
  });
  await mkdir(join(temp, 'source'));
  await mkdir(join(temp, 'output'));
  await writeFile(join(temp, 'source', 'seq_1-9.jpeg'), jpeg);
  const sourceDirectory = new DiskDirectory(
    join(temp, 'source'),
    undefined,
    true,
  );
  const output = new DiskDirectory(join(temp, 'output'), hook);
  return {
    sourceDirectory,
    output,
    request: fixture,
    source: (await listReplacementSources(sourceDirectory, fixture))[0],
    api: api(),
  };
}

test('actual exported digest is verified; tampered/planned/incomplete requests cannot prepare files', async () => {
  assert.deepEqual(await readReplacementRequest(fixture), fixture);
  await assert.rejects(
    readReplacementRequest({ ...fixture, digest: 'b'.repeat(64) }),
    /DIGEST_MISMATCH/,
  );
  await assert.rejects(
    readReplacementRequest({
      ...fixture,
      schemaVersion: 'source-replacement-manifest-v1',
    }),
    /INVALID_REQUEST/,
  );
});

test('new source listing keeps duplicate exact ranges for manual choice and skips unselected photos without reading or copying them', async (t) => {
  const input = await environment(t);
  await writeFile(join(input.sourceDirectory.path, 'seq_1-9.jpg'), jpeg);
  assert.equal(
    (await listReplacementSources(input.sourceDirectory, fixture)).length,
    2,
  );
  await writeFile(join(input.sourceDirectory.path, 'seq_10-18.jpg'), jpeg);
  assert.equal(
    (await listReplacementSources(input.sourceDirectory, fixture)).length,
    2,
  );
  await writeReplacementPhoto(input);
  assert.equal(
    (await readdir(input.output.path)).includes('seq_10-18.jpg'),
    false,
  );
  await assert.rejects(
    assertSeparateReplacementDirectories(
      input.sourceDirectory,
      input.sourceDirectory,
    ),
    /MUST_BE_SEPARATE/,
  );
  await assert.rejects(
    assertSeparateReplacementDirectories(
      new DiskDirectory(resolve(input.output.path, '..')),
      input.output,
    ),
    /MUST_BE_SEPARATE/,
  );
});

test('write produces original JPEG bytes, committed journal and unchanged handoff; lost response retries retain operation ID', async (t) => {
  const input = await environment(t);
  const saved = await writeReplacementPhoto(input);
  assert.deepEqual(
    await readFile(join(input.output.path, 'seq_1-9.jpg')),
    jpeg,
  );
  assert.equal(saved.journal[0].state, 'committed');
  const filled = await readActiveFilledGapsManifest(
    new DiskDirectory(input.output.path),
  );
  assert.equal(filled.entries[0].fillOperationId, saved.journal[0].id);
  assert.equal(filled.entries[0].sourcePath, 'seq_1-9.jpeg');
  assert.equal(filled.entries[0].entryId, undefined);
  const retry = await writeReplacementPhoto({
    ...input,
    api: {
      getSourceReplacementBatch: async () => {
        throw new Error('should not authorize a receipt');
      },
    },
  });
  assert.equal(retry.journal[0].id, saved.journal[0].id);
  await assert.rejects(readRepairManifest(input.output), /V3_REQUIRES/);
});

for (const point of ['intent', 'jpeg', 'commit', 'handoff']) {
  test(`fresh handles recover crash/lost response after persisted ${point} without changing operation identity`, async (t) => {
    let fired = false;
    const hook = (name, phase, bytes) => {
      const isCommit =
        name === REPLACEMENT_REPAIR_NAME &&
        bytes.toString().includes('"state": "committed"');
      const match =
        point === 'intent'
          ? name === REPLACEMENT_REPAIR_NAME && !isCommit
          : point === 'jpeg'
            ? name.endsWith('.jpg')
            : point === 'commit'
              ? isCommit
              : name === handoff &&
                bytes.toString().includes('fillOperationId');
      if (!fired && phase === 'after' && match) {
        fired = true;
        throw new Error(`crash-${point}`);
      }
    };
    const input = await environment(t, hook);
    await assert.rejects(writeReplacementPhoto(input), /crash-/);
    const before = JSON.parse(
      await readFile(join(input.output.path, REPLACEMENT_REPAIR_NAME)),
    );
    if (point === 'jpeg') {
      const code = `import {DiskDirectory} from ${JSON.stringify(new URL('./fixtures/replacement-disk-directory.mjs', import.meta.url).href)}; import {inspectReplacementOutput} from ${JSON.stringify(new URL('../src/features/manual-image-selection/replacement-repair-storage.ts', import.meta.url).href)}; const saved=await inspectReplacementOutput(new DiskDirectory(${JSON.stringify(input.output.path)})); console.log(saved.journal[0].id);`;
      const configPath = join(input.output.path, '..', 'child-tsconfig.json');
      await writeFile(
        configPath,
        JSON.stringify({
          compilerOptions: {
            paths: {
              '@game-predictor/manual-image-selection-core': [
                fileURLToPath(
                  new URL(
                    '../../../packages/manual-image-selection-core/src/index.ts',
                    import.meta.url,
                  ),
                ),
              ],
              '@game-predictor/manual-image-selection-core/*': [
                fileURLToPath(
                  new URL(
                    '../../../packages/manual-image-selection-core/src/*',
                    import.meta.url,
                  ),
                ),
              ],
            },
          },
        }),
      );
      const child = spawnSync(
        process.execPath,
        ['--import', 'tsx', '--input-type=module', '--eval', code],
        {
          encoding: 'utf8',
          timeout: 30_000,
          env: { ...process.env, TSX_TSCONFIG_PATH: configPath },
        },
      );
      assert.equal(child.status, 0, child.stderr);
      assert.equal(child.stdout.trim(), before.journal[0].id);
    }
    const fresh = new DiskDirectory(input.output.path);
    let recovered = await inspectReplacementOutput(fresh, fixture);
    if (point === 'intent') {
      assert.equal(recovered.journal[0].state, 'intent');
      assert.equal(
        JSON.parse(await readFile(join(fresh.path, handoff))).entries.length,
        0,
      );
      recovered = await writeReplacementPhoto({ ...input, output: fresh });
    }
    assert.equal(recovered.journal[0].state, 'committed');
    assert.equal(recovered.journal[0].id, before.journal[0].id);
    assert.equal(
      (await readActiveFilledGapsManifest(fresh)).entries[0].fillOperationId,
      before.journal[0].id,
    );
  });
}

test('changed/partial output and foreign files fail closed, never adopt or overwrite', async (t) => {
  const input = await environment(t);
  await writeFile(join(input.output.path, 'seq_1-9.jpg'), jpeg);
  await assert.rejects(writeReplacementPhoto(input), /FOREIGN_FILE/);
  assert.deepEqual(
    await readFile(join(input.output.path, 'seq_1-9.jpg')),
    jpeg,
  );
  await rm(join(input.output.path, 'seq_1-9.jpg'));
  const saved = await writeReplacementPhoto(input);
  await writeFile(join(input.output.path, 'seq_1-9.jpg'), jpeg.subarray(0, 50));
  await assert.rejects(
    inspectReplacementOutput(new DiskDirectory(input.output.path)),
    /FILE_CHANGED/,
  );
  assert.equal(
    JSON.parse(await readFile(join(input.output.path, REPLACEMENT_REPAIR_NAME)))
      .journal[0].id,
    saved.journal[0].id,
  );
});

test('missing API, stale own entry, retired SHA and invalid JPEG cannot write an intent', async (t) => {
  const input = await environment(t);
  for (const data of [
    null,
    { ...current(), id: 'other' },
    { ...current(), entries: [{ ...current().entries[0], revision: 300 }] },
  ])
    await assert.rejects(
      writeReplacementPhoto({ ...input, api: api(data) }),
      /CURRENT_API|ENTRY_STALE/,
    );
  assert.deepEqual(await readdir(input.output.path), []);
  const checksum = createHash('sha256').update(jpeg).digest('hex');
  const request = sign({
    ...fixture,
    entries: [{ ...fixture.entries[0], sourceSha256: checksum }],
  });
  await assert.rejects(
    writeReplacementPhoto({ ...input, request, api: api(current(request)) }),
    /RETIRED_SHA/,
  );
  await writeFile(join(input.sourceDirectory.path, 'seq_1-9.jpeg'), 'not jpeg');
  await assert.rejects(writeReplacementPhoto(input), /INVALID_JPEG/);
  assert.deepEqual(await readdir(input.output.path), []);
});

test('unrelated entry progress and global revision do not invalidate a remaining selected entry', async () => {
  const data = current();
  data.entries.push({ id: 'other', phase: 'restored', revision: 900 });
  data.revision = 10000;
  await authorizeReplacementWrite(
    api(data),
    fixture,
    fixture.entries[0].entryId,
  );
});

test('interruption before intent close never writes JPEG, and a partial pending JPEG is never overwritten', async (t) => {
  const beforeIntent = await environment(t, (name, phase) => {
    if (name === REPLACEMENT_REPAIR_NAME && phase === 'before')
      throw new Error('before-intent');
  });
  await assert.rejects(writeReplacementPhoto(beforeIntent), /before-intent/);
  assert.equal(
    (await readdir(beforeIntent.output.path)).some((name) =>
      name.endsWith('.jpg'),
    ),
    false,
  );
  const beforeJpeg = await environment(t, (name, phase) => {
    if (name.endsWith('.jpg') && phase === 'before')
      throw new Error('before-jpeg-close');
  });
  await assert.rejects(writeReplacementPhoto(beforeJpeg), /before-jpeg-close/);
  const target = join(beforeJpeg.output.path, 'seq_1-9.jpg');
  assert.equal((await readFile(target)).length, 0);
  await assert.rejects(
    writeReplacementPhoto({
      ...beforeJpeg,
      output: new DiskDirectory(beforeJpeg.output.path),
    }),
    /FILE_CHANGED/,
  );
  assert.equal((await readFile(target)).length, 0);
});

test('pending intent requires the original chosen bytes; a changed committed source cannot masquerade as a receipt', async (t) => {
  let fired = false;
  const input = await environment(t, (name, phase) => {
    if (!fired && name === REPLACEMENT_REPAIR_NAME && phase === 'after') {
      fired = true;
      throw new Error('intent-response-lost');
    }
  });
  await assert.rejects(writeReplacementPhoto(input), /intent-response-lost/);
  await writeFile(
    join(input.sourceDirectory.path, 'seq_1-9.jpeg'),
    Buffer.concat([
      jpeg.subarray(0, 2),
      Buffer.from('changed'),
      jpeg.subarray(2),
    ]),
  );
  await assert.rejects(
    writeReplacementPhoto({
      ...input,
      output: new DiskDirectory(input.output.path),
    }),
    /PENDING_SOURCE_REQUIRED/,
  );
  await writeFile(join(input.sourceDirectory.path, 'seq_1-9.jpeg'), jpeg);
  await writeReplacementPhoto({
    ...input,
    output: new DiskDirectory(input.output.path),
  });
  await writeFile(join(input.sourceDirectory.path, 'seq_1-9.jpeg'), 'changed');
  await assert.rejects(
    writeReplacementPhoto({
      ...input,
      output: new DiskDirectory(input.output.path),
    }),
    /ENTRY_ALREADY_PREPARED/,
  );
});

test('concurrent different requests for one output are serialized and the foreign owner loses without adoption', async (t) => {
  const input = await environment(t);
  const other = sign({
    ...fixture,
    batchId: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
  });
  const results = await Promise.allSettled([
    writeReplacementPhoto(input),
    writeReplacementPhoto({
      ...input,
      output: new DiskDirectory(input.output.path),
      request: other,
      api: api(current(other)),
    }),
  ]);
  assert.equal(
    results.filter((result) => result.status === 'fulfilled').length,
    1,
  );
  assert.match(
    results.find((result) => result.status === 'rejected').reason.message,
    /FOREIGN_MANIFEST/,
  );
  const saved = await inspectReplacementOutput(
    new DiskDirectory(input.output.path),
  );
  assert.equal(saved.request.batchId, fixture.batchId);
  assert.equal(saved.journal.length, 1);
});

test('foreign handoff ownership and entries fail closed while an owned stale subset is regenerated', async (t) => {
  const input = await environment(t);
  const saved = await writeReplacementPhoto(input);
  const path = join(input.output.path, handoff);
  const own = JSON.parse(await readFile(path));
  for (const foreign of [
    { ...own, repairKey: 'foreign' },
    {
      ...own,
      entries: [{ ...own.entries[0], fillOperationId: 'foreign-operation' }],
    },
    { ...own, entries: [own.entries[0], own.entries[0]] },
  ]) {
    await writeFile(path, JSON.stringify(foreign));
    await assert.rejects(
      inspectReplacementOutput(new DiskDirectory(input.output.path)),
      /FOREIGN_HANDOFF/,
    );
    assert.deepEqual(JSON.parse(await readFile(path)), foreign);
  }
  await writeFile(
    path,
    JSON.stringify({ ...own, repairRevision: 0, entries: [] }),
  );
  await inspectReplacementOutput(new DiskDirectory(input.output.path));
  assert.equal(
    JSON.parse(await readFile(path)).entries[0].fillOperationId,
    saved.journal[0].id,
  );
});

test('a public inspector holding an old snapshot cannot overwrite a newer writer journal', async (t) => {
  const input = await environment(t);
  const b = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
  const request = sign({
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
  await writeReplacementPhoto({
    ...input,
    request,
    api: api(current(request)),
  });
  await writeFile(join(input.sourceDirectory.path, 'seq_19-20.jpg'), jpeg);
  const source = (
    await listReplacementSources(input.sourceDirectory, request)
  ).find((row) => row.entryId === b);
  const slow = new DiskDirectory(input.output.path);
  const original = slow.getFileHandle.bind(slow);
  let release, started;
  const paused = new Promise((done) => {
    started = done;
  });
  const resume = new Promise((done) => {
    release = done;
  });
  let first = true;
  slow.getFileHandle = async (name, options) => {
    const handle = await original(name, options);
    if (first && name === REPLACEMENT_REPAIR_NAME) {
      first = false;
      const read = handle.getFile;
      handle.getFile = async () => {
        const value = await read();
        started();
        await resume;
        return value;
      };
    }
    return handle;
  };
  const inspection = inspectReplacementOutput(slow, request);
  await paused;
  let apiCalls = 0;
  const writing = writeReplacementPhoto({
    ...input,
    output: new DiskDirectory(input.output.path),
    request,
    source,
    api: {
      getSourceReplacementBatch: async () => {
        apiCalls++;
        return { data: current(request) };
      },
    },
  });
  await new Promise((done) => setTimeout(done, 10));
  assert.equal(
    apiCalls,
    0,
    'writer must wait for the mutating public inspector',
  );
  release();
  await Promise.all([inspection, writing]);
  const final = await inspectReplacementOutput(
    new DiskDirectory(input.output.path),
  );
  assert.equal(final.journal.length, 2);
  assert.equal(
    final.journal.every((write) => write.state === 'committed'),
    true,
  );
});

test('a known Chromium temporary file gets an explicit recovery error and is never adopted or removed', async (t) => {
  let fired = false;
  const input = await environment(t, (name, phase) => {
    if (!fired && name === REPLACEMENT_REPAIR_NAME && phase === 'after') {
      fired = true;
      throw new Error('after-intent');
    }
  });
  await assert.rejects(writeReplacementPhoto(input), /after-intent/);
  const path = join(input.output.path, 'seq_1-9.jpg.crswap');
  await writeFile(path, jpeg.subarray(0, 100));
  await assert.rejects(
    inspectReplacementOutput(new DiskDirectory(input.output.path)),
    /TEMPORARY_WRITE_REMAINS/,
  );
  assert.deepEqual(await readFile(path), jpeg.subarray(0, 100));
  assert.equal(
    (await readdir(input.output.path)).includes('seq_1-9.jpg'),
    false,
  );
});

test('the unchanged crop handoff reader works with a read-only v3 directory and never commits an intent', async (t) => {
  const input = await environment(t);
  const saved = await writeReplacementPhoto(input);
  const path = join(input.output.path, REPLACEMENT_REPAIR_NAME);
  const before = await readFile(path);
  const beforeMtime = (await stat(path)).mtimeMs;
  const readonly = new DiskDirectory(input.output.path, undefined, true);
  assert.equal(
    (await readActiveFilledGapsManifest(readonly)).entries[0].fillOperationId,
    saved.journal[0].id,
  );
  assert.deepEqual(await readFile(path), before);
  assert.equal((await stat(path)).mtimeMs, beforeMtime);
  await rm(join(input.output.path, handoff));
  assert.equal(
    (await readActiveFilledGapsManifest(readonly)).entries.length,
    1,
  );
  assert.equal(
    (await readdir(input.output.path)).includes(handoff),
    false,
    'a derived readonly handoff is not materialized',
  );
  await writeFile(
    path,
    JSON.stringify({
      ...saved,
      journal: [{ ...saved.journal[0], state: 'intent' }],
    }),
  );
  assert.equal(
    (await readActiveFilledGapsManifest(readonly)).entries.length,
    0,
  );
  assert.equal(JSON.parse(await readFile(path)).journal[0].state, 'intent');
  assert.equal(readonly.writes, 0);
});
