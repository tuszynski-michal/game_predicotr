import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import {
  lstat,
  realpath,
  rm,
  stat,
  mkdir,
  mkdtemp,
  copyFile,
  writeFile,
} from 'node:fs/promises';
import { execFileSync, spawn } from 'node:child_process';
import path from 'node:path';

export async function hashFile(file) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}

export function gitBuildInfo(root) {
  const git = (...args) =>
    execFileSync('git', args, {
      cwd: root,
      encoding: 'utf8',
      timeout: 10000,
      windowsHide: true,
    }).trim();
  const sourceCommit = git('rev-parse', 'HEAD');
  if (!/^[a-f0-9]{40}$/.test(sourceCommit))
    throw new Error('Invalid Git commit');
  return {
    sourceCommit,
    dirty: git('status', '--porcelain', '--untracked-files=normal') !== '',
    applicationSourceDirty:
      git(
        'status',
        '--porcelain',
        '--untracked-files=normal',
        '--',
        'apps/selector-desktop',
        'packages/manual-image-selection-core',
        'package.json',
        'package-lock.json',
      ) !== '',
    builtAt: new Date().toISOString(),
  };
}

export async function requireFreshArchive(file, makeStartedAt) {
  const details = await stat(file);
  if (
    !details.isFile() ||
    details.size === 0 ||
    details.mtimeMs < makeStartedAt
  )
    throw new Error('Forge did not produce a fresh nonempty ZIP');
  return details.size;
}

export async function removeOwnedTemp(directory, tempRoot) {
  if ((await lstat(tempRoot)).isSymbolicLink())
    throw new Error('Cleanup temporary root must not be a link');
  const root = await realpath(tempRoot);
  const target = path.resolve(directory);
  if (path.dirname(target) !== path.resolve(tempRoot))
    throw new Error(
      'Cleanup requires a direct child of the owned temporary root',
    );
  const details = await lstat(target);
  if (!details.isDirectory() || details.isSymbolicLink())
    throw new Error('Cleanup target is not an owned ordinary directory');
  const actual = await realpath(target);
  if (path.dirname(actual) !== root)
    throw new Error('Cleanup target escapes the owned temporary root');
  await rm(actual, {
    recursive: true,
    force: true,
    maxRetries: 10,
    retryDelay: 200,
  });
}

