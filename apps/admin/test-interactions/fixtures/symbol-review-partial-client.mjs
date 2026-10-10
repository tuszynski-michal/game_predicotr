export const sourceSvg =
  '<svg xmlns="http://www.w3.org/2000/svg" width="500" height="300"><rect width="500" height="300" fill="#dbeafe"/><text x="120" y="150" font-size="36">Zdjęcie testowe</text></svg>';

export function partialReviewItem(overrides = {}) {
  return {
    id: 'outside-cell',
    sequenceNumber: 62287,
    cellIndex: 0,
    rowIndex: 0,
    columnIndex: 0,
    assetMode: 'none',
    sourceVisibility: 'outside',
    cropChecksumSha256: null,
    cropSampleId: null,
    assignedSymbolCode: null,
    assignedSymbolId: null,
    assignedSymbolName: null,
    boardStatus: 'pending',
    cropApprovalState: 'unverified',
    geometryRevision: 4,
    hasGridIssue: false,
    importJobId: 'import-1',
    isUnknown: false,
    predictionConfidence: null,
    predictionSymbolCode: null,
    qualityIssue: null,
    recognizedBoardId: 'board-1',
    renderSpecChecksumSha256: null,
    reviewItemId: 'review-1',
    reviewState: 'pending',
    revision: 1,
    ...overrides,
  };
}

