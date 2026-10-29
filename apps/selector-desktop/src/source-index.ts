import type { SourceIndex, SourceImage } from './contracts.ts';

export interface SourceLookup {
  byId: ReadonlyMap<string, SourceImage>;
  byPath: ReadonlyMap<string, string>;
  ordinal: ReadonlyMap<string, number>;
}
const indexes = new WeakMap<SourceIndex, SourceLookup>();
/** One lookup per immutable bootstrap instance, independently in each process. */
export function sourceLookup(source: SourceIndex): SourceLookup {
  let index = indexes.get(source);
  if (!index) {
    const byId = new Map<string, SourceImage>();
    const byPath = new Map<string, string>();
    const ordinal = new Map<string, number>();
    source.images.forEach((image, position) => {
      byId.set(image.id, image);
      byPath.set(image.relativePath, image.id);
      ordinal.set(image.id, position);
    });
    index = { byId, byPath, ordinal };
    indexes.set(source, index);
  }
  return index;
}
