import type { ImageSequenceSourceSelectionResponse } from '@game-predictor/admin-api-client';

export function SequenceSourceCandidates({
  selection,
  busy,
  apiBaseUrl,
  onChoose,
  sourceAssetUrl,
}: {
  readonly selection: ImageSequenceSourceSelectionResponse;
  readonly busy: boolean;
  readonly apiBaseUrl: string;
  readonly onChoose: (reviewItemId: string | null) => void;
  readonly sourceAssetUrl: (
    reviewItemId: string,
    context: { gameId: string; importJobId: string },
  ) => string;
}) {
  const reserved =
    selection.state === 'reserved_gap' || selection.state === 'pending_bound';
  return (
    <>
      {reserved ? (
        <p role="status">
          {selection.state === 'reserved_gap'
            ? 'Luka zarezerwowana na zdjęcie zastępcze. Zwykły wybór źródła jest zablokowany.'
            : 'Zdjęcie zastępcze powiązano z rezerwacją. Oczekuje na zatwierdzenie.'}{' '}
          {selection.replacementManifestUrl ? (
            <a
              href={`${apiBaseUrl.replace(/\/$/, '')}${selection.replacementManifestUrl}`}
            >
              Manifest wymiany
            </a>
          ) : null}
          {selection.replacementEntryId ? (
            <small> · wpis {selection.replacementEntryId}</small>
          ) : null}
        </p>
      ) : null}
      {selection.state === 'history_only' ? (
        <p role="status">
          Brak bieżącego źródła. Zachowano historię wycofanych zdjęć.
        </p>
      ) : null}
      {selection.manualOverrideReviewItemId && !reserved ? (
        <button
          className="secondaryButton"
          disabled={busy}
          onClick={() => onChoose(null)}
          type="button"
        >
          Przywróć wybór automatyczny
        </button>
      ) : null}
      <ul className="importCompactList">
        {selection.candidates.map((candidate) => (
          <li key={candidate.reviewItemId}>
            <strong>
              #{candidate.automaticRank} · jakość{' '}
              {(candidate.qualityScore * 100).toFixed(1)}%
              {candidate.selected ? ' · wybrane' : ''}
            </strong>
            {candidate.sourceState === 'retired' ||
            candidate.sourceState === 'replaced' ? (
              <span>
                {candidate.sourceState === 'replaced'
                  ? 'Zastąpione zdjęcie'
                  : 'Wycofane zdjęcie'}{' '}
                · tylko historia
              </span>
            ) : null}
            <span>
              {candidate.width} × {candidate.height} · OCR{' '}
              {(candidate.sequenceConfidence * 100).toFixed(1)}% · plansza{' '}
              {(candidate.boardConfidence * 100).toFixed(1)}%
            </span>
            <small>{candidate.sourceRelativePath}</small>
            <a
              href={sourceAssetUrl(candidate.reviewItemId, {
                gameId: selection.gameId,
                importJobId: candidate.importJobId,
              })}
              target="_blank"
              rel="noreferrer"
            >
              Podgląd zdjęcia
            </a>
            {!candidate.selected &&
            candidate.selectable !== false &&
            !reserved ? (
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() => onChoose(candidate.reviewItemId)}
                type="button"
              >
                Wybierz to źródło
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </>
  );
}
