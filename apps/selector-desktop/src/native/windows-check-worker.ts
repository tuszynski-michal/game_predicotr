import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { StringDecoder } from 'node:string_decoder';
import { SelectorError } from '../contracts.ts';

type Check =
  | { op: 'driveInfo'; root: string }
  | { op: 'reparseScan'; paths: string[]; recursive: boolean }
  | { op: 'processIdentity'; pid: number };
type Result =
  | { type: number; ready: boolean }
  | { identity: string | null }
  | { clean: true };
const MAX_INPUT = 256 * 1024;
const MAX_OUTPUT = 16 * 1024;
// A fixed, read-only dispatcher. Neither paths nor process IDs become code.
const SCRIPT = `
$ErrorActionPreference='Stop'
$utf8=New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding=$utf8
[Console]::OutputEncoding=$utf8
while($null -ne ($line=[Console]::In.ReadLine())) {
  try {
    if($utf8.GetByteCount($line) -gt ${MAX_INPUT}) { exit 3 }
    $d=$line | ConvertFrom-Json
    if($d.version -ne 1 -or $d.id -isnot [string]) { exit 3 }
    $result=$null
    switch($d.op) {
      'driveInfo' {
        if($d.root -isnot [string] -or [string]::IsNullOrWhiteSpace($d.root)) { exit 3 }
        $drive=New-Object IO.DriveInfo($d.root)
        $result=@{type=[int]$drive.DriveType;ready=[bool]$drive.IsReady}
      }
      'reparseScan' {
        if($d.recursive -isnot [bool] -or @($d.paths).Count -gt 512) { exit 3 }
        foreach($p in $d.paths) {
          if($p -isnot [string] -or [string]::IsNullOrWhiteSpace($p)) { exit 3 }
          $item=Get-Item -LiteralPath $p -Force
          if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'REPARSE_POINT' }
          if($d.recursive) {
            Get-ChildItem -LiteralPath $p -Recurse -Force | ForEach-Object {
              if(($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'REPARSE_POINT' }
            }
          }
        }
        $result=@{clean=$true}
      }
      'processIdentity' {
        if($d.pid -lt 1 -or $d.pid -gt 2147483647 -or [math]::Floor($d.pid) -ne $d.pid) { exit 3 }
        $p=Get-CimInstance Win32_Process -Filter ('ProcessId = '+[int]$d.pid)
        if($null -eq $p) { $result=@{identity=$null} }
        else {
          if($null -eq $p.CreationDate) { throw 'PROCESS_UNKNOWN' }
          $result=@{identity=$p.CreationDate.ToUniversalTime().ToString('O')}
        }
      }
      default { exit 3 }
    }
    $response=@{version=1;id=$d.id;ok=$true;result=$result}
  } catch {
    $code='NATIVE_CHECK_FAILED'
    if($_.Exception.Message -eq 'REPARSE_POINT') { $code='REPARSE_POINT' }
    $response=@{version=1;id=$d.id;ok=$false;code=$code}
  }
  [Console]::Out.WriteLine(($response | ConvertTo-Json -Compress -Depth 4))
  [Console]::Out.Flush()
}
`;
const failure = (code = 'NATIVE_CHECK_FAILED') =>
  new SelectorError(code, 'Nie można potwierdzić natywnych kontroli systemu.');
