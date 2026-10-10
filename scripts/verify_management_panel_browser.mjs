import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const out = resolve('artifacts/management-panel-browser/browser');
const execute = promisify(execFile);
await mkdir(out, { recursive: true });
await writeFile(
  `${out}/mobile-result.json`,
  JSON.stringify({ passed: false, status: 'running' }),
);
const executable =
  process.env.MANAGEMENT_BROWSER_EXECUTABLE ??
  [
    `${process.env.PROGRAMFILES}/Google/Chrome/Application/chrome.exe`,
    `${process.env.LOCALAPPDATA}/Google/Chrome/Application/chrome.exe`,
    `${process.env['PROGRAMFILES(X86)']}/Microsoft/Edge/Application/msedge.exe`,
    `${process.env.PROGRAMFILES}/Microsoft/Edge/Application/msedge.exe`,
  ].find(existsSync);
if (!executable || !existsSync(executable))
  throw Error(
    'Chrome/Edge unavailable. Install/configure an existing browser via MANAGEMENT_BROWSER_EXECUTABLE; visual acceptance remains unverified.',
  );
const browser = spawn(
  executable,
  [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--remote-debugging-pipe',
    `--user-data-dir=${out}/profile-${Date.now()}`,
  ],
  { stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe'] },
);
let buffer = '',
  next = 0;
const waiting = new Map();
let browserFailure;
const rejectPending = (error) => {
  browserFailure = error;
  for (const callbacks of waiting.values()) callbacks.reject(error);
  waiting.clear();
};
browser.on('error', rejectPending);
browser.on('exit', () => rejectPending(Error('Acceptance browser exited')));
browser.stdio[3].on('error', rejectPending);
browser.stdio[4].on('error', rejectPending);
browser.stdio[4].on('data', (chunk) => {
  try {
    buffer += chunk;
    let i;
    while ((i = buffer.indexOf('\0')) >= 0) {
      const message = JSON.parse(buffer.slice(0, i));
      buffer = buffer.slice(i + 1);
      if (message.id) {
        const callbacks = waiting.get(message.id);
        waiting.delete(message.id);
        if (!callbacks) continue;
        message.error
          ? callbacks.reject(Error(JSON.stringify(message.error)))
          : callbacks.resolve(message.result);
      }
    }
  } catch (error) {
    rejectPending(error);
  }
});
const deadline = Date.now() + 110000;
const cdp = (method, params = {}, sessionId) =>
  new Promise((resolve, reject) => {
    if (browserFailure) {
      reject(browserFailure);
      return;
    }
    const id = ++next;
    const remaining =
      method === 'Browser.close'
        ? 15000
        : Math.min(15000, deadline - Date.now());
    if (remaining <= 0) {
      reject(Error('110s browser deadline'));
      return;
    }
    const timer = setTimeout(() => {
      waiting.delete(id);
      reject(Error(`Bounded CDP command timeout: ${method}`));
    }, remaining);
    waiting.set(id, {
      resolve: (result) => {
        clearTimeout(timer);
        resolve(result);
      },
      reject: (error) => {
        clearTimeout(timer);
        reject(error);
      },
    });
    browser.stdio[3].write(
      JSON.stringify({
        id,
        method,
        params,
        ...(sessionId ? { sessionId } : {}),
      }) + '\0',
    );
  });
let session;
const browserAlive = () =>
  browser.exitCode === null && browser.signalCode === null;
try {
  const target = await cdp('Target.createTarget', { url: 'about:blank' });
  session = (
    await cdp('Target.attachToTarget', {
      targetId: target.targetId,
      flatten: true,
    })
  ).sessionId;
  const send = (m, p) => cdp(m, p, session);
  await send('Page.enable');
  const cases = [
    [390, 'flow'],
    ...[390, 1440, 1920].flatMap((width) =>
      [1, 4, 40].map((count) => [width, String(count)]),
    ),
  ];
  const results = [];
  for (const [width, scenario] of cases) {
    await send('Emulation.setDeviceMetricsOverride', {
      width,
      height: width === 390 ? 844 : 1000,
      deviceScaleFactor: 1,
      mobile: width === 390,
    });
    await send('Emulation.setTouchEmulationEnabled', {
      enabled: true,
      maxTouchPoints: 1,
    });
    await send('Page.navigate', {
      url: `${pathToFileURL(`${out}/index.html`).href}?scenario=${scenario}`,
    });
    let result;
    let lastStage = '';
    while (Date.now() < deadline) {
      const value = await send('Runtime.evaluate', {
        expression:
          '({result:window.acceptanceResult,touch:window.touchRequest,stage:window.stageRequest,error:window.fixtureError})',
        returnByValue: true,
      });
      const state = value.result.value;
      if (state?.error) throw Error(`Fixture startup: ${state.error}`);
      if (state?.stage && state.stage !== lastStage) {
        lastStage = state.stage;
        const shot = await send('Page.captureScreenshot', {
          format: 'png',
          captureBeyondViewport: false,
        });
        await writeFile(
          `${out}/${lastStage}-${width}.png`,
          Buffer.from(shot.data, 'base64'),
        );
        await send('Runtime.evaluate', {
          expression: 'window.layoutResolve()',
        });
      }
      if (state?.result) {
        result = state.result;
        break;
      }
      if (state?.touch) {
        await send('Input.dispatchTouchEvent', {
          type: 'touchStart',
          touchPoints: [{ ...state.touch, radiusX: 1, radiusY: 1 }],
        });
        await send('Input.dispatchTouchEvent', {
          type: 'touchEnd',
          touchPoints: [],
        });
        await send('Runtime.evaluate', { expression: 'window.touchResolve()' });
      }
      await new Promise((r) => setTimeout(r, 40));
    }
    const sanity = await send('Runtime.evaluate', {
      expression:
        '({fontFamily:getComputedStyle(document.body).fontFamily,stylesheets:[...document.styleSheets].map(s=>s.href),touchEnabled:"ontouchstart" in window})',
      returnByValue: true,
    });
    if (result) result.sanity = sanity.result.value;
    if (
      !result?.sanity?.touchEnabled ||
      !result.sanity.stylesheets.length ||
      result.sanity.fontFamily.includes('Times New Roman')
    )
      throw Error('Real browser touch/style sanity failed');
    results.push({ width, scenario, ...result });
    await writeFile(
      `${out}/result-${scenario}-${width}.json`,
      JSON.stringify(results.at(-1), null, 2),
    );
    if (!result?.passed) throw Error(result?.error ?? 'Browser deadline');
  }
  await writeFile(
    `${out}/mobile-result.json`,
    JSON.stringify({ passed: true, results }, null, 2),
  );
  console.log(JSON.stringify({ passed: true, results }));
} catch (error) {
  await writeFile(
    `${out}/mobile-result.json`,
    JSON.stringify({ passed: false, error: String(error) }, null, 2),
  );
  throw error;
} finally {
  await cdp('Browser.close').catch(() => {});
  await new Promise((r) => setTimeout(r, 500));
  if (browserAlive()) {
    try {
      await execute('taskkill', ['/PID', String(browser.pid), '/T', '/F'], {
        timeout: 10000,
      });
    } catch (error) {
      for (let attempt = 0; attempt < 20 && browserAlive(); attempt += 1)
        await new Promise((r) => setTimeout(r, 100));
      if (browserAlive()) {
        await writeFile(
          `${out}/mobile-result.json`,
          JSON.stringify({
            passed: false,
            error: `Owned browser cleanup failed: ${String(error)}`,
          }),
        );
        throw error;
      }
    }
  }
}
