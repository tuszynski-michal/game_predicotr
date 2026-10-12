import { randomUUID } from 'node:crypto';
import { lstat, readdir, realpath, open } from 'node:fs/promises';
import path from 'node:path';
import { naturalCompare } from '@game-predictor/manual-image-selection-core';
import {
  SelectorError,
  type SourceIndex,
  type SourceImage,
} from '../contracts.ts';
import {
  assertNoLinks,
  assertWindowsReparse,
  safeExistingPath,
} from './path-security.ts';

export const MAX_SOURCE_IMAGES = 15000;
// A scan is transient native evidence, never reconstructed from persisted inventory.
export interface VerifiedSourceScan {
  readonly root: string;
  readonly index: SourceIndex;
  readonly dev: number;
  readonly ino: number;
}
const verifiedScans = new WeakSet<VerifiedSourceScan>();
export async function scanSource(
  directory: string,
): Promise<VerifiedSourceScan> {
  await assertNoLinks(directory);
  const root = await realpath(directory);
  await assertWindowsReparse([root], true);
  const rootStat = await lstat(root);
  if (!rootStat.isDirectory())
    throw new SelectorError('NOT_DIRECTORY', 'Wybierz katalog źródłowy.');
  const sourceId = randomUUID();
  const images: SourceImage[] = [];
  const pending = [''];
  let entriesSeen = 0;
  while (pending.length) {
    const prefix = pending.pop()!;
    const entries = await readdir(path.join(root, prefix), {
      withFileTypes: true,
    });
    for (const entry of entries) {
      if (++entriesSeen > 100000)
        throw new SelectorError(
          'SOURCE_TOO_LARGE',
          'Katalog zawiera zbyt wiele plików lub podkatalogów.',
        );
      const relativePath = prefix ? `${prefix}/${entry.name}` : entry.name;
      // Fail closed rather than silently omitting a linked subtree.
      const file = await safeExistingPath(root, relativePath, false);
      const stat = await lstat(file);
      if (stat.isDirectory()) {
        pending.push(relativePath);
        continue;
      }
      if (!stat.isFile() || !/\.jpe?g$/i.test(entry.name)) continue;
      if (images.length === MAX_SOURCE_IMAGES)
        throw new SelectorError(
          'SOURCE_TOO_LARGE',
          'Projekt obsługuje najwyżej 15 000 zdjęć JPEG.',
        );
      const id = randomUUID();
      images.push({
        id,
        relativePath,
        name: entry.name,
        size: stat.size,
        lastModified: stat.mtimeMs,
        url: `selector-photo://${sourceId}/${id}`,
      });
    }
  }
  images.sort(
    (a, b) =>
      naturalCompare(a.relativePath, b.relativePath) ||
      (a.relativePath < b.relativePath
        ? -1
        : a.relativePath > b.relativePath
          ? 1
          : 0),
  );
  const index = { id: sourceId, name: path.basename(root), images };
  const currentRoot = await lstat(root);
  if (rootStat.dev !== currentRoot.dev || rootStat.ino !== currentRoot.ino)
    throw new SelectorError(
      'SOURCE_CHANGED',
      'Katalog źródłowy zmienił tożsamość podczas sprawdzania.',
    );
  for (const image of images) Object.freeze(image);
  Object.freeze(images);
  Object.freeze(index);
  const scan = Object.freeze({
    root,
    index,
    dev: rootStat.dev,
    ino: rootStat.ino,
  });
  verifiedScans.add(scan);
  return scan;
}
export class SourceRegistry {
  private sources = new Map<
    string,
    { root: string; index: SourceIndex; byId: Map<string, SourceImage> }
  >();
  async register(directory: string): Promise<SourceIndex> {
    return this.registerVerifiedScan(await scanSource(directory));
  }
  async registerVerifiedScan(scan: VerifiedSourceScan): Promise<SourceIndex> {
    if (!verifiedScans.has(scan))
      throw new SelectorError(
        'SOURCE_IDENTITY_CONFLICT',
        'Indeks nie pochodzi ze zweryfikowanego skanu.',
      );
    await assertNoLinks(scan.root);
    const [root, stat] = await Promise.all([
      realpath(scan.root),
      lstat(scan.root),
    ]);
    if (root !== scan.root || stat.dev !== scan.dev || stat.ino !== scan.ino)
      throw new SelectorError(
        'SOURCE_CHANGED',
        'Katalog źródłowy zmienił tożsamość.',
      );
    const index = structuredClone(scan.index);
    this.sources.clear();
    this.sources.set(index.id, {
      root,
      index,
      byId: new Map(index.images.map((image) => [image.id, image])),
    });
    return structuredClone(index);
  }
  getRoot(sourceId: string): string {
    const source = this.sources.get(sourceId);
    if (!source)
      throw new SelectorError(
        'UNKNOWN_SOURCE',
        'Źródło nie jest zarejestrowane.',
      );
    return source.root;
  }
  async openImage(sourceId: string, imageId: string) {
    const source = this.sources.get(sourceId);
    const image = source?.byId.get(imageId);
    if (!source || !image)
      throw new SelectorError(
        'UNKNOWN_IMAGE',
        'Zdjęcie nie jest zarejestrowane.',
      );
    const file = await safeExistingPath(source.root, image.relativePath);
    const handle = await open(file, 'r');
    try {
      // Revalidate after opening and compare identity to detect replacement.
      await safeExistingPath(source.root, image.relativePath);
      const [opened, current] = await Promise.all([handle.stat(), lstat(file)]);
      if (
        !opened.isFile() ||
        opened.dev !== current.dev ||
        opened.ino !== current.ino ||
        opened.size !== image.size ||
        opened.mtimeMs !== image.lastModified
      )
        throw new SelectorError(
          'SOURCE_CHANGED',
          'Zdjęcie zmieniło się od wczytania źródła.',
        );
      return handle.createReadStream({ autoClose: true });
    } catch (error) {
      await handle.close();
      throw error;
    }
  }
}
