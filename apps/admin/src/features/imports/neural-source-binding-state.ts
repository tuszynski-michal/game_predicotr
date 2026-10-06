import type {
  BrowserPageGeometryOverrideCreate,
  BrowserPageGeometryReviewSourceResponse,
} from '@game-predictor/admin-api-client';

export type NeuralSourceProposal = NonNullable<
  BrowserPageGeometryReviewSourceResponse['neuralProposal']
>;
export type NeuralSourceBinding = NonNullable<
  BrowserPageGeometryOverrideCreate['neuralProposalBinding']
>;
export interface NeuralSourceBindingDraft {
  readonly rangeStart: string;
  readonly rangeEnd: string;
  readonly rangeConfirmed: boolean;
  /** Empty is undecided; ignore is a deliberate rejection, never an absent slot. */
  readonly choices: Readonly<Record<string, string>>;
  readonly missing: readonly number[];
}
export interface NeuralSourceDraftScope {
  readonly gameId: string;
  readonly uploadId: string;
  readonly sourceChecksumSha256: string;
  readonly proposalChecksumSha256: string;
  readonly manifestChecksumSha256: string;
  readonly overrideRevision: number;
}
export function neuralBindingMatchesProposal(
  proposal: NeuralSourceProposal,
  binding: NeuralSourceBinding | null | undefined,
): binding is NeuralSourceBinding {
  return (
    binding != null &&
    binding.gameId === proposal.gameId &&
    binding.sourceSelectionId === proposal.sourceSelectionId &&
    binding.sourceChecksumSha256 === proposal.sourceChecksumSha256 &&
    binding.proposalChecksumSha256 === proposal.proposalChecksumSha256 &&
    binding.sourceWidth === proposal.sourceWidth &&
    binding.sourceHeight === proposal.sourceHeight &&
    binding.originalRange.sequenceRangeStart ===
      proposal.originalRange.sequenceRangeStart &&
    binding.originalRange.sequenceRangeEnd ===
      proposal.originalRange.sequenceRangeEnd
  );
}
export function initialNeuralSourceDraft(
  proposal: NeuralSourceProposal,
  binding?: NeuralSourceBinding | null,
  rangeConfirmedByOperator = false,
): NeuralSourceBindingDraft {
  const currentBinding = neuralBindingMatchesProposal(proposal, binding)
    ? binding
    : null;
  return {
    rangeStart: String(
      currentBinding?.confirmedRange.sequenceRangeStart ??
        proposal.originalRange.sequenceRangeStart,
    ),
    rangeEnd: String(
      currentBinding?.confirmedRange.sequenceRangeEnd ??
        proposal.originalRange.sequenceRangeEnd,
    ),
    rangeConfirmed: currentBinding != null && rangeConfirmedByOperator,
    choices:
      currentBinding == null
        ? {}
        : Object.fromEntries([
            ...currentBinding.assignments.map((a) => [
              a.detectionId,
              String(a.positionIndex),
            ]),
            ...currentBinding.ignoredDetectionIds.map((id) => [id, 'ignore']),
          ]),
    missing: currentBinding?.missingPositionIndexes ?? [],
  };
}
export function confirmedNeuralRange(
  proposal: NeuralSourceProposal,
  draft: NeuralSourceBindingDraft,
) {
  if (
    !/^[1-9]\d*$/.test(draft.rangeStart) ||
    !/^[1-9]\d*$/.test(draft.rangeEnd)
  )
    throw new Error('Podaj dodatni początek i koniec zakresu.');
  const start = Number(draft.rangeStart),
    end = Number(draft.rangeEnd);
  if (
    !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(end) ||
    end < start ||
    end - start > 8 ||
    start < proposal.originalRange.sequenceRangeStart ||
    end > proposal.originalRange.sequenceRangeEnd ||
    end > proposal.engineSnapshot.expectedLayoutCount
  )
    throw new Error(
      'Zakres musi zawierać od 1 do 9 pozycji, mieścić się w zakresie z nazwy i w granicy gry. Potwierdź poprawne numery ręcznie.',
    );
  return { sequenceRangeStart: start, sequenceRangeEnd: end };
}
export function buildNeuralSourceBinding(
  proposal: NeuralSourceProposal,
  draft: NeuralSourceBindingDraft,
): NeuralSourceBinding {
  const range = confirmedNeuralRange(proposal, draft);
  if (!draft.rangeConfirmed)
    throw new Error('Potwierdź numery plansz na zdjęciu.');
  const count = range.sequenceRangeEnd - range.sequenceRangeStart + 1;
  const assignments: NeuralSourceBinding['assignments'] = [],
    ignoredDetectionIds: string[] = [];
  const used = new Set<number>();
  for (const detection of proposal.detections) {
    const choice = draft.choices[detection.detectionId];
    if (choice === 'ignore') {
      ignoredDetectionIds.push(detection.detectionId);
      continue;
    }
    if (choice === undefined || !/^[0-8]$/.test(choice))
      throw new Error(
        'Przypisz każde wykrycie do planszy albo jawnie je odrzuć.',
      );
    const positionIndex = Number(choice);
    if (
      positionIndex >= count ||
      used.has(positionIndex) ||
      !detection.structurallyValid ||
      detection.latticeNodes === null
    )
      throw new Error('Każda plansza wymaga innego, poprawnego wykrycia.');
    used.add(positionIndex);
    assignments.push({ detectionId: detection.detectionId, positionIndex });
  }
  const missingPositionIndexes = Array.from(
    { length: count },
    (_, i) => i,
  ).filter((i) => !used.has(i));
  if (
    new Set(draft.missing).size !== draft.missing.length ||
    JSON.stringify([...draft.missing].sort((a, b) => a - b)) !==
      JSON.stringify(missingPositionIndexes)
  )
    throw new Error(
      'Potwierdź wszystkie brakujące plansze. Ich numery pozostaną wolne.',
    );
  return {
    contractVersion: 'neural-source-binding-v1',
    gameId: proposal.gameId,
    sourceSelectionId: proposal.sourceSelectionId,
    sourceChecksumSha256: proposal.sourceChecksumSha256,
    sourceWidth: proposal.sourceWidth,
    sourceHeight: proposal.sourceHeight,
    proposalChecksumSha256: proposal.proposalChecksumSha256,
    originalRange: proposal.originalRange,
    confirmedRange: range,
    assignments: assignments.sort((a, b) => a.positionIndex - b.positionIndex),
    missingPositionIndexes,
    ignoredDetectionIds: ignoredDetectionIds.sort(),
  };
}
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem' | 'removeItem'>;
export function neuralSourceDraftKey(scope: NeuralSourceDraftScope) {
  return `neural-source-binding-draft-v1:${scope.gameId}:${scope.uploadId}:${scope.sourceChecksumSha256}`;
}
export interface StoredNeuralSourceDraft {
  readonly draft: NeuralSourceBindingDraft;
  readonly submittedCommand: BrowserPageGeometryOverrideCreate | null;
}
export function writeNeuralSourceDraft(
  storage: Storage,
  scope: NeuralSourceDraftScope,
  draft: StoredNeuralSourceDraft,
) {
  storage.setItem(
    neuralSourceDraftKey(scope),
    JSON.stringify({ version: 1, scope, ...draft }),
  );
}
export function clearNeuralSourceDraft(
  storage: Storage,
  scope: NeuralSourceDraftScope,
) {
  storage.removeItem(neuralSourceDraftKey(scope));
}
export function readNeuralSourceDraft(
  storage: Storage,
  scope: NeuralSourceDraftScope,
): StoredNeuralSourceDraft | null {
  const text = storage.getItem(neuralSourceDraftKey(scope));
  if (text === null) return null;
  const raw = JSON.parse(text);
  const d = raw?.draft;
  if (
    raw.version !== 1 ||
    JSON.stringify(raw.scope) !== JSON.stringify(scope) ||
    !d ||
    typeof d.rangeStart !== 'string' ||
    typeof d.rangeEnd !== 'string' ||
    typeof d.rangeConfirmed !== 'boolean' ||
    !d.choices ||
    typeof d.choices !== 'object' ||
    Object.values(d.choices).some(
      (v) =>
        typeof v !== 'string' ||
        (v !== '' && v !== 'ignore' && !/^[0-8]$/.test(v)),
    ) ||
    !Array.isArray(d.missing) ||
    d.missing.some(
      (i: unknown) =>
        typeof i !== 'number' || !Number.isInteger(i) || i < 0 || i > 8,
    ) ||
    (raw.submittedCommand !== null &&
      (!raw.submittedCommand ||
        raw.submittedCommand.gameId !== scope.gameId ||
        raw.submittedCommand.sourceChecksumSha256 !==
          scope.sourceChecksumSha256 ||
        raw.submittedCommand.neuralProposalBinding?.proposalChecksumSha256 !==
          scope.proposalChecksumSha256))
  )
    throw new Error(
      'Zapisany szkic dotyczy wcześniejszej propozycji lub rewizji. Odśwież kontekst i rozpocznij nowy szkic.',
    );
  return { draft: d, submittedCommand: raw.submittedCommand };
}