interface Pending {
  id: string;
  check: Check;
  frame: string;
  resolve(value: Result): void;
  reject(error: unknown): void;
  timer: ReturnType<typeof setTimeout>;
}
export interface IdentityDiagnostic {
  attempt: 1 | 2;
  elapsedMs: number;
  code: string;
}
export interface CheckWorkerOptions {
  diagnostics?: (entry: IdentityDiagnostic) => void | Promise<void>;
  /** Native test seam; never exposed to IPC. Production uses the fixed dispatcher. */
  launch?: () => ChildProcessWithoutNullStreams;
  timeoutMs?: number;
  maxQueue?: number;
}
export class WindowsCheckWorker {
  private child: ChildProcessWithoutNullStreams | null = null;
  private retiring: Promise<void> = Promise.resolve();
  private queue: Pending[] = [];
  private active: Pending | null = null;
  private disposed = false;
  private starting = false;
  private spawnCount = 0;
  private readonly options: CheckWorkerOptions;
  private readonly children = new Set<ChildProcessWithoutNullStreams>();
  private readonly onExit = () => {
    for (const child of this.children) child.kill();
  };
  constructor(options: CheckWorkerOptions = {}) {
    this.options = options;
    process.once('exit', this.onExit);
  }
  stats() {
    return {
      spawnCount: this.spawnCount,
      pid: this.child?.pid ?? null,
      pending: this.queue.length + Number(Boolean(this.active)),
    };
  }
  async driveInfo(root: string): Promise<{ type: number; ready: boolean }> {
    return this.request({ op: 'driveInfo', root }) as Promise<{
      type: number;
      ready: boolean;
    }>;
  }
  async reparseScan(paths: string[], recursive: boolean): Promise<void> {
    await this.request({ op: 'reparseScan', paths: [...paths], recursive });
  }
  async processIdentity(pid: number): Promise<string | null> {
    for (const attempt of [1, 2] as const) {
      const started = performance.now();
      try {
        const result = (await this.request({ op: 'processIdentity', pid })) as {
          identity: string | null;
        };
        this.reportIdentity(attempt, started, 'NATIVE_CHECK_OK');
        return result.identity;
      } catch (error) {
        const code =
          error instanceof SelectorError ? error.code : 'NATIVE_CHECK_FAILED';
        this.reportIdentity(attempt, started, code);
        // A timeout is unknown, never evidence of a dead owner. The retirement
        // barrier must finish before the retry dispatches a new request.
        if (attempt === 2 || code !== 'NATIVE_CHECK_TIMEOUT') throw error;
      }
    }
    throw failure();
  }
  setDiagnostics(sink: CheckWorkerOptions['diagnostics']): void {
    this.options.diagnostics = sink;
  }
  private reportIdentity(attempt: 1 | 2, started: number, code: string): void {
    try {
      const result = this.options.diagnostics?.({
        attempt,
        elapsedMs: Math.max(0, Math.round(performance.now() - started)),
        code,
      });
      if (result) void result.catch(() => {});
    } catch {
      // Diagnostics cannot change ownership evidence or block the check.
    }
  }

