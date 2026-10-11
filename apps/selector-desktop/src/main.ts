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
let window: BrowserWindow | null = null;
let log: DiagnosticLog;
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
  await window.loadURL(APP_URL);
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => {
    window?.restore();
    window?.focus();
  });
  app
    .whenReady()
    .then(async () => {
      log = new DiagnosticLog(path.join(app.getPath('userData'), 'logs'));
      await log.write('application-start');
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
      const handle = <T>(channel: string, run: () => Promise<T>) =>
        ipcMain.handle(
          channel,
          async (event, ...args: unknown[]): Promise<NativeResult<T>> => {
            try {
              validateSender(
                event.senderFrame?.url ?? '',
                event.senderFrame === event.sender.mainFrame,
                event.sender === window?.webContents,
              );
              validateNoArguments(args);
              return { ok: true, value: await run() };
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
      handle(CHANNELS.pickSource, async () => {
        const selected = await dialog.showOpenDialog(window!, {
          title: 'Wybierz katalog zdjęć JPEG',
          properties: ['openDirectory', 'dontAddToRecent'],
        });
        return selected.canceled || !selected.filePaths[0]
          ? null
          : registry.register(selected.filePaths[0]);
      });
      handle(CHANNELS.openLogs, async () => {
        await log.write('open-logs');
        const error = await shell.openPath(log.directory);
        if (error)
          throw new SelectorError(
            'OPEN_LOGS_FAILED',
            'Nie udało się otworzyć katalogu logów.',
          );
      });
      await createWindow();
    })
    .catch((error) => {
      void log?.write(
        'startup-failed',
        error instanceof SelectorError ? error.code : 'IO_ERROR',
      );
      dialog.showErrorBox(
        'Selektor zdjęć',
        'Aplikacja nie może się uruchomić. Sprawdź dostęp do lokalnego katalogu aplikacji.',
      );
      app.quit();
    });
}
app.on('window-all-closed', () => app.quit());
