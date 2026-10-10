import type {
  DictionaryView,
  LabQueuePreview,
  SymbolRequest,
  SymbolResult,
} from '../../../../packages/vision-lab-api-client/src/index';

export const MAX_QUEUE_ASSIGNMENT = 30;

export type QueueConfirmation = {
  request: Extract<SymbolRequest, { op: 'label_cells_decide' }>;
  result: SymbolResult;
};

/** Keep the displayed pixels frozen; only receipt-confirmed labels change their badge. */
export function confirmedQueuePage(
  page: LabQueuePreview,
  { request, result }: QueueConfirmation,
): LabQueuePreview | null {
  if (
    !result.label_valid ||
    result.request_id !== request.request_id ||
    page.revision !== request.expected_revision ||
    result.revision !== request.expected_revision + 1 ||
    result.decision_ids.length !== request.bindings.length ||
    new Set(result.decision_ids).size !== result.decision_ids.length ||
    !request.bindings.length ||
    request.bindings.length > MAX_QUEUE_ASSIGNMENT ||
    request.bindings.some(
      (binding) =>
        !page.items.some(
          (item) =>
            item.status !== 'assigned' &&
            item.binding.crop_id === binding.crop_id &&
            JSON.stringify(item.binding) === JSON.stringify(binding),
        ),
    )
  )
    return null;
  const removed = new Set(request.bindings.map((binding) => binding.crop_id));
  if (removed.size !== request.bindings.length) return null;
  return {
    ...page,
    revision: result.revision,
    items: page.items.map((item) =>
      removed.has(item.binding.crop_id)
        ? { ...item, status: 'assigned' as const, reason: null }
        : item,
    ),
  };
}

export function queueSourceCaption(sourceName: string): string {
  const filename = sourceName.split(/[\\/]/).at(-1) || sourceName;
  return filename.length > 24 ? `…${filename.slice(-17)}` : filename;
}

export function selectableQueueItems(
  page: LabQueuePreview | null,
  loaded: ReadonlySet<string>,
  failed: ReadonlySet<string>,
) {
  return (
    page?.items.filter(
      (item) =>
        item.status !== 'assigned' &&
        loaded.has(item.binding.crop_id) &&
        !failed.has(item.binding.crop_id),
    ) ?? []
  );
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
  if (
    !active?.version ||
    !active.entries?.some((entry) => entry.id === symbolId)
  )
    return null;
  if (
    [...selected].some(
      (id) =>
        !loaded.has(id) ||
        failed.has(id) ||
        !page.items.some(
          (item) => item.binding.crop_id === id && item.status !== 'assigned',
        ),
    )
  )
    return null;
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
