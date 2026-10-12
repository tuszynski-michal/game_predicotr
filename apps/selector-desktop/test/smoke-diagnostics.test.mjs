import test from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdir,
  mkdtemp,
  writeFile,
  readFile,
  readdir,
  stat,
} from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  createOwnedSmoke,
  removeOwnedTemp,
  runSmokeChild,
} from '../scripts/release-support.mjs';

async function fixture() {
  const tempRoot = path.resolve('.tmp');
  await mkdir(tempRoot, { recursive: true });
  const outer = await mkdtemp(path.join(tempRoot, 'diagnostics-test-'));
  const owned = path.join(outer, 'fixtures');
  await mkdir(owned);
  const directory = await mkdtemp(path.join(owned, 'smoke-'));
  const userData = path.join(directory, 'user-data');
  await mkdir(path.join(userData, 'logs'), { recursive: true });
  await writeFile(
    path.join(userData, 'logs', 'selector.log'),
    'application-start\n',
  );
  await writeFile(
    path.join(userData, 'logs', 'selector.log.1'),
    'previous-run\n',
  );
  return {
    outer,
    tempRoot,
    directory,
    userData,
    owned,
    diagnosticsRoot: path.join(outer, 'proof'),
  };
}

test('failed smoke copies bounded logs and rotations before deleting its fixture', async () => {
  const f = await fixture();
  try {
    const smoke = createOwnedSmoke({
      name: 'fault',
      fixture: f.directory,
      tempRoot: f.owned,
      userData: [f.userData],
      diagnosticsRoot: f.diagnosticsRoot,
    });
    smoke.result.error = new Error(
      'Controlled diagnostic failure after application start',
    );
    await assert.rejects(smoke.finish(), /Smoke failed/);
    await assert.rejects(stat(f.directory), { code: 'ENOENT' });
    const [run] = await readdir(f.diagnosticsRoot);
    const proof = path.join(f.diagnosticsRoot, run);
    assert.equal(
      await readFile(path.join(proof, '0-selector.log'), 'utf8'),
      'application-start\n',
    );
    assert.equal(
      await readFile(path.join(proof, '0-selector.log.1'), 'utf8'),
      'previous-run\n',
    );
    const metadata = await readFile(path.join(proof, 'failure.json'), 'utf8');
    assert.equal(
      JSON.parse(metadata).failures[0].message,
      'Controlled diagnostic failure after application start',
    );
    assert.deepEqual(JSON.parse(metadata).logs, [
      '0-selector.log',
      '0-selector.log.1',
    ]);
  } finally {
    await removeOwnedTemp(f.outer, f.tempRoot);
  }
});

test('diagnostic failure reasons retain codes, redact encoded image data and stay bounded', async () => {
  const f = await fixture();
  try {
    const smoke = createOwnedSmoke({
      name: 'redaction',
      fixture: f.directory,
      tempRoot: f.owned,
      userData: [f.userData],
      diagnosticsRoot: f.diagnosticsRoot,
    });
    const error = new Error(
      `Launch failed: data:image/jpeg;base64,${'A'.repeat(300)} raw ${'B'.repeat(200)} <Buffer 01 02 ff> ${'detail '.repeat(1000)}`,
    );
    error.code = 'STARTUP_FAILED';
    smoke.result.error = error;
    await assert.rejects(smoke.finish(), /Smoke failed/);
    const [run] = await readdir(f.diagnosticsRoot);
    const { failures } = JSON.parse(
      await readFile(path.join(f.diagnosticsRoot, run, 'failure.json'), 'utf8'),
    );
    assert.equal(failures[0].code, 'STARTUP_FAILED');
    assert.match(failures[0].message, /^Launch failed:/);
    assert.equal(failures[0].message.includes('data:image'), false);
    assert.equal(failures[0].message.includes('A'.repeat(100)), false);
    assert.equal(failures[0].message.includes('B'.repeat(100)), false);
    assert.equal(failures[0].message.includes('01 02 ff'), false);
    assert.equal(failures[0].message.length, 1500);
    assert.equal(Object.hasOwn(failures[0], 'stack'), false);
  } finally {
    await removeOwnedTemp(f.outer, f.tempRoot);
  }
});

test('diagnostic capture failure retains the entire owned fixture', async () => {
  const f = await fixture();
  try {
    await writeFile(f.diagnosticsRoot, 'blocked directory');
    const smoke = createOwnedSmoke({
      name: 'capture-fault',
      fixture: f.directory,
      tempRoot: f.owned,
      userData: [f.userData],
      diagnosticsRoot: f.diagnosticsRoot,
    });
    smoke.result.error = new Error('failure');
    await assert.rejects(smoke.finish(), /could not be preserved/);
    assert.equal(
      await readFile(path.join(f.userData, 'logs', 'selector.log'), 'utf8'),
      'application-start\n',
    );
  } finally {
    await removeOwnedTemp(f.outer, f.tempRoot);
  }
});

