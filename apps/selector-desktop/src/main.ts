import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  protocol,
  session,
  shell,
  Menu,
} from 'electron';
import { readFile } from 'node:fs/promises';
import { Readable } from 'node:stream';
import path from 'node:path';
import {
  APP_URL,
  CHANNELS,
  SelectorError,
  parsePhotoUrl,
  validateSender,
  validateNoArguments,
  type NativeResult,
} from './contracts.ts';
import { SourceRegistry } from './native/source-registry.ts';
import { DiagnosticLog } from './native/diagnostic-log.ts';
import { ProjectController } from './native/project-controller.ts';
import { disposeNativeChecks } from './native/windows-check-worker.ts';
import { DesktopLifecycle } from './native/desktop-lifecycle.ts';

// Standard Chromium/Electron switch also isolates native project/view caches.
// It is a process-launch option, never a renderer filesystem capability.
const userDataOverride = app.commandLine.getSwitchValue('user-data-dir');
if (userDataOverride) app.setPath('userData', path.resolve(userDataOverride));

protocol.registerSchemesAsPrivileged([
  {
    scheme: 'selector',
    privileges: { standard: true, secure: true, supportFetchAPI: true },
  },
  {
    scheme: 'selector-photo',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,
    },
  },
]);
const registry = new SourceRegistry();
const lifecycle = new DesktopLifecycle();
let window: BrowserWindow | null = null;
let log: DiagnosticLog;
let controller: ProjectController;
const CSP =
  "default-src 'none'; script-src 'self'; style-src 'self'; img-src selector-photo:; connect-src 'none'; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'";

