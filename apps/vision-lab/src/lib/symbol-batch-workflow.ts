import type {
  BatchLabelDecide,
  BatchQueuePreview,
  SymbolResult,
} from '../../../../packages/vision-lab-api-client/src/index';

/** Only an actually displayed crop and an explicit operator choice can be submitted. */
export function batchDecision(
  page: BatchQueuePreview,
  caseId: string,
  loaded: ReadonlySet<string>,
  action: BatchLabelDecide['action'],
  symbolId: string | null,
  requestId: string,
): BatchLabelDecide | null {
  if (
    !loaded.has(caseId) ||
    !page.items.some((item) => item.case_id === caseId)
  )
    return null;
  if (
    action === 'approve' &&
    !page.dictionary.entries?.some((entry) => entry.id === symbolId)
  )
    return null;
  if (action !== 'approve' && symbolId !== null) return null;
  return {
    op: 'batch_label_decide',
    actor: 'operator',
    request_id: requestId,
    expected_revision: page.revision,
    reference_id: page.reference_id,
    case_id: caseId,
    action,
    symbol_id: symbolId,
  };
}

/** Receipt updates one decision while keeping every exact PNG frozen. */
export function confirmedBatchPage(
  page: BatchQueuePreview,
  request: BatchLabelDecide,
  result: SymbolResult,
): BatchQueuePreview | null {
  if (
    request.reference_id !== page.reference_id ||
    request.expected_revision !== page.revision ||
    result.request_id !== request.request_id ||
    result.revision !== page.revision + 1 ||
    result.decision_ids?.length !== 1 ||
    result.result_id !== result.decision_ids[0] ||
    !page.items.some((item) => item.case_id === request.case_id)
  )
    return null;
  return {
    ...page,
    revision: result.revision,
    items: page.items.map((item) =>
      item.case_id === request.case_id
        ? {
            ...item,
            action: request.action,
            symbol_id: request.symbol_id ?? null,
            decision_id: result.decision_ids[0],
          }
        : item,
    ),
  };
}
