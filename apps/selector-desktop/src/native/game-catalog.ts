import { SelectorError, validateGameName } from '../contracts.ts';
import {
  ensureDirectory,
  SecureFiles,
  stableStringify,
} from '../filesystem/secure-files.ts';

const FILE_NAME = 'selector-games-v1.json';
const key = (name: string) => name.toLowerCase();

/** Durable user choices, independent of the optional recent-project cache. */
export class GameCatalog {
  private directory: string;
  private queue: Promise<unknown> = Promise.resolve();
  constructor(directory: string) {
    this.directory = directory;
  }
  private async read(files: SecureFiles): Promise<string[]> {
    const bytes = await files.read(FILE_NAME);
    if (!bytes) return [];
    try {
      const value = JSON.parse(bytes.toString());
      if (value.schemaVersion !== 1 || !Array.isArray(value.games))
        throw new Error('schema');
      const seen = new Set<string>();
      return value.games.map((name: unknown) => {
        const valid = validateGameName(name);
        if (valid !== name || seen.has(key(valid))) throw new Error('name');
        seen.add(key(valid));
        return valid;
      });
    } catch {
      throw new SelectorError(
        'GAME_CATALOG_CORRUPT',
        'Lista gier jest uszkodzona. Plik nie został nadpisany.',
      );
    }
  }
  private serial(work: () => Promise<string[]>): Promise<string[]> {
    const result = this.queue.then(work);
    this.queue = result.catch(() => {});
    return result;
  }
  list(): Promise<string[]> {
    return this.addMany([]);
  }
  add(name: unknown): Promise<string[]> {
    return this.addMany([validateGameName(name)]);
  }
  addMany(names: string[]): Promise<string[]> {
    return this.serial(async () => {
      const files = new SecureFiles(await ensureDirectory(this.directory));
      await files.verifyRoot();
      const games = await this.read(files);
      const seen = new Set(games.map(key));
      let changed = false;
      for (const name of names) {
        const valid = validateGameName(name);
        if (seen.has(key(valid))) continue;
        games.push(valid);
        seen.add(key(valid));
        changed = true;
      }
      if (changed)
        await files.replace(
          FILE_NAME,
          stableStringify({ schemaVersion: 1, games }),
        );
      return games.sort((a, b) => a.localeCompare(b, 'pl', { numeric: true }));
    });
  }
}