test('explicit close and restart finalize successfully after Playwright destroys the connection', async () => {
  const f = await fixture();
  try {
    const smoke = createOwnedSmoke({
      name: 'close-restart',
      fixture: f.directory,
      tempRoot: f.owned,
      userData: [f.userData],
      diagnosticsRoot: f.diagnosticsRoot,
    });
    let closes = 0;
    const electron = {
      launch: async () => {
        let destroyed = false;
        const child = { pid: 0, exitCode: null, signalCode: null };
        return {
          process() {
            if (destroyed) throw new Error('Playwright connection destroyed');
            return child;
          },
          async close() {
            destroyed = true;
            child.exitCode = 0;
            closes++;
          },
        };
      },
    };
    const first = await smoke.launch(electron, {});
    await smoke.close(first);
    await smoke.close(first);
    const second = await smoke.launch(electron, {});
    await smoke.close(second);
    await assert.rejects(
      smoke.close({
        process() {
          throw new Error('Foreign process must not be read');
        },
      }),
      /unregistered/,
    );
    smoke.result.succeeded = true;
    await smoke.finish();
    assert.equal(closes, 2);
    await assert.rejects(stat(f.directory), { code: 'ENOENT' });
    await assert.rejects(stat(f.diagnosticsRoot), { code: 'ENOENT' });
  } finally {
    await removeOwnedTemp(f.outer, f.tempRoot);
  }
});

test('launch failure preserves startup logs and a successful smoke cleans without a failure artifact', async () => {
  const f = await fixture();
  try {
    const smoke = createOwnedSmoke({
      name: 'launch-fault',
      fixture: f.directory,
      tempRoot: f.owned,
      userData: [f.userData],
      diagnosticsRoot: f.diagnosticsRoot,
    });
    try {
      await smoke.run(() =>
        smoke.launch(
          {
            launch: async () => {
              throw new Error('launch failed');
            },
          },
          {},
        ),
      );
      smoke.result.succeeded = true;
    } catch (error) {
      smoke.result.error = error;
    }
    await assert.rejects(smoke.finish(), /Smoke failed/);
    assert.equal((await readdir(f.diagnosticsRoot)).length, 1);
    const second = await mkdtemp(path.join(f.owned, 'success-'));
    const success = createOwnedSmoke({
      name: 'success',
      fixture: second,
      tempRoot: f.owned,
      diagnosticsRoot: f.diagnosticsRoot,
    });
    success.result.succeeded = true;
    await success.finish();
    await assert.rejects(stat(second), { code: 'ENOENT' });
    assert.equal((await readdir(f.diagnosticsRoot)).length, 1);
  } finally {
    await removeOwnedTemp(f.outer, f.tempRoot);
  }
});

test('teardown failure also preserves evidence despite completed assertions', async () => {
  const f = await fixture();
  try {
    const smoke = createOwnedSmoke({
      name: 'teardown-fault',
      fixture: f.directory,
      tempRoot: f.owned,
      userData: [f.userData],
      diagnosticsRoot: f.diagnosticsRoot,
    });
    smoke.result.succeeded = true;
    await assert.rejects(
      smoke.finish({
        teardown: async () => {
          throw new Error('close failed');
        },
      }),
      /Smoke failed/,
    );
    assert.equal((await readdir(f.diagnosticsRoot)).length, 1);
    await assert.rejects(stat(f.directory), { code: 'ENOENT' });
  } finally {
    await removeOwnedTemp(f.outer, f.tempRoot);
  }
});

test('capture refuses userData outside its fixture and leaves unrelated bytes intact', async () => {
  const f = await fixture();
  try {
    const foreign = path.join(f.outer, 'operator-data');
    await mkdir(foreign);
    await writeFile(path.join(foreign, 'keep'), 'unchanged');
    const smoke = createOwnedSmoke({
      name: 'ownership-fault',
      fixture: f.directory,
      tempRoot: f.owned,
      userData: [foreign],
      diagnosticsRoot: f.diagnosticsRoot,
    });
    smoke.result.error = new Error('failure');
    await assert.rejects(smoke.finish(), /could not be preserved/);
    assert.equal(
      await readFile(path.join(foreign, 'keep'), 'utf8'),
      'unchanged',
    );
    assert.equal((await stat(f.directory)).isDirectory(), true);
  } finally {
    await removeOwnedTemp(f.outer, f.tempRoot);
  }
});

test('nested child unwinds its deadline and preserves evidence outside parent fixture', async () => {
  const f = await fixture();
  try {
    await assert.rejects(
      runSmokeChild(
        fileURLToPath(
          new URL('./fixtures/smoke-diagnostic-child.mjs', import.meta.url),
        ),
        [f.directory, f.owned, f.userData, f.diagnosticsRoot],
        { seconds: 1 },
      ),
      /exited/,
    );
    await assert.rejects(stat(f.directory), { code: 'ENOENT' });
    const [run] = await readdir(f.diagnosticsRoot);
    assert.equal(
      await readFile(
        path.join(f.diagnosticsRoot, run, '0-selector.log'),
        'utf8',
      ),
      'application-start\n',
    );
  } finally {
    await removeOwnedTemp(f.outer, f.tempRoot);
  }
});
