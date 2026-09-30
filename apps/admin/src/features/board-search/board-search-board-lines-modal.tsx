'use client';

import type {
  ApproximateWinRowResponse,
  BoardSearchBoardDetailResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useRef, useState } from 'react';

import type { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

import {
  BOARD_SCHEMA_CELL,
  type BoardLinePoint,
  type BoardLineVisibility,
  boardLineKey,
  boardLineOffset,
  boardLineStyles,
  boardLinesConsistency,
  boardLinesPolygonCentroid,
  boardSchemaCellPolygon,
  initialBoardLineVisibility,
  setAllBoardLinesVisibility,
  toggleBoardLineVisibility,
} from './board-search-board-lines-state';

export type BoardLinesClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  | 'boardSearchBoardViewUrl'
  | 'getBoardSearchBoardDetail'
  | 'symbolImageAssetUrl'
>;

type DetailState =
  | { readonly kind: 'loading' }
  | { readonly kind: 'error'; readonly message: string }
  | {
      readonly kind: 'ready';
      readonly detail: BoardSearchBoardDetailResponse;
    };

export function BoardSearchBoardLinesModal({
  api,
  formatAmount,
  gameId,
  onClose,
  onRecalculate,
  row,
  rulesVersionId,
  symbols,
}: {
  readonly api: BoardLinesClient;
  readonly formatAmount: (baseCredits: number) => string;
  readonly gameId: string;
  readonly onClose: () => void;
  readonly onRecalculate: () => void;
  readonly row: ApproximateWinRowResponse;
  readonly rulesVersionId: string;
  readonly symbols: readonly SymbolResponse[];
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<DetailState>({ kind: 'loading' });
  const [visibility, setVisibility] = useState<BoardLineVisibility>(new Set());
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  useEffect(() => {
    // A late answer for an earlier attempt or board must never be shown.
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setState({ kind: 'loading' });
      setImageFailed(false);
      void api
        .getBoardSearchBoardDetail(gameId, row.sequenceNumber)
        .then((result) => {
          if (cancelled) return;
          if (result.error !== undefined || result.data === undefined) {
            setState({
              kind: 'error',
              message: apiErrorMessage(
                result.error,
                'Nie udało się pobrać planszy z liniami wypłat.',
              ),
            });
            return;
          }
          setVisibility(initialBoardLineVisibility(result.data.matches));
          setState({ detail: result.data, kind: 'ready' });
        })
        .catch(() => {
          if (!cancelled) {
            setState({
              kind: 'error',
              message:
                'Połączenie z lokalnym Admin API zostało przerwane podczas pobierania planszy.',
            });
          }
        });
    });
    return () => {
      cancelled = true;
    };
  }, [api, gameId, row.sequenceNumber, attempt]);

  // Close the native modal first: while it is open everything else is
  // inert, so the parent could not move focus back to the row button.
  const requestClose = () => {
    dialog.current?.close();
    onClose();
  };

  const detail = state.kind === 'ready' ? state.detail : null;
  const consistency =
    detail === null
      ? null
      : boardLinesConsistency(detail, row.payoutCredits, rulesVersionId);

  return (
    <dialog
      aria-labelledby="board-lines-title"
      className="symbolImagePickerDialog boardSearchBoardLinesDialog"
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
      ref={dialog}
    >
      <div className="symbolImagePickerCard">
        <header className="symbolImagePickerHeader">
          <div>
            <h2 id="board-lines-title">
              Plansza #{row.sequenceNumber} · spin{' '}
              {row.spinNumber.toLocaleString('pl-PL')}
            </h2>
            <p>
              Wypłata {formatAmount(row.payoutCredits)}
              {row.payoutKind === 'confirmed_minimum'
                ? ' · częściowa (potwierdzone minimum)'
                : ''}{' '}
              · {boardStatusLabel(row.boardStatus)}. Linia liczy się tylko od
              lewej krawędzi i kończy na pierwszym nieznanym polu.
            </p>
          </div>
          <button
            className="secondaryButton"
            onClick={requestClose}
            type="button"
          >
            Zamknij
          </button>
        </header>

        {state.kind === 'loading' ? (
          <p role="status">Wczytywanie planszy…</p>
        ) : null}
        {state.kind === 'error' ? (
          <div role="alert">
            <p className="feedbackBanner feedbackBannerError">
              {state.message}
            </p>
            <button
              className="secondaryButton"
              onClick={() => setAttempt((value) => value + 1)}
              type="button"
            >
              Spróbuj ponownie
            </button>
          </div>
        ) : null}
        {detail !== null && consistency?.kind === 'inconsistent' ? (
          <div role="alert">
            <p className="feedbackBanner feedbackBannerError">
              {consistency.reason === 'rules'
                ? 'Reguły wypłat zmieniły się od obliczenia tabeli.'
                : 'Wypłata tej planszy zmieniła się od obliczenia tabeli.'}{' '}
              Linie nie zostały narysowane, aby nie pokazać niespójnego wyniku.
            </p>
            <button
              className="primaryButton"
              onClick={() => {
                onRecalculate();
                requestClose();
              }}
              type="button"
            >
              Przelicz ponownie
            </button>
          </div>
        ) : null}
        {detail !== null && consistency?.kind === 'consistent' ? (
          <BoardLinesView
            api={api}
            detail={detail}
            formatAmount={formatAmount}
            gameId={gameId}
            imageFailed={imageFailed}
            onImageError={() => setImageFailed(true)}
            onVisibilityChange={setVisibility}
            symbols={symbols}
            visibility={visibility}
          />
        ) : null}
      </div>
    </dialog>
  );
}

