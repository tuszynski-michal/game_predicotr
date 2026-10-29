import { mkdir, stat, rename, appendFile, rm } from 'node:fs/promises';
import path from 'node:path';
export interface DiagnosticMetadata {
  attempt?: number;
  elapsedMs?: number;
  count?: number;
  sampleCount?: number;
  median?: number;
  p95?: number;
  maximum?: number;
}
export type PerformanceMetric =
  'native-execute-ms' | 'execute-payload-bytes' | 'photo-open-ms';
/** Last 256 samples per fixed metric; no identities, paths or per-key writes. */
export class DiagnosticAggregates {
  private samples = new Map<
    PerformanceMetric,
    { count: number; values: number[] }
  >();
  record(metric: PerformanceMetric, value: number): void {
    if (!Number.isFinite(value) || value < 0) return;
    const entry = this.samples.get(metric) ?? { count: 0, values: [] };
    entry.count++;
    if (entry.values.length === 256) entry.values.shift();
    entry.values.push(Math.min(value, 1e12));
    this.samples.set(metric, entry);
  }
  snapshot(): { metric: PerformanceMetric; metadata: DiagnosticMetadata }[] {
    return [...this.samples].map(([metric, entry]) => {
      const values = [...entry.values].sort((a, b) => a - b);
      const percentile = (p: number) =>
        values[Math.ceil(values.length * p) - 1]!;
      return {
        metric,
        metadata: {
          count: entry.count,
          sampleCount: values.length,
          median: percentile(0.5),
          p95: percentile(0.95),
          maximum: values.at(-1)!,
        },
      };
    });
  }
  async flush(log: DiagnosticLog): Promise<void> {
    const batch = this.snapshot();
    this.samples.clear();
    // Observability never changes an operation's success/failure.
    await Promise.all(
      batch.map(({ metric, metadata }) =>
        log.write('performance-summary', metric, metadata).catch(() => {}),
      ),
    );
  }
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
    for (const key of [
      'count',
      'sampleCount',
      'median',
      'p95',
      'maximum',
    ] as const) {
      const value = metadata?.[key];
      if (typeof value === 'number' && Number.isFinite(value) && value >= 0)
        safe[key] = Math.min(value, key === 'sampleCount' ? 256 : 1e12);
    }
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