export async function boundedSmokeStep(action, milliseconds = 5000) {
  let timer;
  try {
    return await Promise.race([
      Promise.resolve().then(action),
      new Promise((_, reject) => {
        timer = setTimeout(
          () => reject(new Error('Smoke teardown timed out')),
          milliseconds,
        );
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

// Only handles returned by our launches or a verified fixture CDP session enter
// this registry. Never discover processes by executable name or global userData.
export function createOwnedSmoke({
  name,
  fixture,
  tempRoot,
  userData = [],
  diagnosticsRoot,
}) {
  const processes = new Map();
  const applications = new Map();
  const closedApplications = new Set();
  const launches = new Set();
  let finishing = false;
  const root =
    diagnosticsRoot ??
    process.env.SELECTOR_SMOKE_DIAGNOSTICS_ROOT ??
    path.resolve('../../artifacts/selector-smoke-diagnostics');
  const run = process.env.SELECTOR_SMOKE_RUN ?? `${Date.now()}-${process.pid}`;
  const result = { name, fixture, run, succeeded: false, error: null };
  return {
    result,
    async run(action) {
      const seconds = Number(
        process.env.SELECTOR_SMOKE_DEADLINE_SECONDS ?? 105,
      );
      return boundedSmokeStep(
        action,
        Math.min(Math.max(seconds, 1), 110) * 1000,
      );
    },
    registerProcess(child) {
      if (Number.isInteger(child?.pid) && child.pid > 0)
        processes.set(child.pid, child);
      return child;
    },
    registerPid(pid) {
      if (!Number.isInteger(pid) || pid <= 0)
        throw new Error('Invalid owned fixture PID');
      processes.set(pid, null);
    },
    async launch(electron, options) {
      if (finishing) throw new Error('Smoke is already finishing');
      const pending = electron.launch(options).then((application) => {
        const child = application.process();
        applications.set(application, child);
        this.registerProcess(child);
        return application;
      });
      launches.add(pending);
      try {
        const application = await pending;
        if (finishing)
          throw new Error('Smoke launch finished after its deadline');
        return application;
      } finally {
        launches.delete(pending);
      }
    },
    async close(application) {
      if (!application) return;
      if (closedApplications.has(application)) return;
      const child = applications.get(application);
      if (!child)
        throw new Error('Cannot close an unregistered smoke application');
      if (child.exitCode !== null || child.signalCode !== null) return;
      await boundedSmokeStep(() => application.close());
      closedApplications.add(application);
    },
    async finish({ teardown } = {}) {
      finishing = true;
      const failures = [];
      if (result.error) failures.push(result.error);
      if (!result.succeeded && !result.error)
        failures.push(new Error('Smoke did not complete'));
      // Await an already started Playwright launch before walking the registry.
      // Its existing launch timeout stays in force; no late process is missed.
      if (launches.size) {
        try {
          await boundedSmokeStep(
            () => Promise.allSettled([...launches]),
            25000,
          );
        } catch (error) {
          failures.push(error);
        }
      }
      if (teardown) {
        try {
          await boundedSmokeStep(teardown);
        } catch (error) {
          failures.push(error);
        }
      }
      for (const application of applications.keys()) {
        try {
          await this.close(application);
        } catch (error) {
          failures.push(error);
        }
      }
      for (const [pid, child] of processes) {
        if (child && (child.exitCode !== null || child.signalCode !== null))
          continue;
        try {
          if (!child) {
            // A CDP window close is graceful but process exit can trail it.
            await boundedSmokeStep(async () => {
              while (true) {
                try {
                  process.kill(pid, 0);
                } catch (error) {
                  if (error.code === 'ESRCH') return;
                  throw error;
                }
                await new Promise((resolve) => setTimeout(resolve, 50));
              }
            }, 2000).catch(() => {});
          }
          process.kill(pid, 0);
          failures.push(
            new Error('Owned fixture process required forced teardown'),
          );
          if (process.platform === 'win32') {
            execFileSync('taskkill.exe', ['/PID', String(pid), '/T', '/F'], {
              timeout: 5000,
              windowsHide: true,
              stdio: 'ignore',
            });
          } else process.kill(pid, 'SIGKILL');
          await boundedSmokeStep(async () => {
            while (true) {
              try {
                process.kill(pid, 0);
              } catch (error) {
                if (error.code === 'ESRCH') return;
                throw error;
              }
              await new Promise((resolve) => setTimeout(resolve, 50));
            }
          });
        } catch (error) {
          if (error.code !== 'ESRCH') failures.push(error);
        }
      }
      let diagnostics;
      if (failures.length) {
        // Capture must succeed before cleanup. If storage/read fails the entire
        // owned fixture is intentionally retained for manual inspection.
        try {
          diagnostics = await preserveSmokeDiagnostics({
            name,
            run,
            fixture,
            userData,
            diagnosticsRoot: root,
            failures,
            ownedPids: [...processes.keys()],
          });
          console.error(`Smoke diagnostics: ${diagnostics}`);
        } catch (error) {
          console.error(
            `Smoke diagnostics capture failed; fixture retained: ${fixture}`,
          );
          throw new AggregateError(
            [...failures, error],
            'Smoke failed and diagnostics could not be preserved',
          );
        }
      }
      // A live owned process can still write; never remove its fixture.
      const live = [...processes.keys()].some((pid) => {
        try {
          process.kill(pid, 0);
          return true;
        } catch {
          return false;
        }
      });
      if (!live) {
        try {
          await removeOwnedTemp(fixture, tempRoot);
        } catch (error) {
          failures.push(error);
          if (!diagnostics) {
            diagnostics = await preserveSmokeDiagnostics({
              name,
              run,
              fixture,
              userData,
              diagnosticsRoot: root,
              failures,
              ownedPids: [...processes.keys()],
            });
            console.error(`Smoke diagnostics: ${diagnostics}`);
          }
        }
      }
      if (failures.length)
        throw new AggregateError(
          failures,
          `Smoke failed; diagnostics: ${diagnostics}`,
        );
    },
  };
}

function diagnosticFailureMessage(error) {
  // Messages help identify the failed assertion/launch without saving stacks,
  // image data URLs, raw buffers or long base64 values from assertion dumps.
  return String(error?.message ?? '')
    .slice(0, 10000)
    .replace(/data:[^\s"'<>]+/gi, '[redacted data URL]')
    .replace(/<Buffer\s[^>]*>/gi, '[redacted buffer]')
    .replace(/[A-Za-z0-9+/]{100,}={0,2}/g, '[redacted encoded payload]')
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '')
    .slice(0, 1500);
}

export async function preserveSmokeDiagnostics({
  name,
  run,
  fixture,
  userData,
  diagnosticsRoot,
  failures,
  ownedPids = [],
}) {
  const root = path.resolve(diagnosticsRoot);
  const owned = await realpath(fixture);
  if (root === owned || root.startsWith(`${owned}${path.sep}`))
    throw new Error('Diagnostics must be outside the fixture');
  await mkdir(root, { recursive: true });
  if ((await lstat(root)).isSymbolicLink())
    throw new Error('Diagnostics root must not be a link');
  const actualRoot = await realpath(root);
  if (actualRoot === owned || actualRoot.startsWith(`${owned}${path.sep}`))
    throw new Error('Diagnostics root resolves inside the fixture');
  const directory = await mkdtemp(
    path.join(root, `${name.replace(/[^a-z0-9-]/gi, '-').slice(0, 60)}-`),
  );
  const logs = [];
  for (const [index, data] of userData.entries()) {
    const resolved = path.resolve(data);
    if (!resolved.startsWith(`${path.resolve(fixture)}${path.sep}`))
      throw new Error('Diagnostics userData must belong to the fixture');
    for (const suffix of ['', '.1', '.2', '.3']) {
      const file = path.join(resolved, 'logs', `selector.log${suffix}`);
      try {
        const details = await lstat(file);
        if (
          !details.isFile() ||
          details.isSymbolicLink() ||
          details.size > 2 * 1024 * 1024
        )
          throw new Error('Smoke log is not a bounded ordinary file');
        if (!(await realpath(file)).startsWith(`${owned}${path.sep}`))
          throw new Error('Smoke log escapes owned fixture');
        const output = `${index}-selector.log${suffix}`;
        await copyFile(file, path.join(directory, output));
        logs.push(output);
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
    }
  }
  await writeFile(
    path.join(directory, 'failure.json'),
    JSON.stringify(
      {
        name: name.slice(0, 80),
        run: String(run).slice(0, 120),
        time: new Date().toISOString(),
        fixture,
        logs,
        ownedPids,
        // Persist only a bounded, redacted reason; never exception stacks.
        failures: failures.slice(0, 12).map((error) => ({
          name: String(error.name ?? 'Error').slice(0, 80),
          message: diagnosticFailureMessage(error),
          code:
            typeof error.code === 'string'
              ? error.code.slice(0, 80)
              : undefined,
        })),
      },
      null,
      2,
    ) + '\n',
  );
  return directory;
}

export async function runSmokeChild(
  script,
  args,
  { seconds = 100, env = process.env } = {},
) {
  const child = spawn(process.execPath, [script, ...args], {
    stdio: 'inherit',
    windowsHide: true,
    env: { ...env, SELECTOR_SMOKE_DEADLINE_SECONDS: String(seconds) },
  });
  await new Promise((resolve, reject) => {
    let timedOut = false;
    // SIGINT is handled by the child to unwind its protected finally. Windows
    // cannot deliver it through child.kill, so the child has its own deadline.
    const timer = setTimeout(
      () => {
        timedOut = true;
        if (process.platform === 'win32')
          execFileSync(
            'taskkill.exe',
            ['/PID', String(child.pid), '/T', '/F'],
            { timeout: 5000, windowsHide: true, stdio: 'ignore' },
          );
        else child.kill('SIGKILL');
      },
      (seconds + 15) * 1000,
    );
    child.once('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once('close', (code) => {
      clearTimeout(timer);
      if (!timedOut && code === 0) resolve();
      else
        reject(
          new Error(
            timedOut
              ? 'Smoke child exceeded cleanup grace'
              : `Smoke child exited ${code}`,
          ),
        );
    });
  });
}
