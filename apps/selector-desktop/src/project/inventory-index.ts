import type { SourceInventoryItem } from './types.ts';
const indexes = new WeakMap<
  SourceInventoryItem[],
  ReadonlyMap<string, number>
>();
/** Inventories are immutable for the lifetime of a project. */
export function inventoryOrdinal(items: SourceInventoryItem[]) {
  let index = indexes.get(items);
  if (!index) {
    index = new Map(
      items.map((item, position) => [item.relativePath, position]),
    );
    indexes.set(items, index);
  }
  return index;
}