  private request(check: Check): Promise<Result> {
    if (this.disposed) return Promise.reject(failure('NATIVE_CHECK_CLOSED'));
    if (
      (check.op === 'driveInfo' &&
        (typeof check.root !== 'string' ||
          !check.root ||
          check.root.includes('\0'))) ||
      (check.op === 'processIdentity' &&
        (!Number.isSafeInteger(check.pid) ||
          check.pid < 1 ||
          check.pid > 2147483647)) ||
      (check.op === 'reparseScan' &&
        (typeof check.recursive !== 'boolean' ||
          check.paths.length > 512 ||
          check.paths.some(
            (p) => typeof p !== 'string' || !p || p.includes('\0'),
          )))
    )
      return Promise.reject(failure('INVALID_ARGUMENT'));
    const id = randomUUID();
    const frame = `${JSON.stringify({ version: 1, id, ...check })}\n`;
    if (Buffer.byteLength(frame) > MAX_INPUT)
      return Promise.reject(failure('INVALID_ARGUMENT'));
    if (this.stats().pending >= (this.options.maxQueue ?? 64))
      return Promise.reject(failure('NATIVE_CHECK_BUSY'));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => this.abort(failure('NATIVE_CHECK_TIMEOUT')),
        this.options.timeoutMs ?? (check.op === 'reparseScan' ? 30000 : 10000),
      );
      this.queue.push({ id, check, frame, resolve, reject, timer });
      void this.pump();
    });
  }
  private async pump(): Promise<void> {
    if (this.starting || this.active || !this.queue.length || this.disposed)
      return;
    this.starting = true;
    try {
      await this.retiring;
      if (!this.queue.length || this.disposed) return;
      if (!this.child) this.start();
      this.active = this.queue.shift()!;
      this.refChild(true);
      this.child!.stdin.write(this.active.frame, (error) => {
        if (error) this.abort(failure());
      });
    } catch {
      this.abort(failure());
    } finally {
      this.starting = false;
    }
  }
  private refChild(ref: boolean): void {
    const child = this.child;
    if (!child) return;
    if (ref) child.ref();
    else child.unref();
    // Idle pipes must not keep a command/test alive. Node exit closes stdin;
    // the dispatcher also exits on EOF, with an explicit kill as a final guard.
    for (const stream of [child.stdin, child.stdout, child.stderr]) {
      const pipe = stream as typeof stream & {
        ref?: () => void;
        unref?: () => void;
      };
      if (ref) pipe.ref?.();
      else pipe.unref?.();
    }
  }
  private start(): void {
    const child =
      this.options.launch?.() ??
      spawn(
        'powershell.exe',
        [
          '-NoLogo',
          '-NoProfile',
          '-NonInteractive',
          '-EncodedCommand',
          Buffer.from(SCRIPT, 'utf16le').toString('base64'),
        ],
        { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] },
      );
    this.child = child;
    this.children.add(child);
    this.spawnCount++;
    const decoder = new StringDecoder('utf8');
    let output = '';
    let stderrBytes = 0;
    child.stdout.on('data', (chunk: Buffer) => {
      if (this.child !== child) return;
      output += decoder.write(chunk);
      if (Buffer.byteLength(output) > MAX_OUTPUT)
        return this.abort(failure('NATIVE_CHECK_PROTOCOL'));
      let newline;
      while ((newline = output.indexOf('\n')) >= 0) {
        const line = output
          .slice(0, newline)
          .replace(/^\uFEFF/, '')
          .trimEnd();
        output = output.slice(newline + 1);
        try {
          this.response(JSON.parse(line));
        } catch {
          this.abort(failure('NATIVE_CHECK_PROTOCOL'));
        }
        if (this.child !== child) return;
      }
    });
    child.stderr.on('data', (chunk: Buffer) => {
      stderrBytes += chunk.length;
      if (this.child === child && stderrBytes > MAX_OUTPUT)
        this.abort(failure('NATIVE_CHECK_PROTOCOL'));
    });
    child.stdin.on('error', () => {
      if (this.child === child) this.abort(failure());
    });
    child.on('error', () => {
      if (this.child === child) this.abort(failure());
    });
    child.on('close', () => {
      this.children.delete(child);
      if (this.child === child) this.abort(failure());
    });
  }
  private response(value: unknown): void {
    const v = value as Record<string, unknown>;
    const pending = this.active;
    if (
      !pending ||
      !v ||
      typeof v !== 'object' ||
      Array.isArray(v) ||
      v.version !== 1 ||
      v.id !== pending.id ||
      typeof v.ok !== 'boolean' ||
      Object.keys(v).sort().join(',') !==
        (v.ok ? 'id,ok,result,version' : 'code,id,ok,version')
    )
      throw failure();
    if (v.ok === false) {
      if (!['REPARSE_POINT', 'NATIVE_CHECK_FAILED'].includes(String(v.code)))
        throw failure();
      this.finish(pending, failure(String(v.code)));
      return;
    }
    const r = v.result as Record<string, unknown>;
    if (!r || typeof r !== 'object' || Array.isArray(r)) throw failure();
    if (
      pending.check.op === 'driveInfo' &&
      (Object.keys(r).sort().join(',') !== 'ready,type' ||
        !Number.isSafeInteger(r.type) ||
        Number(r.type) < 0 ||
        Number(r.type) > 6 ||
        typeof r.ready !== 'boolean')
    )
      throw failure();
    if (
      pending.check.op === 'reparseScan' &&
      (Object.keys(r).join(',') !== 'clean' || r.clean !== true)
    )
      throw failure();
    if (
      pending.check.op === 'processIdentity' &&
      (Object.keys(r).join(',') !== 'identity' ||
        (r.identity !== null &&
          (typeof r.identity !== 'string' ||
            !r.identity ||
            r.identity.length > 256)))
    )
      throw failure();
    this.finish(pending, null, r as Result);
  }
  private finish(pending: Pending, error: unknown, result?: Result): void {
    clearTimeout(pending.timer);
    this.active = null;
    if (error) pending.reject(error);
    else pending.resolve(result!);
    if (this.queue.length) void this.pump();
    else this.refChild(false);
  }
  private abort(error: unknown): void {
    const pending = [...(this.active ? [this.active] : []), ...this.queue];
    this.active = null;
    this.queue = [];
    for (const request of pending) {
      clearTimeout(request.timer);
      request.reject(error);
    }
    const child = this.child;
    this.child = null;
    if (!child) return;
    if (child.exitCode !== null || child.signalCode !== null) return;
    this.retiring = new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        child.kill();
        reject(failure('NATIVE_CHECK_SHUTDOWN_FAILED'));
      }, 2000);
      child.once('close', () => {
        clearTimeout(timer);
        resolve();
      });
      child.kill();
    });
    // Preserve a rejected retirement barrier (no replacement worker may start),
    // while avoiding an unhandled rejection before the next request/dispose.
    void this.retiring.catch(() => {});
  }
  async dispose(): Promise<void> {
    this.disposed = true;
    this.abort(failure('NATIVE_CHECK_CLOSED'));
    await this.retiring;
    process.removeListener('exit', this.onExit);
  }
}
let shared: WindowsCheckWorker | null = null;
export function nativeChecks(): WindowsCheckWorker {
  return (shared ??= new WindowsCheckWorker());
}
export async function disposeNativeChecks(): Promise<void> {
  const worker = shared;
  await worker?.dispose();
  if (shared === worker) shared = null;
}
