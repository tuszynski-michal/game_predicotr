import assert from 'node:assert/strict';
import { readFile, writeFile, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

const [configurationPath, version, phase] = process.argv.slice(2);
const config = JSON.parse(await readFile(configurationPath, 'utf8'));
if (!['baseline', 'current'].includes(version))
  throw new Error('Unknown version');
const root = path.join(config.runRoot, version);
const source = config.sources[version];
const { ProjectStore } = await import(
  pathToFileURL(path.join(source, 'project/project-store.ts'))
);
const { nativeChecks, disposeNativeChecks } = await import(
  pathToFileURL(path.join(source, 'native/windows-check-worker.ts'))
);
const { decodeEnvelope, PROJECT_JOURNAL_NAME } = await import(
  pathToFileURL(path.join(source, 'project/state-codec.ts'))
);
const checks = nativeChecks();
const samples = [];
let store;
let active = null;
let journalPeakBytes = 0;
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const quantiles = (values) => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return {
    count: sorted.length,
    p50Ms: sorted[Math.ceil(sorted.length * 0.5) - 1],
    p95Ms: sorted[Math.ceil(sorted.length * 0.95) - 1],
    maxMs: sorted.at(-1),
  };
};
async function metadata() {
  const entries = [];
  for (const name of (await readdir(path.join(root, 'project'))).sort()) {
    if (name === 'selector-project.lock') continue;
    const target = path.join(root, 'project', name);
    const info = await stat(target);
    if (!info.isFile()) continue;
    entries.push({
      name,
      bytes: info.size,
      mtimeMs: info.mtimeMs,
      sha256: hash(await readFile(target)),
    });
  }
  return entries;
}
const checkpoint = async (point) => {
  if (!active) return;
  const now = performance.now();
  active.checkpoints.push({ point, elapsedMs: now - active.started });
  if (point === 'prepare:after') {
    const info = await stat(path.join(root, 'project', PROJECT_JOURNAL_NAME));
    journalPeakBytes = Math.max(journalPeakBytes, info.size);
  }
};
const timed = async (operationId, command) => {
  active = {
    operationId,
    kind: command.kind,
    started: performance.now(),
    checkpoints: [],
  };
  const receipt = await store.execute(operationId, command);
  const elapsedMs = performance.now() - active.started;
  samples.push({
    operationId,
    kind: command.kind,
    elapsedMs,
    receipt,
    checkpoints: active.checkpoints,
  });
  active = null;
};
const projection = () =>
  typeof store.workspaceSnapshot === 'function'
    ? store.workspaceSnapshot()
    : store.snapshot();
