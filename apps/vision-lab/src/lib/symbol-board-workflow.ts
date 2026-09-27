import type {
  LabBoardPreview,
  LabelBoardDecide,
} from '../../../../packages/vision-lab-api-client/src/index';

export function boardChoices(preview: LabBoardPreview): string[] {
  return preview.cells.map(({ binding, current }) => {
    const dictionary = preview.dictionary;
    if (!current || !dictionary || current.action === 'withdraw') return '';
    const saved = current.metadata;
    if (
      saved.dictionary_version !== dictionary.version ||
      saved.dictionary_digest !== dictionary.digest ||
      (saved.binding as { crop_id?: string } | undefined)?.crop_id !==
        binding.crop_id
    )
      return '';
    if (current.action === 'approve') {
      return current.label_valid &&
        dictionary.entries?.some((e) => e.id === current.symbol_id)
        ? `class:${current.symbol_id}`
        : '';
    }
    if (
      ['unknown', 'unreadable', 'grid_issue'].includes(current.action) &&
      current.reasons.every((reason) =>
        ['SYMBOL_NOT_APPROVED', 'SYMBOL_CLASS_UNKNOWN'].includes(reason),
      )
    ) {
      return `state:${current.action}`;
    }
    return '';
  });
}

export function boardDecision(
  preview: LabBoardPreview,
  choices: readonly string[],
  requestId: string,
): LabelBoardDecide {
  const dictionary = preview.dictionary;
  if (
    !dictionary?.version ||
    choices.length !== preview.cells.length ||
    choices.some((c) => !c)
  )
    throw new Error('SYMBOL_BOARD_INCOMPLETE');
  return {
    op: 'label_board_decide',
    request_id: requestId,
    expected_revision: preview.revision,
    actor: 'operator',
    dictionary_version: dictionary.version,
    dictionary_digest: dictionary.digest,
    cells: preview.cells.map(({ binding }, index) => {
      const value = choices[index];
      if (
        value.startsWith('class:') &&
        dictionary.entries?.some((e) => e.id === value.slice(6))
      )
        return { binding, action: 'approve', symbol_id: value.slice(6) };
      const action = value.slice(6);
      if (
        value.startsWith('state:') &&
        (action === 'unknown' ||
          action === 'unreadable' ||
          action === 'grid_issue')
      )
        return { binding, action, symbol_id: null };
      throw new Error('SYMBOL_BOARD_CHOICE_INVALID');
    }),
  };
}

export function boardOverlay(preview: LabBoardPreview) {
  const { columns, rows } = preview.topology;
  const point = (row: number, column: number) =>
    preview.nodes[row * (columns + 1) + column];
  const lines = [
    ...Array.from({ length: rows + 1 }, (_, r) =>
      Array.from({ length: columns + 1 }, (_, c) => point(r, c)),
    ),
    ...Array.from({ length: columns + 1 }, (_, c) =>
      Array.from({ length: rows + 1 }, (_, r) => point(r, c)),
    ),
  ].map((line) => line.map((p) => `${p.x},${p.y}`).join(' '));
  const labels = preview.cells.map(({ binding }) => {
    const r = Math.floor(binding.cell_index / columns),
      c = binding.cell_index % columns;
    const quad = [
      point(r, c),
      point(r, c + 1),
      point(r + 1, c + 1),
      point(r + 1, c),
    ];
    return {
      index: binding.cell_index,
      x: quad.reduce((sum, p) => sum + p.x, 0) / 4,
      y: quad.reduce((sum, p) => sum + p.y, 0) / 4,
    };
  });
  return { lines, labels };
}

/** A late response never replaces the board selected by the operator. */
export function boardReadSession() {
  let generation = 0;
  return {
    begin: () => ++generation,
    invalidate: () => {
      generation++;
    },
    isCurrent: (session: number) => session === generation,
  };
}

export function boardImagesReady(
  preview: LabBoardPreview,
  loaded: ReadonlySet<string>,
  failed: boolean,
) {
  return (
    !failed &&
    loaded.has('board') &&
    preview.cells.every((c) => loaded.has(String(c.binding.cell_index)))
  );
}