async function createWindow() {
  window = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 760,
    minHeight: 600,
    title: 'Selektor zdjęć',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
      spellcheck: false,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event) => event.preventDefault());
  window.webContents.on('will-redirect', (event) => event.preventDefault());
  window.webContents.on('will-attach-webview', (event) =>
    event.preventDefault(),
  );
  window.on('closed', () => {
    window = null;
  });
  let closing = false;
  let closingRequested = false;
  window.on('close', (event) => {
    if (closing) return;
    event.preventDefault();
    if (closingRequested) return;
    closingRequested = true;
    lifecycle.beginClosing();
    void (async () => {
      try {
        await controller.close();
        const issue = controller.getCloseIssue();
        if (issue) await log.write('project-close-issue', issue.code);
      } catch (error) {
        await log.write(
          'project-close-failed',
          error instanceof SelectorError ? error.code : 'IO_ERROR',
        );
      } finally {
        try {
          await disposeNativeChecks();
        } catch {
          await log.write('native-checks-dispose-failed', 'IO_ERROR');
        } finally {
          closing = true;
          window?.close();
        }
      }
    })().catch(() => {
      closing = true;
      window?.close();
    });
  });
  await window.loadURL(APP_URL);
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => {
    const action = lifecycle.secondInstance();
    if (action === 'relaunch') {
      // Electron defers the new process until this process has exited.
      app.relaunch({ args: process.argv.slice(1) });
      return;
    }
    if (action === 'pending') return;
    window?.restore();
    window?.focus();
  });
  app
    .whenReady()
    .then(async () => {
      log = new DiagnosticLog(path.join(app.getPath('userData'), 'logs'));
      await log.write('application-start');
      controller = new ProjectController(app.getPath('userData'), registry, {
        directory: async (title, defaultPath) => {
          const result = await dialog.showOpenDialog(window!, {
            title,
            defaultPath,
            properties: ['openDirectory', 'createDirectory', 'dontAddToRecent'],
          });
          return result.canceled ? null : (result.filePaths[0] ?? null);
        },
        confirm: async (message, confirmLabel) =>
          (
            await dialog.showMessageBox(window!, {
              type: 'question',
              message,
              buttons: ['Anuluj', confirmLabel ?? 'Potwierdź'],
              defaultId: 0,
              cancelId: 0,
            })
          ).response === 1,
        openFolder: async (directory) => {
          if (await shell.openPath(directory))
            throw new SelectorError(
              'OPEN_FOLDER_FAILED',
              'Nie udało się otworzyć katalogu.',
            );
        },
      });
      Menu.setApplicationMenu(null);
      session.defaultSession.setPermissionRequestHandler(
        (_contents, _permission, callback) => callback(false),
      );
      session.defaultSession.setPermissionCheckHandler(() => false);
      session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
        callback({
          cancel:
            !details.url.startsWith('selector://app/') &&
            !details.url.startsWith('selector-photo://'),
        });
      });
      protocol.handle('selector', async (request) => {
        const files: Record<string, [string, string]> = {
          'selector://app/index.html': [
            'index.html',
            'text/html; charset=utf-8',
          ],
          'selector://app/app.js': ['app.js', 'text/javascript; charset=utf-8'],
          'selector://app/app.css': ['app.css', 'text/css; charset=utf-8'],
        };
        const file = files[request.url];
        if (!file || request.method !== 'GET')
          return new Response(null, { status: 404 });
        return new Response(
          await readFile(path.join(__dirname, 'renderer', file[0])),
          {
            headers: {
              'Content-Type': file[1],
              'Content-Security-Policy': CSP,
              'X-Content-Type-Options': 'nosniff',
            },
          },
        );
      });
      protocol.handle('selector-photo', async (request) => {
        try {
          if (request.method !== 'GET')
            return new Response(null, { status: 405 });
          const { sourceId, imageId } = parsePhotoUrl(request.url);
          const stream = await registry.openImage(sourceId, imageId);
          return new Response(
            Readable.toWeb(stream) as ReadableStream<Uint8Array>,
            {
              headers: {
                'Content-Type': 'image/jpeg',
                'Cache-Control': 'no-store',
                'X-Content-Type-Options': 'nosniff',
              },
            },
          );
        } catch (error) {
          await log.write(
            'photo-read-failed',
            error instanceof SelectorError ? error.code : 'IO_ERROR',
          );
          return new Response(null, { status: 403 });
        }
      });
      const handle = <T>(
        channel: string,
        run: (...args: unknown[]) => Promise<T> | T,
        count = 0,
      ) =>
        ipcMain.handle(
          channel,
          async (event, ...args: unknown[]): Promise<NativeResult<T>> => {
            try {
              validateSender(
                event.senderFrame?.url ?? '',
                event.senderFrame === event.sender.mainFrame,
                event.sender === window?.webContents,
              );
              if (count === 0) validateNoArguments(args);
              else if (args.length !== count)
                throw new SelectorError(
                  'INVALID_ARGUMENT',
                  'Nieprawidłowa liczba argumentów.',
                );
              return { ok: true, value: await run(...args) };
            } catch (error) {
              const code =
                error instanceof SelectorError ? error.code : 'IO_ERROR';
              await log.write('command-failed', code);
              return {
                ok: false,
                error: {
                  code,
                  message:
                    error instanceof SelectorError
                      ? error.message
                      : 'Operacja lokalna nie powiodła się. Sprawdź dostęp do katalogu i logi.',
                },
              };
            }
          },
        );
      handle(CHANNELS.openLogs, async () => {
        await log.write('open-logs');
        const error = await shell.openPath(log.directory);
        if (error)
          throw new SelectorError(
            'OPEN_LOGS_FAILED',
            'Nie udało się otworzyć katalogu logów.',
          );
      });
      handle(CHANNELS.create, (options) => controller.create(options), 1);
      handle(CHANNELS.begin, () => controller.begin());
      handle(CHANNELS.legacyPreview, () => controller.legacyPreview());
      handle(CHANNELS.legacyAdopt, (token) => controller.legacyAdopt(token), 1);
      handle(CHANNELS.open, () => controller.open());
      handle(CHANNELS.recent, () => controller.recent());
      handle(CHANNELS.continue, (projectId) => controller.open(projectId), 1);
      handle(CHANNELS.snapshot, () => controller.snapshot());
      handle(CHANNELS.execute, (request) => controller.execute(request), 1);
      handle(CHANNELS.resume, () => controller.resume());
      handle(CHANNELS.relink, (kind) => controller.relink(kind), 1);
      handle(CHANNELS.restartPreview, () => controller.previewRestart());
      handle(
        CHANNELS.saveView,
        (projectId, view) => controller.saveView(projectId, view),
        2,
      );
      handle(CHANNELS.close, async () => {
        await controller.close();
        const issue = controller.getCloseIssue();
        if (issue) await log.write('project-close-issue', issue.code);
      });
      handle(CHANNELS.openOutput, () => controller.openOutput());
      handle(CHANNELS.fullscreen, () => {
        window!.setFullScreen(!window!.isFullScreen());
        return window!.isFullScreen();
      });
      await createWindow();
    })
    .catch(async (error) => {
      void log?.write(
        'startup-failed',
        error instanceof SelectorError ? error.code : 'IO_ERROR',
      );
      dialog.showErrorBox(
        'Selektor zdjęć',
        'Aplikacja nie może się uruchomić. Sprawdź dostęp do lokalnego katalogu aplikacji.',
      );
      try {
        await disposeNativeChecks();
      } finally {
        app.quit();
      }
    });
}
app.on('window-all-closed', () => app.quit());
