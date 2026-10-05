import type { ImageGridReviewItemResponse } from '@game-predictor/admin-api-client';

export function gridShadowErrorMessage(
  error: unknown,
  fallback: string,
): string {
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? error.code
      : null;
  if (code === 'GRID_SHADOW_DISABLED')
    return 'Tryb porównawczy jest wyłączony. Operator musi go włączyć przed uruchomieniem zadania.';
  if (code === 'GRID_SHADOW_PROFILE_REQUIRED')
    return 'Najpierw wybierz profil silnika siatek dla tej gry.';
  return fallback;
}

export function gridShadowSourceChoices(
  items: readonly ImageGridReviewItemResponse[],
) {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.sourceImageId)) return false;
    seen.add(item.sourceImageId);
    return true;
  });
}

export function gridShadowUnknownVisibilityCount(
  visibility: readonly string[],
): number {
  return visibility.filter((state) => state === 'unknown').length;
}

/** Full 4 × 6 lattice, never an interpolation of only four corners. */
export function gridShadowMeshLines(
  nodes: readonly { readonly x: number; readonly y: number }[],
) {
  if (
    nodes.length !== 24 ||
    nodes.some(({ x, y }) => !Number.isFinite(x) || !Number.isFinite(y))
  )
    return [];
  const lines: string[] = [];
  for (let row = 0; row < 4; row++) {
    lines.push(
      nodes
        .slice(row * 6, row * 6 + 6)
        .map(({ x, y }) => `${x},${y}`)
        .join(' '),
    );
  }
  for (let col = 0; col < 6; col++) {
    lines.push(
      [0, 1, 2, 3]
        .map((row) => nodes[row * 6 + col])
        .map(({ x, y }) => `${x},${y}`)
        .join(' '),
    );
  }
  return lines;
}

export function gridShadowReviewerUrl(
  adminUrl: string,
  gameId: string,
  resultId: string,
  positionIndex: number,
): string | null {
  let url: URL;
  try {
    url = new URL(adminUrl);
  } catch {
    return null;
  }
  if (
    url.protocol !== 'http:' ||
    !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  )
    return null;
  url.port = '3001';
  url.pathname = '/';
  url.search = '';
  url.hash = '';
  url.searchParams.set('mode', 'local');
  url.searchParams.set('queue', 'grid-shadow');
  url.searchParams.set('gameId', gameId);
  url.searchParams.set('resultId', resultId);
  url.searchParams.set('positionIndex', String(positionIndex));
  return url.toString();
}

/** Preserve request identity after a lost response and after a page restart. */
export function gridShadowRequestId(
  storage: Pick<Storage, 'getItem' | 'setItem'>,
  gameId: string,
  sourceImageIds: readonly string[],
  newId: () => string,
): string {
  const key = `grid-shadow-request:${gameId}`;
  const sources = [...new Set(sourceImageIds)].sort();
  try {
    const saved = JSON.parse(storage.getItem(key) ?? 'null') as {
      sources?: unknown;
      requestId?: unknown;
    } | null;
    if (
      saved &&
      JSON.stringify(saved.sources) === JSON.stringify(sources) &&
      typeof saved.requestId === 'string'
    )
      return saved.requestId;
  } catch {
    /* Invalid local metadata is replaced; it never changes server data. */
  }
  const requestId = newId();
  storage.setItem(key, JSON.stringify({ sources, requestId }));
  return requestId;
}

export function gridShadowStateLabel(state: string): string {
  const labels: Readonly<Record<string, string>> = {
    needs_review: 'Do sprawdzenia',
    missing: 'Brak wykrytej siatki',
    invalid: 'Niepoprawna siatka',
    unsupported: 'Nieobsługiwany układ',
    failed: 'Błąd przetwarzania',
    created: 'Oczekuje na przetwarzanie',
    processing: 'W trakcie porównania',
    completed: 'Porównanie zakończone',
    cancelled: 'Anulowane',
    waiting_for_review: 'Oczekuje na przegląd',
  };
  return labels[state] ?? 'Do sprawdzenia';
}

export function gridShadowReasonLabels(reasons: readonly string[]): string {
  const labels: Readonly<Record<string, string>> = {
    NEURAL_GRID_GATE_UNCALIBRATED:
      'Model wymaga ręcznego sprawdzenia — brak kalibracji',
    NEURAL_GRID_REVIEW_REQUIRED: 'Propozycja wymaga sprawdzenia',
    NEURAL_GRID_MISSING: 'Nie wykryto siatki',
    SOURCE_BINDING_STALE: 'Źródło albo geometria zmieniły się',
  };
  return (
    [
      ...new Set(
        reasons.map(
          (reason) => labels[reason] ?? 'Geometria wymaga sprawdzenia',
        ),
      ),
    ].join(' · ') || 'Wynik wymaga ręcznego sprawdzenia'
  );
}
