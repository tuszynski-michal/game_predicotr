import { MANUAL_IMAGE_NAVIGATION_STEPS } from '@game-predictor/manual-image-selection-core';
import {
  ensureDirectory,
  SecureFiles,
  stableStringify,
} from '../filesystem/secure-files.ts';
import { SelectorError, type ViewPreferences } from '../contracts.ts';
export const DEFAULT_VIEW: ViewPreferences = {
  navigationStep: 1,
  zoom: 100,
  scrollX: 0,
  scrollY: 0,
};
export function validateView(value: unknown): ViewPreferences {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new SelectorError('INVALID_ARGUMENT', 'Nieprawidłowy widok.');
  const v = value as ViewPreferences;
  if (
    Object.keys(v).sort().join(',') !== 'navigationStep,scrollX,scrollY,zoom' ||
    !MANUAL_IMAGE_NAVIGATION_STEPS.includes(v.navigationStep as 1) ||
    !Number.isFinite(v.zoom) ||
    v.zoom < 100 ||
    v.zoom > 3000 ||
    !Number.isFinite(v.scrollX) ||
    !Number.isFinite(v.scrollY) ||
    v.scrollX < 0 ||
    v.scrollY < 0 ||
    v.scrollX > 10000000 ||
    v.scrollY > 10000000
  )
    throw new SelectorError(
      'INVALID_ARGUMENT',
      'Nieprawidłowy krok, zoom lub przewijanie.',
    );
  return { ...v };
}
export function validateId(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(
      value,
    )
  )
    throw new SelectorError('INVALID_ARGUMENT', 'Nieprawidłowy identyfikator.');
  return value;
}
export class ViewPreferencesStore {
  private queue: Promise<void> = Promise.resolve();
  private pending = new Map<
    string,
    {
      value: ViewPreferences;
      promise: Promise<void>;
      resolve: () => void;
      reject: (error: unknown) => void;
    }
  >();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private directory: string;
  constructor(directory: string) {
    this.directory = directory;
  }
  async load(projectId: string): Promise<ViewPreferences> {
    validateId(projectId);
    await this.flush();
    try {
      const files = new SecureFiles(this.directory);
      await files.verifyRoot();
      const bytes = await files.read(`${projectId}.json`);
      if (!bytes || bytes.length > 4096) return { ...DEFAULT_VIEW };
      return validateView(JSON.parse(bytes.toString()));
    } catch {
      return { ...DEFAULT_VIEW };
    }
  }
  save(projectId: string, view: ViewPreferences): Promise<void> {
    validateId(projectId);
    const value = validateView(view);
    let entry = this.pending.get(projectId);
    if (entry) entry.value = value;
    else {
      let resolve!: () => void;
      let reject!: (error: unknown) => void;
      const promise = new Promise<void>((success, failure) => {
        resolve = success;
        reject = failure;
      });
      entry = { value, promise, resolve, reject };
      this.pending.set(projectId, entry);
    }
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      void this.flush().catch(() => {});
    }, 250);
    return entry.promise;
  }
  async flush(): Promise<void> {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    const batch = [...this.pending.entries()];
    this.pending.clear();
    const work = this.queue.then(async () => {
      for (const [projectId, entry] of batch) {
        try {
          const files = new SecureFiles(await ensureDirectory(this.directory));
          await files.verifyRoot();
          await files.replace(
            `${projectId}.json`,
            stableStringify(entry.value),
          );
          entry.resolve();
        } catch (error) {
          for (const [, waiting] of batch) waiting.reject(error);
          throw error;
        }
      }
    });
    this.queue = work.catch(() => {});
    await work;
  }
}
