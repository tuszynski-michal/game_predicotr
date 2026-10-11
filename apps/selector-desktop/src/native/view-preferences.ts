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
    const work = this.queue.then(async () => {
      const files = new SecureFiles(await ensureDirectory(this.directory));
      await files.verifyRoot();
      await files.replace(`${projectId}.json`, stableStringify(value));
    });
    this.queue = work.catch(() => {});
    return work;
  }
  flush(): Promise<void> {
    return this.queue;
  }
}
