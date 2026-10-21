// A real bounded child process is used for crash/recovery tests. No Electron,
// filesystem mock, service, or user corpus is involved.
import { ProjectStore } from '../src/project/project-store.ts';

const [mode, projectRoot, operationId, imagePath, phase] =
  process.argv.slice(2);
if (mode === 'range-crash' || mode === 'range-recover') {
  const store = await ProjectStore.open(projectRoot, {
    checkpoint(point) {
      if (mode === 'range-crash' && point === phase) process.exit(73);
    },
  });
  if (store.getIssue()) throw new Error(JSON.stringify(store.getIssue()));
  const receipt = await store.execute(operationId, {
    kind: 'range',
    start: 100,
    direction: 'descending',
  });
  process.stdout.write(JSON.stringify({ receipt, state: store.snapshot() }));
  await store.close();
} else if (mode === 'crash') {
  const store = await ProjectStore.open(projectRoot, {
    checkpoint(point) {
      if (point === phase) process.exit(73);
    },
  });
  await store.execute(operationId, { kind: 'accept', imagePath });
  process.exit(74);
} else if (mode === 'recover') {
  const store = await ProjectStore.open(projectRoot);
  if (store.getIssue()) throw new Error(JSON.stringify(store.getIssue()));
  const receipt = await store.execute(operationId, {
    kind: 'accept',
    imagePath,
  });
  process.stdout.write(JSON.stringify({ receipt, state: store.snapshot() }));
  await store.close();
} else if (mode === 'hold') {
  const store = await ProjectStore.open(projectRoot);
  process.stdout.write('LOCKED\n');
  const timer = setTimeout(async () => {
    await store.close();
    process.exit(0);
  }, 15000);
  process.on('SIGTERM', async () => {
    clearTimeout(timer);
    await store.close();
    process.exit(0);
  });
} else throw new Error('unknown test worker mode');