function BoardLinesView({
  api,
  detail,
  formatAmount,
  gameId,
  imageFailed,
  onImageError,
  onVisibilityChange,
  symbols,
  visibility,
}: {
  readonly api: BoardLinesClient;
  readonly detail: BoardSearchBoardDetailResponse;
  readonly formatAmount: (baseCredits: number) => string;
  readonly gameId: string;
  readonly imageFailed: boolean;
  readonly onImageError: () => void;
  readonly onVisibilityChange: (visibility: BoardLineVisibility) => void;
  readonly symbols: readonly SymbolResponse[];
  readonly visibility: BoardLineVisibility;
}) {
  const view = detail.view;
  const polygons = view?.cellPolygons ?? null;
  const usePhoto = view !== null && polygons !== null && !imageFailed;
  const width = usePhoto ? view.width : 5 * BOARD_SCHEMA_CELL;
  const height = usePhoto ? view.height : 3 * BOARD_SCHEMA_CELL;
  const cells: readonly (readonly BoardLinePoint[])[] =
    usePhoto && polygons !== null
      ? polygons.map((polygon) =>
          polygon.map((point) => ({
            x: point.x * view.width,
            y: point.y * view.height,
          })),
        )
      : Array.from({ length: 15 }, (_, index) => boardSchemaCellPolygon(index));
  const centroids = cells.map(boardLinesPolygonCentroid);
  const cellHeight = (index: number) => {
    const ys = (cells[index] ?? []).map((point) => point.y);
    return ys.length === 0 ? 0 : Math.max(...ys) - Math.min(...ys);
  };
  const styles = boardLineStyles(detail.matches);
  const symbolByCode = new Map(symbols.map((symbol) => [symbol.code, symbol]));
  const visibleMatches = detail.matches.filter((match) =>
    visibility.has(boardLineKey(match)),
  );
  const imageUrl =
    view === null
      ? null
      : api.boardSearchBoardViewUrl(
          gameId,
          detail.sequenceNumber,
          detail.boardChecksumSha256,
          view.revision,
        );

  return (
    <div className="boardSearchBoardLines">
      <div className="boardSearchBoardLinesCanvas">
        <svg
          aria-label={`Plansza ${detail.sequenceNumber} z ${visibleMatches.length} widocznymi liniami wypłat`}
          role="img"
          viewBox={`0 0 ${width} ${height}`}
        >
          {usePhoto && imageUrl !== null ? (
            <image
              height={height}
              href={imageUrl}
              onError={onImageError}
              preserveAspectRatio="none"
              width={width}
              x={0}
              y={0}
            />
          ) : (
            cells.map((cell, index) => {
              const code = detail.symbolCodes[index] ?? null;
              const symbol = code === null ? undefined : symbolByCode.get(code);
              const centre = centroids[index] ?? { x: 0, y: 0 };
              return (
                <g className="boardSearchBoardLinesSchemaCell" key={index}>
                  <polygon points={pointsText(cell)} />
                  {symbol?.imagePath ? (
                    <image
                      height={BOARD_SCHEMA_CELL * 0.62}
                      href={api.symbolImageAssetUrl(gameId, symbol.id)}
                      width={BOARD_SCHEMA_CELL * 0.62}
                      x={centre.x - BOARD_SCHEMA_CELL * 0.31}
                      y={centre.y - BOARD_SCHEMA_CELL * 0.4}
                    />
                  ) : null}
                  {code !== null ? (
                    <text
                      textAnchor="middle"
                      x={centre.x}
                      y={centre.y + BOARD_SCHEMA_CELL * 0.38}
                    >
                      {symbol?.name ?? code}
                    </text>
                  ) : null}
                </g>
              );
            })
          )}
          {cells.map((cell, index) =>
            detail.symbolCodes[index] === null ? (
              <g
                className="boardSearchBoardLinesUnknown"
                key={`unknown:${index}`}
              >
                <polygon points={pointsText(cell)} />
                <text
                  fontSize={cellHeight(index) * 0.42}
                  textAnchor="middle"
                  x={centroids[index]?.x ?? 0}
                  y={(centroids[index]?.y ?? 0) + cellHeight(index) * 0.15}
                >
                  ?
                </text>
              </g>
            ) : null,
          )}
          {visibleMatches.map((match) => {
            const style = styles.get(boardLineKey(match));
            const color = style?.color ?? '#ffffff';
            // Offsets use the position among all lines, so hiding one line
            // never moves the others.
            const offset = boardLineOffset(
              detail.matches.indexOf(match),
              detail.matches.length,
            );
            const path = match.matchedCells.map((cellIndex) => {
              const centre = centroids[cellIndex] ?? { x: 0, y: 0 };
              return {
                x: centre.x,
                y: centre.y + offset * cellHeight(cellIndex),
              };
            });
            return (
              <g
                className="boardSearchBoardLinesMatch"
                data-line={boardLineKey(match)}
                key={boardLineKey(match)}
              >
                {match.matchedCells.map((cellIndex) => (
                  <polygon
                    fill={color}
                    fillOpacity={0.12}
                    key={cellIndex}
                    points={pointsText(cells[cellIndex] ?? [])}
                    stroke={color}
                    strokeWidth={2}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
                <polyline
                  fill="none"
                  points={pointsText(path)}
                  stroke={color}
                  strokeDasharray={style?.dashArray}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={4}
                  vectorEffect="non-scaling-stroke"
                />
                {match.jokerCells.map((cellIndex) => {
                  const centre = path[match.matchedCells.indexOf(cellIndex)];
                  return centre === undefined ? null : (
                    <g className="boardSearchBoardLinesJoker" key={cellIndex}>
                      <circle
                        cx={centre.x}
                        cy={centre.y}
                        r={cellHeight(cellIndex) * 0.14}
                        stroke={color}
                      />
                      <text
                        fontSize={cellHeight(cellIndex) * 0.17}
                        textAnchor="middle"
                        x={centre.x}
                        y={centre.y + cellHeight(cellIndex) * 0.06}
                      >
                        J
                      </text>
                    </g>
                  );
                })}
              </g>
            );
          })}
        </svg>
        {!usePhoto ? (
          <p className="boardSearchBoardLinesNote">
            {view === null || imageFailed
              ? 'Zdjęcie tej planszy jest niedostępne — linie pokazano na schemacie 3 × 5.'
              : 'Plansza archiwalna nie ma zapisanej siatki pól — linie pokazano na schemacie 3 × 5.'}
          </p>
        ) : null}
      </div>

      <aside
        aria-label="Legenda linii wypłat"
        className="boardSearchBoardLinesLegend"
      >
        <div className="boardSearchBoardLinesLegendActions">
          <button
            className="textButton"
            onClick={() =>
              onVisibilityChange(
                setAllBoardLinesVisibility(detail.matches, true),
              )
            }
            type="button"
          >
            Pokaż wszystkie
          </button>
          <button
            className="textButton"
            onClick={() =>
              onVisibilityChange(
                setAllBoardLinesVisibility(detail.matches, false),
              )
            }
            type="button"
          >
            Ukryj wszystkie
          </button>
        </div>
        {detail.matches.length === 0 ? (
          <p>Ta plansza nie ma wygrywającej linii.</p>
        ) : (
          <ul>
            {detail.matches.map((match) => {
              const key = boardLineKey(match);
              const style = styles.get(key);
              const symbol = symbolByCode.get(match.symbolCode);
              return (
                <li key={key}>
                  <label>
                    <input
                      checked={visibility.has(key)}
                      onChange={() =>
                        onVisibilityChange(
                          toggleBoardLineVisibility(visibility, key),
                        )
                      }
                      type="checkbox"
                    />
                    <span
                      aria-hidden="true"
                      className="boardSearchBoardLinesSwatch"
                      style={{
                        borderColor: style?.color,
                        borderStyle:
                          style?.dashArray === undefined
                            ? 'solid'
                            : style.dashArray === '8 5'
                              ? 'dashed'
                              : 'dotted',
                      }}
                    />
                    <span>
                      <strong>{match.paylineName}</strong> ·{' '}
                      {symbol?.name ?? match.symbolCode} × {match.matchedLength}
                      {match.jokerCells.length > 0
                        ? ` (joker: ${match.jokerCells.length})`
                        : ''}{' '}
                      · {formatAmount(match.payoutCredits)}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </aside>
    </div>
  );
}

function boardStatusLabel(status: string): string {
  switch (status) {
    case 'accepted':
      return 'plansza zatwierdzona';
    case 'corrected':
      return 'plansza poprawiona';
    case 'pending':
      return 'plansza oczekuje';
    default:
      return `status ${status}`;
  }
}

function pointsText(points: readonly BoardLinePoint[]): string {
  return points.map((point) => `${point.x},${point.y}`).join(' ');
}
