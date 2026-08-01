import type { SymbolImageCandidateResponse } from '@game-predictor/admin-api-client';

export function appendUniqueCandidates(
  current: readonly SymbolImageCandidateResponse[],
  incoming: readonly SymbolImageCandidateResponse[],
): readonly SymbolImageCandidateResponse[] {
  const seen = new Set(current.map((item) => item.observationId));
  return [
    ...current,
    ...incoming.filter((item) => {
      if (seen.has(item.observationId)) return false;
      seen.add(item.observationId);
      return true;
    }),
  ];
}