try {
  const started = performance.now();
  if (phase === 'create')
    store = await ProjectStore.create(
      {
        sourceRoot: config.fixtureRoot,
        projectRoot: path.join(root, 'project'),
        outputRoot: path.join(root, 'output'),
        direction: 'ascending',
        firstLayout: 1,
        localStorageConfirmed: true,
      },
      { checkpoint },
    );
  else
    store = await ProjectStore.open(path.join(root, 'project'), { checkpoint });
  const openMs = performance.now() - started;
  assert.equal(store.getIssue(), null);
  const state = store.snapshot();
  assert.equal(state.inventory.length, 15000);
  assert.equal(state.inventory[0].relativePath, 'photo1.jpg');
  assert.equal(state.inventory[1].relativePath, 'photo2.jpg');
  assert.equal(state.inventory.at(-1).relativePath, 'photo15000.jpg');
  const before = await metadata();
  const warmStatsBefore = checks.stats();
  const result = {
    version,
    phase,
    nodePid: process.pid,
    openMs,
    revisionBefore: state.revision,
    warmStatsBefore,
  };
  if (phase === 'nav') {
    for (let i = 0; i < 20; i++)
      await timed(`measure_nav_${String(i).padStart(3, '0')}`, {
        kind: 'navigate',
        imagePath: `photo${i + 2}.jpg`,
      });
  } else if (phase === 'accept' || phase === 'skip') {
    let imagePath = state.currentRelativePath;
    for (let i = 0; i < 20; i++) {
      await timed(
        `measure_${phase}_${String(i).padStart(3, '0')}`,
        phase === 'accept' ? { kind: 'accept', imagePath } : { kind: 'skip' },
      );
      await timed(`measure_${phase}_undo_${String(i).padStart(3, '0')}`, {
        kind: 'undo',
      });
      imagePath = samples.at(-1).receipt.currentRelativePath;
    }
  } else if (phase === 'reopen') {
    assert.equal(Object.keys(state.receipts).length, 100);
    assert.equal(state.revision, 100);
    assert.equal(state.decisions.length, 0);
    const beforeRetry = state.revision;
    const startRetry = performance.now();
    const receipt = await store.execute('measure_nav_000', {
      kind: 'navigate',
      imagePath: 'photo2.jpg',
    });
    result.retryMs = performance.now() - startRetry;
    assert.deepEqual(receipt, state.receipts.measure_nav_000);
    assert.equal(projection().revision, beforeRetry);
    result.retainedReceiptCount = Object.keys(state.receipts).length;
    result.retryAfterUndoAndFreshProcess = true;
  } else if (phase === 'projection') {
    const { ProjectController } = await import(
      pathToFileURL(path.join(source, 'native/project-controller.ts'))
    );
    const { SourceRegistry } = await import(
      pathToFileURL(path.join(source, 'native/source-registry.ts'))
    );
    const controller = new ProjectController(
      path.join(root, 'measurement-user-data'),
      new SourceRegistry(),
      {},
    );
    // This measurement attaches the already-open owned store through native-only
    // TypeScript private fields; no dialogs, IPC or application lifecycle runs.
    controller.store = store;
    await controller.refreshSource();
    const controllerTimes = [],
      ipcTimes = [];
    let payloadBytes = 0;
    for (let i = 0; i < 20; i++) {
      let start = performance.now();
      const value = controller.snapshot();
      controllerTimes.push(performance.now() - start);
      assert.equal(value.source.images.length, 15000);
      start = performance.now();
      const payload = JSON.stringify(value);
      ipcTimes.push(performance.now() - start);
      payloadBytes = Buffer.byteLength(payload);
    }
    result.controllerWorkspaceProjectionTiming = quantiles(controllerTimes);
    result.workspaceJsonSerializationTiming = quantiles(ipcTimes);
    result.workspaceJsonPayloadBytes = payloadBytes;
  } else if (phase !== 'create') throw new Error('Unknown phase');
  result.warmStatsAfter = checks.stats();
  result.warmWorkerSpawnDelta =
    result.warmStatsAfter.spawnCount - warmStatsBefore.spawnCount;
  assert.equal(result.warmWorkerSpawnDelta, 0);
  const projectionTimes = [],
    snapshotTimes = [],
    previewTimes = [];
  for (let i = 0; i < 20; i++) {
    let start = performance.now();
    projection();
    projectionTimes.push(performance.now() - start);
    start = performance.now();
    store.snapshot();
    snapshotTimes.push(performance.now() - start);
    start = performance.now();
    const bytes = await readFile(path.join(config.fixtureRoot, 'photo21.jpg'));
    previewTimes.push(performance.now() - start);
    assert.equal(hash(bytes), config.jpegSha256);
  }
  const after = await metadata();
  const immutableBefore = before.filter((item) =>
    /selector-(inventory|baseline)-/.test(item.name),
  );
  const immutableAfter = after.filter((item) =>
    /selector-(inventory|baseline)-/.test(item.name),
  );
  if (version === 'current') {
    assert.equal(immutableBefore.length, 4);
    assert.deepEqual(immutableAfter, immutableBefore);
    result.immutableInventoryAndBaselineUnchanged = true;
    const headName = after.find(
      (item) => item.name === 'selector-project-v1.json',
    );
    const head = decodeEnvelope(
      await readFile(path.join(root, 'project', headName.name)),
    );
    assert.equal(head.schemaVersion, 2);
    result.diskSchema = head.schemaVersion;
  } else {
    const stateName = after.find(
      (item) => item.name === 'selector-project-v1.json',
    );
    const diskState = decodeEnvelope(
      await readFile(path.join(root, 'project', stateName.name)),
    );
    assert.equal(diskState.schemaVersion, 1);
    assert.equal(diskState.inventory.length, 15000);
    result.diskSchema = diskState.schemaVersion;
  }
  const phases = {};
  for (const sample of samples) {
    for (const entry of sample.checkpoints.filter((entry) =>
      entry.point.endsWith(':before'),
    )) {
      const end = sample.checkpoints.find(
        (candidate) =>
          candidate.point === entry.point.replace(/:before$/, ':after') &&
          candidate.elapsedMs >= entry.elapsedMs,
      );
      if (end)
        (phases[entry.point.slice(0, -7)] ??= []).push(
          end.elapsedMs - entry.elapsedMs,
        );
    }
  }
  Object.assign(result, {
    samples,
    operationTiming: quantiles(samples.map((sample) => sample.elapsedMs)),
    timingByKind: Object.fromEntries(
      [...new Set(samples.map((sample) => sample.kind))].map((kind) => [
        kind,
        quantiles(
          samples
            .filter((sample) => sample.kind === kind)
            .map((sample) => sample.elapsedMs),
        ),
      ]),
    ),
    checkpointTiming: Object.fromEntries(
      Object.entries(phases).map(([key, values]) => [key, quantiles(values)]),
    ),
    workspaceProjectionTiming: quantiles(projectionTimes),
    workspaceProjectionUsesFullSnapshot: version === 'baseline',
    publicSnapshotTiming: quantiles(snapshotTimes),
    previewFileReadTiming: quantiles(previewTimes),
    journalPeakBytes,
    metadataBefore: before,
    metadataAfter: after,
    metadataTotalBytes: after.reduce((total, item) => total + item.bytes, 0),
    revisionAfter: projection().revision,
    memory: process.memoryUsage(),
    nativeChecksAreProduction: true,
  });
  await writeFile(
    path.join(config.resultRoot, `${version}-${phase}.json`),
    `${JSON.stringify(result, null, 2)}\n`,
  );
  console.log(
    `${version} ${phase} PASS: ${samples.length} operations, open ${openMs.toFixed(1)}ms, p50 ${result.operationTiming?.p50Ms.toFixed(1) ?? '-'}ms, warm spawns ${result.warmWorkerSpawnDelta}`,
  );
} finally {
  await store?.close();
  await disposeNativeChecks();
}
