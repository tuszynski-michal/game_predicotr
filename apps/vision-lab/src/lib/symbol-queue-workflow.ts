import type {
  DictionaryView,
  LabQueuePreview,
  SymbolRequest,
} from '../../../../packages/vision-lab-api-client/src/index';

export const MAX_QUEUE_ASSIGNMENT = 30;

export function queueSourceCaption(sourceName: string): string {
  const filename = sourceName.split(/[\\/]/).at(-1) || sourceName;
  return filename.length > 24
    ? `…${filename.slice(-17)}`
    : filename;
}

export function selectableQueueItems(
  page: LabQueuePreview | null,
  loaded: ReadonlySet<string>,
  failed: ReadonlySet<string>,
) {
  return page?.items.filter((item) => loaded.has(item.binding.crop_id)
    && !failed.has(item.binding.crop_id)) ?? [];
}

export function queueDecision(
  page: LabQueuePreview,
  selected: ReadonlySet<string>,
  loaded: ReadonlySet<string>,
  failed: ReadonlySet<string>,
  active: DictionaryView | null,
  symbolId: string,
  requestId: string,
): SymbolRequest | null {
  if (!active?.version || !active.entries?.some((entry) => entry.id === symbolId))
    return null;
  if ([...selected].some((id) => !loaded.has(id) || failed.has(id)
    || !page.items.some((item) => item.binding.crop_id === id))) return null;
  const bindings = selectableQueueItems(page, loaded, failed)
    .filter((item) => selected.has(item.binding.crop_id))
    .map((item) => item.binding);
  if (!bindings.length || bindings.length > MAX_QUEUE_ASSIGNMENT) return null;
  return {
    op: 'label_cells_decide',
    request_id: requestId,
    expected_revision: page.revision,
    actor: 'operator',
    dictionary_version: active.version,
    dictionary_digest: active.digest,
    symbol_id: symbolId,
    bindings,
  };
}
