import { mkdir, stat, rename, appendFile, rm } from 'node:fs/promises';
import path from 'node:path';
export interface DiagnosticMetadata {
  attempt?: number;
  elapsedMs?: number;
}
export class DiagnosticLog {
  private queue: Promise<void> = Promise.resolve();
  readonly directory: string;
  private maxBytes: number;
  private copies: number;
  constructor(directory: string, maxBytes = 1024 * 1024, copies = 3) {
    this.directory = directory;
    this.maxBytes = maxBytes;
    this.copies = copies;
  }
  write(
    event: string,
    code?: string,
    metadata?: DiagnosticMetadata,
  ): Promise<void> {
    // Explicit numeric whitelist prevents paths, identities and arbitrary dumps.
    const safe: DiagnosticMetadata = {};
    if (metadata?.attempt === 1 || metadata?.attempt === 2)
      safe.attempt = metadata.attempt;
    if (
      typeof metadata?.elapsedMs === 'number' &&
      Number.isFinite(metadata.elapsedMs) &&
      metadata.elapsedMs >= 0
    )
      safe.elapsedMs = Math.min(Math.round(metadata.elapsedMs), 86400000);
    const work = this.queue.then(async () => {
      await mkdir(this.directory, { recursive: true });
      const file = path.join(this.directory, 'selector.log');
      const line =
        JSON.stringify({
          time: new Date().toISOString(),
          event: event.slice(0, 120),
          code: code?.slice(0, 80),
          ...safe,
        }) + '\n';
      const size = await stat(file).then(
        (s) => s.size,
        (e) => {
          if (e.code === 'ENOENT') return 0;
          throw e;
        },
      );
      if (size + Buffer.byteLength(line) > this.maxBytes) {
        await rm(`${file}.${this.copies}`, { force: true });
        for (let i = this.copies - 1; i >= 0; i--) {
          await rename(i ? `${file}.${i}` : file, `${file}.${i + 1}`).catch(
            (e) => {
              if (e.code !== 'ENOENT') throw e;
            },
          );
        }
      }
      await appendFile(file, line, 'utf8');
    });
    this.queue = work.catch(() => {});
    return work;
  }
}