export async function createPartialReviewClient() {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(sourceSvg),
  );
  const checksum = Array.from(new Uint8Array(digest), (x) =>
    x.toString(16).padStart(2, '0'),
  ).join('');
  const calls = {
    pages: [],
    decisions: [],
    atlases: [],
    source: 0,
    reference: 0,
  };
  const cells = [
    partialReviewItem(),
    partialReviewItem({
      id: 'partial-cell',
      cellIndex: 1,
      columnIndex: 1,
      assetMode: 'virtual_source',
      sourceVisibility: 'partial',
      cropChecksumSha256: 'b'.repeat(64),
      cropSampleId: 'partial-crop',
      isUnknown: true,
      qualityIssue: 'partial_visibility',
    }),
    partialReviewItem({
      id: 'full-cell',
      cellIndex: 2,
      columnIndex: 2,
      assetMode: 'virtual_source',
      sourceVisibility: 'full',
      cropChecksumSha256: 'c'.repeat(64),
      cropSampleId: 'full-crop',
      isUnknown: false,
      assignedSymbolId: 'cherry',
      assignedSymbolName: 'Wiśnia',
      assignedSymbolCode: 'cherry',
    }),
  ];
  const matches = (item, scope) =>
    scope === 'all' ||
    (scope === 'outside'
      ? item.sourceVisibility === 'outside' && item.assignedSymbolId === null
      : scope === 'unknown'
        ? item.sourceVisibility !== 'outside' && item.assignedSymbolId === null
        : item.assignedSymbolId === scope);
  const api = {
    listGames: async () => ({
      data: [
        { id: 'game-1', name: 'Gra testowa', code: 'test', status: 'active' },
      ],
    }),
    listSymbols: async () => ({
      data: [
        {
          id: 'cherry',
          name: 'Wiśnia',
          code: 'cherry',
          status: 'active',
          displayOrder: 0,
        },
      ],
    }),
    getSymbolCellReviewProjectionStatus: async () => ({
      data: {
        gameId: 'game-1',
        status: 'ready',
        activeJobId: null,
        expectedBoardCount: 1,
        expectedCellCount: 15,
        persistedCellCount: 15,
      },
    }),
    listSymbolCellReviews: async (options) => {
      calls.pages.push(options);
      return {
        data: {
          catalogRevision: 1 + calls.decisions.length,
          items: cells
            .filter((cell) => matches(cell, options.symbolId))
            .filter(
              (cell) =>
                !['pending', 'approved'].includes(options.state) ||
                cell.reviewState === options.state,
            )
            .map((cell) => ({ ...cell })),
          nextCursor: null,
          previousCursor: null,
        },
      };
    },
    getSymbolCellReviewCounts: async (options) => ({
      data: {
        catalogRevision: 1 + calls.decisions.length,
        counts: {
          allCount: cells.filter((cell) => matches(cell, options.symbolId))
            .length,
          approvedCount: cells.filter(
            (cell) =>
              matches(cell, options.symbolId) &&
              cell.reviewState === 'approved',
          ).length,
          pendingCount: cells.filter(
            (cell) =>
              matches(cell, options.symbolId) && cell.reviewState === 'pending',
          ).length,
        },
      },
    }),
    createSymbolCellPreviewBatch: async (_game, body) => {
      calls.atlases.push(body);
      return {
        data: {
          batchKey: 'fixture',
          rendererVersion: 'fixture',
          rendererFingerprintSha256: 'd'.repeat(64),
          unavailableCellReviewIds: [],
          tiles: body.cells.map((cell) => ({
            cellReviewId: cell.cellReviewId,
            x: 0,
            y: 0,
            width: 100,
            height: 100,
          })),
        },
      };
    },
    symbolCellPreviewAtlasUrl: () =>
      `data:image/svg+xml,${encodeURIComponent(sourceSvg)}`,
    applySymbolCellReviewDecision: async (_game, id, command) => {
      calls.decisions.push({ id, command });
      const item = cells.find((cell) => cell.id === id);
      item.revision += 1;
      item.reviewState = 'approved';
      if (
        command.action === 'reassign' ||
        (command.action === 'mark_blurry' && command.targetSymbolId)
      ) {
        const target = (await api.listSymbols()).data.find(
          (symbol) => symbol.id === command.targetSymbolId,
        );
        item.assignedSymbolId = command.targetSymbolId;
        item.assignedSymbolName = target.name;
        item.assignedSymbolCode = target.code;
        item.isUnknown = false;
      }
      if (command.action === 'mark_blurry') {
        item.qualityIssue = 'blurry';
      }
      if (command.action === 'mark_unreadable') {
        item.qualityIssue = 'unreadable';
      }
      return {
        data: {
          assignedSymbolId: item.assignedSymbolId,
          cellReviewId: id,
          cellRevision: item.revision,
          catalogRevision: 1 + calls.decisions.length,
          reviewState: item.reviewState,
        },
      };
    },
    selectSymbolReferenceFromCellReview: async () => {
      calls.reference++;
      return { data: { name: 'Wiśnia' } };
    },
    getOperationalImageReviewItem: async () => ({
      data: {
        id: 'review-1',
        gameId: 'game-1',
        importJobId: 'import-1',
        recognizedBoardId: 'board-1',
        geometryRevision: 4,
        sourceChecksumSha256: checksum,
        geometry: {
          latticeBoundsQuad: [
            { x: -150, y: 0 },
            { x: 350, y: 0 },
            { x: 350, y: 300 },
            { x: -150, y: 300 },
          ],
        },
        cells: [],
      },
    }),
    getOperationalImageReviewSourceAsset: async () => {
      calls.source++;
      return { data: new Blob([sourceSvg], { type: 'image/svg+xml' }) };
    },
  };
  api.previewSymbolCellReviewBulkOperation = async (_game, request) => ({
    data: {
      action: request.action,
      targetCount: request.selection.targets.length,
      boardCount: 1,
      catalogRevision: 1 + calls.decisions.length,
      selectionKind: 'explicit',
    },
  });
  api.startSymbolCellReviewBulkOperation = async (game, request) => {
    for (const target of request.selection.targets) {
      await api.applySymbolCellReviewDecision(game, target.cellReviewId, {
        ...target,
        action: request.action,
        targetSymbolId: request.targetSymbolId,
      });
    }
    return {
      data: {
        created: true,
        operation: {
          id: 'bulk-1',
          gameId: game,
          action: request.action,
          targetSymbolId: request.targetSymbolId ?? null,
          status: 'completed',
          targetCount: request.selection.targets.length,
          appliedCount: request.selection.targets.length,
          conflictCount: 0,
          failedCount: 0,
          pendingCount: 0,
          catalogRevision: 1 + calls.decisions.length,
        },
      },
    };
  };
  return { api, calls, cells };
}
