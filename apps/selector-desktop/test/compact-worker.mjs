// A bounded fresh process proves that the persisted intent survives process exit.
import { ProjectStore } from '../src/project/project-store.ts';
import assert from 'node:assert/strict';
import { readFile, rename } from 'node:fs/promises';
import path from 'node:path';
import { PROJECT_JOURNAL_NAME } from '../src/project/state-codec.ts';

const [mode, projectRoot, point, ...extra] = process.argv.slice(2);
const checkpoint = (current) => {
  if (current === point) process.exit(73);
};
if (mode === 'upgrade-crash') {
  const store = await ProjectStore.open(projectRoot, { checkpoint });
  await store.close();
  process.exit(74);
} else if (mode === 'operation-crash') {
  const store = await ProjectStore.open(projectRoot, { checkpoint });
  await store.execute('compact-process-accept', {
    kind: 'accept',
    imagePath: 'photo1.jpg',
  });
  await store.close();
  process.exit(74);
} else if (mode === 'recover') {
  const store = await ProjectStore.open(projectRoot);
  if (store.getIssue()) throw new Error(JSON.stringify(store.getIssue()));
  const receipt = await store.execute('compact-process-accept', {
    kind: 'accept',
    imagePath: 'photo1.jpg',
  });
  process.stdout.write(JSON.stringify({ receipt, state: store.snapshot() }));
  await store.close();
} else if (mode === 'legacy-relink-retry' || mode === 'upgrade-relink-retry') {
  const operationId =
    mode === 'legacy-relink-retry'
      ? 'legacy-relink-0001'
      : 'upgrade-relink-0001';
  const relink = { kind: 'relink', sourceRoot: point, outputRoot: extra[0] };
  const store = await ProjectStore.open(projectRoot, {
    expectedSourceRoot: point,
  });
  assert.equal(store.getIssue(), null);
  const before = store.snapshot();
  const receipt = await store.execute(operationId, relink);
  assert.equal(
    before.revision,
    receipt.revision + (mode === 'legacy-relink-retry' ? 1 : 0),
  );
  assert.deepEqual(store.snapshot(), before);
  await assert.rejects(store.execute(operationId, { kind: 'skip' }), {
    code: 'OPERATION_ID_CONFLICT',
  });
  assert.deepEqual(store.snapshot(), before);
  process.stdout.write(JSON.stringify({ receipt, state: store.snapshot() }));
  await store.close();
} else if (mode === 'legacy-descriptor-resume-crash') {
  let failDescriptor = false;
  let crashInventory = false;
  const store = await ProjectStore.open(projectRoot, {
    checkpoint(current) {
      if (failDescriptor && current === `${PROJECT_JOURNAL_NAME}:replace`) {
        failDescriptor = false;
        throw Object.assign(new Error('upgrade descriptor disk full'), {
          code: 'ENOSPC',
        });
      }
      if (
        crashInventory &&
        /^upgrade:selector-inventory-[a-f0-9]{64}\.json:after$/.test(current)
      )
        process.exit(73);
    },
  });
  assert.equal(store.getIssue()?.code, 'SOURCE_MISSING');
  await rename(point, extra[0]);
  failDescriptor = true;
  await assert.rejects(store.resume(), { code: 'DISK_FULL' });
  assert.equal(failDescriptor, false);
  await assert.rejects(readFile(path.join(projectRoot, PROJECT_JOURNAL_NAME)), {
    code: 'ENOENT',
  });
  crashInventory = true;
  await store.resume();
  await store.close();
  process.exit(74);
} else {
  throw new Error('Unknown compact persistence worker mode');
}
