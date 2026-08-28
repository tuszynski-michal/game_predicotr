import type { ApprovedSymbolReferenceCandidatePageResponse } from '@game-predictor/admin-api-client';

export type SymbolReferenceCandidatePage =
  ApprovedSymbolReferenceCandidatePageResponse;

export function appendSymbolReferenceCandidatePage(
  pages: readonly SymbolReferenceCandidatePage[],
  page: SymbolReferenceCandidatePage,
): readonly SymbolReferenceCandidatePage[] {
  return [...pages, page];
}

export function currentSymbolReferenceCandidatePage(
  pages: readonly SymbolReferenceCandidatePage[],
  pageIndex: number,
): SymbolReferenceCandidatePage | null {
  return pages[pageIndex] ?? null;
}

export function canGoToNextSymbolReferencePage(
  pages: readonly SymbolReferenceCandidatePage[],
  pageIndex: number,
): boolean {
  const current = currentSymbolReferenceCandidatePage(pages, pageIndex);
  return (
    pageIndex < pages.length - 1 ||
    (current !== null && current.nextCursor !== null)
  );
}

export function canGoToPreviousSymbolReferencePage(pageIndex: number): boolean {
  return pageIndex > 0;
}
