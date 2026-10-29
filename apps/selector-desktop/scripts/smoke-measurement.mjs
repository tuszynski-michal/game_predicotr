import { _electron as electron } from 'playwright-core';
import electronExecutable from 'electron';
import assert from 'node:assert/strict';
import {
  mkdir,
  mkdtemp,
  copyFile,
  readFile,
  writeFile,
  readdir,
  stat,
} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { execFileSync } from 'node:child_process';
import { createOwnedSmoke, hashFile } from './release-support.mjs';
import { continueFromHistory } from './ui-smoke-support.mjs';

const tempRoot = path.resolve('.tmp');
await mkdir(tempRoot, { recursive: true });
const fixture = await mkdtemp(path.join(tempRoot, 'measurement-'));
const source = path.join(fixture, 'source');
const userData = path.join(fixture, 'user-data');
const smoke = createOwnedSmoke({
  name: 'smoke-measurement',
  fixture,
  tempRoot,
  userData: [userData],
});
const local = process.argv.includes('--local');
const executablePath = local
  ? electronExecutable
  : path.resolve(
      process.argv[2] ?? 'out/Selektor zdjec-win32-x64/Selektor-zdjec.exe',
    );
const reportPath = path.resolve(
  process.env.SELECTOR_MEASUREMENT_REPORT ??
    '../../artifacts/selector-fluency-20261029/measurement.json',
);
const report = {
  schemaVersion: 1,
  measuredAt: new Date().toISOString(),
  samples: {},
  limitations: [
    'Local controlled acceptance on copies, not recipient hardware.',
    'Cold application cache; OS cache was not cleared.',
    'Paint measured from captured keydown to first frame with visible target, then next animation frame: conservative rendering opportunity proxy, not photon latency.',
    'nativeExecute includes validation, write/flush and workspace projection; snapshotIPC measures real preload round trip, not execute alone.',
  ],
};
let application;
async function launch() {
  application = await smoke.launch(electron, {
    executablePath,
    args: [...(local ? ['.'] : []), `--user-data-dir=${userData}`],
    timeout: 20000,
  });
  const page = await application.firstWindow();
  page.setDefaultTimeout(10000);
  return page;
}
async function settled(page) {
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll('button')].find(
        (b) => b.textContent.trim() === 'Pomiń',
      )?.disabled === false,
  );
}
const summary = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  return {
    count: sorted.length,
    median: sorted[Math.ceil(sorted.length * 0.5) - 1],
    p95: sorted[Math.ceil(sorted.length * 0.95) - 1],
    maximum: sorted.at(-1),
  };
};
try {
  await smoke.run(async () => {
    await mkdir(source);
    const names = [
      'screen-a.jpg',
      'screen-b.jpg',
      'screen-c.jpg',
      'transition-d.jpg',
    ];
    for (let n = 0; n < 12; n++)
      await copyFile(
        path.resolve(
          '../../services/worker/tests/fixtures/range_ocr_real_v6',
          names[n % 4],
        ),
        path.join(source, `photo${String(n + 1).padStart(2, '0')}.jpg`),
      );
    let page = await launch();
    report.machine = {
      platform: os.platform(),
      release: os.release(),
      arch: os.arch(),
      cpu: os.cpus()[0]?.model,
      logicalCpus: os.cpus().length,
      memoryBytes: os.totalmem(),
      electron: await application.evaluate(() => process.versions.electron),
      applicationVersion: await application.evaluate(({ app }) =>
        app.getVersion(),
      ),
    };
    try {
      report.storageAndProtection = JSON.parse(
        execFileSync(
          'powershell.exe',
          [
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            '$ErrorActionPreference="Stop"; $d=Get-Partition -DriveLetter D | Get-Disk; $a=Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntivirusProduct; $m=Get-MpComputerStatus; @{disk=@($d|Select-Object FriendlyName,BusType,Size); protection=@($a|Select-Object displayName,productState); defender=($m|Select-Object AMProductVersion,AMEngineVersion,AntivirusSignatureVersion,RealTimeProtectionEnabled)}|ConvertTo-Json -Depth 4',
          ],
          { timeout: 10000, windowsHide: true, encoding: 'utf8' },
        ),
      );
    } catch {
      report.storageAndProtection = 'not verified: local read unavailable';
    }
    report.photos = [];
    for (const name of await readdir(source)) {
      const imagePath = path.join(source, name);
      const dimensions = await application.evaluate(
        ({ nativeImage }, imagePath) =>
          nativeImage.createFromPath(imagePath).getSize(),
        imagePath,
      );
      report.photos.push({
        ordinal: Number(name.match(/\d+/)[0]),
        bytes: (await stat(imagePath)).size,
        ...dimensions,
      });
    }
    await application.evaluate(({ dialog, ipcMain, session }, source) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [source],
      });
      globalThis.measurement = {
        nativeExecute: [],
        payloadBytes: [],
        photoRequests: 0,
        requestsByUrl: {},
        delayNext: false,
        responseReleased: false,
      };
      session.defaultSession.webRequest.onCompleted(
        { urls: ['selector-photo://*/*'] },
        ({ url }) => {
          globalThis.measurement.photoRequests++;
          globalThis.measurement.requestsByUrl[url] =
            (globalThis.measurement.requestsByUrl[url] ?? 0) + 1;
        },
      );
      const original = ipcMain._invokeHandlers.get('selector:execute');
      ipcMain.removeHandler('selector:execute');
      ipcMain.handle('selector:execute', async (...args) => {
        const t = performance.now();
        const result = await original(...args);
        globalThis.measurement.nativeExecute.push(performance.now() - t);
        globalThis.measurement.payloadBytes.push(
          Buffer.byteLength(JSON.stringify(result)),
        );
        if (globalThis.measurement.delayNext) {
          globalThis.measurement.delayNext = false;
          await new Promise((resolve) => setTimeout(resolve, 500));
          globalThis.measurement.responseReleased = true;
        }
        return result;
      });
    }, source);
    await page.evaluate(() => {
      window.measurement = {
        decode: [],
        paint: [],
        confirmation: [],
        snapshotIPC: [],
      };
      const decode = HTMLImageElement.prototype.decode;
      HTMLImageElement.prototype.decode = async function () {
        const t = performance.now();
        await decode.call(this);
        window.measurement.decode.push(performance.now() - t);
      };
    });
    await page
      .getByRole('button', { name: 'Wybierz folder zdjęć', exact: true })
      .click();
    await page.getByLabel('Nazwa gry', { exact: true }).fill('Measurement');
    await page.getByLabel('Aktualizacja', { exact: true }).fill('a1');
    await page.getByRole('button', { name: 'Rozpocznij wybieranie' }).click();
    await page.locator('.preview img').waitFor();
    await settled(page);
    const bootstrap = (await page.evaluate(() => window.selector.snapshot()))
      .value;
    await page.waitForFunction(() => window.measurement.decode.length >= 4);
    report.samples.coldDecode = await page.evaluate(() => [
      ...window.measurement.decode,
    ]);
    await page.locator('h1').click();
    // Arm capture before Playwright sends a real Chromium keyboard event.
    async function measureKey(key, target) {
      await page.evaluate((target) => {
        window.measuredPaint = null;
        document.addEventListener(
          'keydown',
          () => {
            const start = performance.now();
            const frame = () => {
              const image = document.querySelector('.preview img');
              if (
                image?.src === target &&
                image.getBoundingClientRect().width > 0
              ) {
                requestAnimationFrame(() => {
                  window.measuredPaint = performance.now() - start;
                });
              } else requestAnimationFrame(frame);
            };
            requestAnimationFrame(frame);
          },
          { once: true, capture: true },
        );
      }, target);
      await page.keyboard.press(key);
      await page.waitForFunction(() => window.measuredPaint !== null);
      return page.evaluate(() => window.measuredPaint);
    }
    const beforeRequests = await application.evaluate(() => ({
      total: globalThis.measurement.photoRequests,
      byUrl: { ...globalThis.measurement.requestsByUrl },
    }));
    for (let n = 0; n < 30; n++) {
      const index = n % 2 === 0 ? 1 : 0;
      const elapsed = await measureKey(
        index ? 'ArrowRight' : 'ArrowLeft',
        bootstrap.source.images[index].url,
      );
      (report.samples.warmPaint ??= []).push(elapsed);
      await settled(page);
      await page.evaluate(async () => {
        const t = performance.now();
        await window.selector.snapshot();
        window.measurement.snapshotIPC.push(performance.now() - t);
      });
    }
    const afterRequests = await application.evaluate(() => ({
      total: globalThis.measurement.photoRequests,
      byUrl: globalThis.measurement.requestsByUrl,
    }));
    report.warmProtocolRequests = afterRequests.total - beforeRequests.total;
    report.warmTargetProtocolRequests = bootstrap.source.images
      .slice(0, 2)
      .reduce(
        (sum, image) =>
          sum +
          (afterRequests.byUrl[image.url] ?? 0) -
          (beforeRequests.byUrl[image.url] ?? 0),
        0,
      );
    assert.equal(report.warmTargetProtocolRequests, 0);
    await application.evaluate(() => {
      globalThis.measurement.delayNext = true;
      globalThis.measurement.responseReleased = false;
    });
    report.delayedPaintMs = await measureKey(
      'ArrowRight',
      bootstrap.source.images[1].url,
    );
    report.paintedBeforeDelayedResponse = !(await application.evaluate(
      () => globalThis.measurement.responseReleased,
    ));
    assert.equal(report.paintedBeforeDelayedResponse, true);
    await settled(page);
    // Alternating opposite ends evicts the target outside ±3; cache of OS remains warm.
    await page.getByLabel('Skok', { exact: true }).selectOption('20');
    await page.locator('h1').click();
    report.samples.coldPaint = [];
    for (const index of [11, 0, 11, 0]) {
      report.samples.coldPaint.push(
        await measureKey(
          index ? 'ArrowRight' : 'ArrowLeft',
          bootstrap.source.images[index].url,
        ),
      );
      await settled(page);
    }
    await page.getByLabel('Skok', { exact: true }).selectOption('1');
    await page.locator('h1').click();
    await measureKey('ArrowRight', bootstrap.source.images[1].url);
    await settled(page);
    const accepted = [];
    for (let n = 0; n < 10; n++) {
      const state = (await page.evaluate(() => window.selector.snapshot()))
        .value;
      accepted.push({
        imageId: state.currentImageId,
        rangeStart: state.nextRangeStart,
      });
      await page.evaluate((count) => {
        window.measuredConfirmation = null;
        document.addEventListener(
          'keydown',
          () => {
            window.acceptStarted = performance.now();
            const observer = new MutationObserver(() => {
              if (
                document
                  .querySelector('[data-testid="counts"]')
                  ?.textContent.includes(`Wybrane: ${count} ·`)
              ) {
                observer.disconnect();
                requestAnimationFrame(() => {
                  window.measuredConfirmation =
                    performance.now() - window.acceptStarted;
                });
              }
            });
            observer.observe(document.querySelector('[data-testid="counts"]'), {
              subtree: true,
              childList: true,
              characterData: true,
            });
          },
          { once: true, capture: true },
        );
      }, n + 1);
      await page.keyboard.press(n % 2 ? 'Enter' : 'f');
      await page
        .getByTestId('counts')
        .filter({ hasText: `Wybrane: ${n + 1} ·` })
        .waitFor();
      (report.samples.acceptConfirmation ??= []).push(
        await page
          .waitForFunction(() => window.measuredConfirmation !== null)
          .then(() => page.evaluate(() => window.measuredConfirmation)),
      );
      await page.locator('.preview img').waitFor();
      await settled(page);
    }
    const renderer = await page.evaluate(() => window.measurement);
    report.samples.snapshotIPC = renderer.snapshotIPC;
    const native = await application.evaluate(() => globalThis.measurement);
    report.samples.nativeExecute = native.nativeExecute;
    report.samples.payloadBytes = native.payloadBytes;
    report.protocolRequests = native.photoRequests;
    await page
      .getByRole('button', { name: 'Zamknij projekt', exact: true })
      .click();
    await application.close();
    page = await launch();
    await continueFromHistory(page);
    await page
      .getByTestId('counts')
      .filter({ hasText: 'Wybrane: 10 ·' })
      .waitFor();
    await settled(page);
    const recovered = (await page.evaluate(() => window.selector.snapshot()))
      .value;
    assert.equal(recovered.acceptedCount, 10);
    assert.equal(recovered.nextRangeStart, 91);
    // Opaque source/image IDs are session scoped; durable identity is the verified relative path.
    assert.deepEqual(
      recovered.acceptedImageIds
        .map(
          (id) =>
            recovered.source.images.find((image) => image.id === id)
              .relativePath,
        )
        .sort(),
      accepted
        .map(
          (item) =>
            bootstrap.source.images.find((image) => image.id === item.imageId)
              .relativePath,
        )
        .sort(),
    );
    const output = path.join(fixture, 'Measurement a1 1-500000');
    const manifest = JSON.parse(
      await readFile(
        path.join(output, 'manual-image-selection-output-v1.json'),
        'utf8',
      ),
    );
    const decisions = manifest.decisions.filter(
      (item) => item.action === 'accepted',
    );
    assert.equal(decisions.length, 10);
    assert.deepEqual(
      decisions.map((item) => ({
        path: item.imagePath,
        start: item.rangeStart,
      })),
      accepted.map((item) => ({
        path: bootstrap.source.images.find((image) => image.id === item.imageId)
          .relativePath,
        start: item.rangeStart,
      })),
    );
    report.outputHashes = [];
    for (const item of accepted) {
      const image = bootstrap.source.images.find(
        (image) => image.id === item.imageId,
      );
      const hash = await hashFile(
        path.join(output, `seq_${item.rangeStart}-${item.rangeStart + 8}.jpg`),
      );
      assert.equal(hash, await hashFile(path.join(source, image.relativePath)));
      report.outputHashes.push({ rangeStart: item.rangeStart, sha256: hash });
    }
    report.recoveredChoices = 10;
    report.summaries = Object.fromEntries(
      Object.entries(report.samples).map(([key, values]) => [
        key,
        summary(values),
      ]),
    );
    report.warmTargetPassed = report.summaries.warmPaint.p95 <= 50;
    await mkdir(path.dirname(reportPath), { recursive: true });
    await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
    console.log(
      JSON.stringify(
        {
          reportPath,
          summaries: report.summaries,
          paintedBeforeDelayedResponse: report.paintedBeforeDelayedResponse,
          recoveredChoices: 10,
          warmTargetPassed: report.warmTargetPassed,
        },
        null,
        2,
      ),
    );
    assert.equal(
      report.warmTargetPassed,
      true,
      'Warm paint p95 exceeds 50 ms; retain every sample and investigate trace before proceeding',
    );
    await page
      .getByRole('button', { name: 'Zamknij projekt', exact: true })
      .click();
  });
  smoke.result.succeeded = true;
} catch (error) {
  smoke.result.error = error;
  report.failure = String(error);
  await mkdir(path.dirname(reportPath), { recursive: true });
  await writeFile(
    reportPath.replace(/\.json$/, `-failed-${Date.now()}.json`),
    JSON.stringify(report, null, 2) + '\n',
  );
} finally {
  await smoke.finish();
}
