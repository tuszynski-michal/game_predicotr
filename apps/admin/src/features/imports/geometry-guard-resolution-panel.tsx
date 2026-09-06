'use client';

/* Staged source assets are checksum-bound local images and bypass Next optimization. */
/* eslint-disable @next/next/no-img-element */

import type {
  ImageGeometryGuardBoardContextResponse,
  ImageGeometryGuardDecisionResponse,
  ImageGeometryGuardDecisionItemCreate,
  ImageGeometryGuardPreviewResponse,
  ImageGeometryGuardQueueResponse,
  ImageGeometryGuardResolutionManifestResponse,
  JobResponse,
  PageGeometryPoint,
} from '@game-predictor/admin-api-client';
import {
  type PointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { resolveAdminApiBaseUrl } from '@/config/admin-api';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

import type { ImageFolderImportClient } from './image-folder-import-actions';
import {
  type GuardQuad,
  guardGridLines,
  guardQuadFromUnknown,
  initialGuardQuad,
  toggleUnavailableCell,
  toggleUnavailableGroup,
} from './geometry-guard-resolution-state';

interface GeometryGuardResolutionPanelProps {
  readonly api: ImageFolderImportClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly guardJobId: string;
  readonly onManifestInvalidated: () => void;
  readonly onManifestSealed: (
    manifest: ImageGeometryGuardResolutionManifestResponse,
  ) => void;
  readonly uploadId: string;
}

type Disposition = 'corrected_full' | 'partial' | 'rejected';
interface BoardDraft {
  readonly disposition: Disposition;
  readonly dirty: boolean;
  readonly preview: ImageGeometryGuardPreviewResponse | null;
  readonly quad: GuardQuad | null;
  readonly unavailable: readonly number[];
}

const ACTOR = 'local-owner';
const CORNER_LABELS = ['LT', 'PT', 'PD', 'LD'] as const;

function boardKey(sourceChecksum: string, positionIndex: number) {
  return `${sourceChecksum}:${positionIndex}`;
}

function initialBoardDraft(
  board: ImageGeometryGuardBoardContextResponse,
  decision: ImageGeometryGuardDecisionResponse | undefined,
): BoardDraft {
  return {
    disposition: decision?.disposition ?? 'corrected_full',
    dirty: false,
    preview: null,
    quad:
      guardQuadFromUnknown(decision?.symbolGridQuad) ?? initialGuardQuad(board),
    unavailable: decision?.unavailableCellIndices ?? [],
  };
}

function errorCode(error: unknown): string | null {
  return typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string'
    ? error.code
    : null;
}

function sourceAssetUrl(
  apiBaseUrl: string,
  uploadId: string,
  guardJobId: string,
  checksum: string,
  gameId: string,
) {
  const base = resolveAdminApiBaseUrl(apiBaseUrl);
  return `${base}/api/v1/admin/image-imports/browser-selections/${encodeURIComponent(uploadId)}/geometry-guards/${encodeURIComponent(guardJobId)}/sources/${encodeURIComponent(checksum)}/asset?game_id=${encodeURIComponent(gameId)}`;
}

function points(quad: GuardQuad) {
  return quad.map((point) => `${point.x},${point.y}`).join(' ');
}

export function GeometryGuardResolutionPanel({
  api,
  apiBaseUrl,
  gameId,
  guardJobId,
  onManifestInvalidated,
  onManifestSealed,
  uploadId,
}: GeometryGuardResolutionPanelProps) {
  const [queue, setQueue] = useState<ImageGeometryGuardQueueResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reconstructionJob, setReconstructionJob] =
    useState<JobResponse | null>(null);
  const [needsReconstruction, setNeedsReconstruction] = useState(false);
  const [sourceChecksum, setSourceChecksum] = useState<string | null>(null);
  const [selectedPositions, setSelectedPositions] = useState<readonly number[]>(
    [],
  );
  const [activePosition, setActivePosition] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<ReadonlyMap<string, BoardDraft>>(
    () => new Map(),
  );
  const [zoomPercent, setZoomPercent] = useState(100);
  const [imageSize, setImageSize] = useState<{
    readonly width: number;
    readonly height: number;
  } | null>(null);
  const [draggingCorner, setDraggingCorner] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await api.listImageGeometryGuardBoards(
        uploadId,
        guardJobId,
        gameId,
      );
      if (result.error !== undefined || result.data === undefined) {
        if (
          errorCode(result.error) ===
          'IMAGE_GEOMETRY_GUARD_BOARD_REPORT_REQUIRED'
        ) {
          setNeedsReconstruction(true);
          setQueue(null);
          return;
        }
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się pobrać problematycznych plansz.',
          ),
        );
        return;
      }
      setNeedsReconstruction(false);
      setQueue(result.data);
      const resultDecisions = new Map(
        result.data.decisions.map((item) => [
          boardKey(item.sourceChecksumSha256, item.positionIndex),
          item,
        ]),
      );
      setDrafts((current) => {
        const next = new Map(current);
        for (const board of result.data.boards) {
          const key = boardKey(board.sourceChecksumSha256, board.positionIndex);
          const previous = next.get(key);
          if (previous?.dirty) continue;
          next.set(key, initialBoardDraft(board, resultDecisions.get(key)));
        }
        return next;
      });
      const firstChecksum =
        result.data.targets[0]?.sourceChecksumSha256 ?? null;
      setSourceChecksum((current) =>
        current !== null &&
        result.data.targets.some(
          (item) => item.sourceChecksumSha256 === current,
        )
          ? current
          : firstChecksum,
      );
    } catch {
      setError(
        'Połączenie z lokalnym API rozliczania plansz zostało przerwane.',
      );
    } finally {
      setLoading(false);
    }
  }, [api, gameId, guardJobId, uploadId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (
      reconstructionJob === null ||
      !['created', 'processing'].includes(reconstructionJob.status)
    )
      return;
    const timer = window.setInterval(() => {
      void api.getJob(reconstructionJob.id).then((result) => {
        if (result.error === undefined && result.data !== undefined) {
          setReconstructionJob(result.data);
          if (result.data.status === 'completed') void refresh();
        }
      });
    }, 3_000);
    return () => window.clearInterval(timer);
  }, [api, reconstructionJob, refresh]);

  const sources = useMemo(
    () => [
      ...new Set(queue?.targets.map((item) => item.sourceChecksumSha256) ?? []),
    ],
    [queue],
  );
  const sourceTargets = useMemo(
    () =>
      queue?.targets.filter(
        (item) => item.sourceChecksumSha256 === sourceChecksum,
      ) ?? [],
    [queue, sourceChecksum],
  );
  const sourceBoards = useMemo(
    () =>
      queue?.boards.filter(
        (item) => item.sourceChecksumSha256 === sourceChecksum,
      ) ?? [],
    [queue, sourceChecksum],
  );
  const activeBoard =
    sourceBoards.find((item) => item.positionIndex === activePosition) ?? null;
  const decisions = useMemo(
    () =>
      new Map(
        queue?.decisions.map((item) => [
          boardKey(item.sourceChecksumSha256, item.positionIndex),
          item,
        ]) ?? [],
      ),
    [queue],
  );

  useEffect(() => {
    const first = sourceTargets[0] ?? sourceBoards[0] ?? null;
    if (first === null) return;
    const timer = window.setTimeout(() => {
      setActivePosition(first.positionIndex);
      setSelectedPositions([first.positionIndex]);
      setImageSize(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [sourceChecksum, sourceTargets, sourceBoards]);

  const activeDraft =
    activeBoard === null
      ? null
      : (drafts.get(
          boardKey(activeBoard.sourceChecksumSha256, activeBoard.positionIndex),
        ) ?? null);

  function updateDraft(
    positionIndex: number,
    update: (draft: BoardDraft) => BoardDraft,
  ) {
    if (sourceChecksum === null) return;
    const key = boardKey(sourceChecksum, positionIndex);
    setDrafts((current) => {
      const value = current.get(key);
      if (value === undefined) return current;
      const next = new Map(current);
      next.set(key, update(value));
      return next;
    });
  }

  function chooseBoard(positionIndex: number, multiple: boolean) {
    if (multiple) {
      setSelectedPositions((current) =>
        current.includes(positionIndex)
          ? current.filter((value) => value !== positionIndex)
          : [...current, positionIndex].sort((left, right) => left - right),
      );
      setActivePosition(positionIndex);
      return;
    }
    setSelectedPositions([positionIndex]);
    setActivePosition(positionIndex);
  }

  function updateCorner(event: PointerEvent<SVGSVGElement>) {
    if (
      draggingCorner === null ||
      imageSize === null ||
      activeBoard === null ||
      activeDraft?.quad === null ||
      activeDraft === null
    )
      return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const point = {
      x: Math.max(
        0,
        Math.min(
          imageSize.width - 1,
          Math.round(
            ((event.clientX - bounds.left) / bounds.width) * imageSize.width,
          ),
        ),
      ),
      y: Math.max(
        0,
        Math.min(
          imageSize.height - 1,
          Math.round(
            ((event.clientY - bounds.top) / bounds.height) * imageSize.height,
          ),
        ),
      ),
    };
    updateDraft(activeBoard.positionIndex, (current) => ({
      ...current,
      dirty: true,
      preview: null,
      quad:
        current.quad === null
          ? null
          : (current.quad.map((value, index) =>
              index === draggingCorner ? point : value,
            ) as unknown as GuardQuad),
    }));
  }

  async function startReconstruction() {
    if (saving) return;
    setSaving(true);
    setError('');
    try {
      const result = await api.startImageGeometryGuardReportReconstruction(
        uploadId,
        guardJobId,
        gameId,
      );
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się uruchomić rekonstrukcji raportu.',
          ),
        );
        return;
      }
      setReconstructionJob(result.data.job);
      setFeedback(
        result.data.created
          ? 'Rekonstrukcja raportu oczekuje na worker.'
          : 'Przywrócono istniejącą rekonstrukcję raportu.',
      );
    } catch {
      setError('Połączenie z workerem rekonstrukcji zostało przerwane.');
    } finally {
      setSaving(false);
    }
  }

  async function retryReconstruction() {
    if (saving || reconstructionJob === null) return;
    setSaving(true);
    try {
      const result = await api.retryJob(reconstructionJob.id);
      if (result.error !== undefined || result.data === undefined)
        setError(
          apiErrorMessage(result.error, 'Nie udało się ponowić rekonstrukcji.'),
        );
      else setReconstructionJob(result.data);
    } catch {
      setError('Połączenie z workerem rekonstrukcji zostało przerwane.');
    } finally {
      setSaving(false);
    }
  }

  async function renderPreview() {
    if (
      activeBoard === null ||
      activeDraft === null ||
      activeDraft.quad === null ||
      activeDraft.disposition === 'rejected'
    )
      return;
    if (
      activeDraft.disposition === 'partial' &&
      (activeDraft.unavailable.length < 1 ||
        activeDraft.unavailable.length > 14)
    ) {
      setError('Plansza częściowa wymaga od 1 do 14 niedostępnych pól.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const result = await api.previewImageGeometryGuardDecision(
        uploadId,
        guardJobId,
        {
          gameId,
          positionIndex: activeBoard.positionIndex,
          sourceChecksumSha256: activeBoard.sourceChecksumSha256,
          symbolGridQuad: activeDraft.quad.map((point) => ({
            x: Math.round(point.x),
            y: Math.round(point.y),
          })) as [
            PageGeometryPoint,
            PageGeometryPoint,
            PageGeometryPoint,
            PageGeometryPoint,
          ],
          unavailableCellIndices:
            activeDraft.disposition === 'partial'
              ? [...activeDraft.unavailable]
              : [],
        },
      );
      if (result.error !== undefined || result.data === undefined)
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się przygotować podglądu cropów.',
          ),
        );
      else
        updateDraft(activeBoard.positionIndex, (current) => ({
          ...current,
          dirty: true,
          preview: result.data ?? null,
        }));
    } catch {
      setError('Połączenie z podglądem cropów zostało przerwane.');
    } finally {
      setSaving(false);
    }
  }

  async function saveDecision() {
    if (queue === null || sourceChecksum === null || saving) return;
    const changed = sourceBoards
      .map((board) => ({
        board,
        draft: drafts.get(boardKey(sourceChecksum, board.positionIndex)),
      }))
      .filter(
        (item): item is { board: typeof item.board; draft: BoardDraft } =>
          item.draft?.dirty === true,
      );
    const withoutPreview = changed.find(
      ({ draft }) =>
        draft.disposition !== 'rejected' &&
        (draft.quad === null || draft.preview === null),
    );
    if (withoutPreview !== undefined) {
      setActivePosition(withoutPreview.board.positionIndex);
      setSelectedPositions([withoutPreview.board.positionIndex]);
      setError(
        `Plansza ${withoutPreview.board.sequenceNumber} wymaga aktualnego podglądu A/B przed zapisem.`,
      );
      return;
    }
    const payload: ImageGeometryGuardDecisionItemCreate[] = changed.map(
      ({ board, draft }) => ({
        disposition: draft.disposition,
        positionIndex: board.positionIndex,
        reason:
          draft.disposition === 'rejected'
            ? 'cropped_or_unreadable'
            : undefined,
        sequenceNumber: board.sequenceNumber,
        sourceChecksumSha256: board.sourceChecksumSha256,
        symbolGridQuad:
          draft.disposition === 'rejected' || draft.quad === null
            ? undefined
            : (draft.quad.map((point) => ({
                x: Math.round(point.x),
                y: Math.round(point.y),
              })) as [
                PageGeometryPoint,
                PageGeometryPoint,
                PageGeometryPoint,
                PageGeometryPoint,
              ]),
        unavailableCellIndices:
          draft.disposition === 'partial' ? [...draft.unavailable] : [],
      }),
    );
    if (payload.length === 0) {
      setError('Na tym zdjęciu nie ma niezapisanych zmian.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const result = await api.createImageGeometryGuardDecisions(
        uploadId,
        guardJobId,
        {
          actor: ACTOR,
          decisions: payload,
          expectedGuardReportChecksumSha256: queue.guardReportChecksumSha256,
          gameId,
        },
      );
      if (result.error !== undefined || result.data === undefined)
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się zapisać decyzji planszy.',
          ),
        );
      else {
        onManifestInvalidated();
        setFeedback(
          `Zapisano atomowo ${result.data.decisions.length} zmienionych plansz. Historia poprzednich rewizji pozostała zachowana.`,
        );
        await refresh();
      }
    } catch {
      setError('Połączenie podczas zapisu decyzji zostało przerwane.');
    } finally {
      setSaving(false);
    }
  }

  async function sealManifest() {
    if (queue === null || queue.unresolvedCount !== 0 || saving) return;
    setSaving(true);
    setError('');
    try {
      const result = await api.sealImageGeometryGuardResolutionManifest(
        uploadId,
        guardJobId,
        {
          actor: ACTOR,
          expectedGuardReportChecksumSha256: queue.guardReportChecksumSha256,
          gameId,
        },
      );
      if (result.error !== undefined || result.data === undefined)
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się zamknąć manifestu decyzji.',
          ),
        );
      else {
        onManifestSealed(result.data);
        setFeedback(
          `Manifest zamknięty: ${result.data.manifestChecksumSha256.slice(0, 12)}. Import nie został uruchomiony automatycznie.`,
        );
      }
    } catch {
      setError('Połączenie podczas zamykania manifestu zostało przerwane.');
    } finally {
      setSaving(false);
    }
  }

  if (loading)
    return (
      <p className="curatedImportStatus">
        Ładowanie kolejki problematycznych plansz…
      </p>
    );
  if (needsReconstruction)
    return (
      <section className="geometryGuardResolution">
        <p>
          Historyczny raport ma tylko agregaty. Utwórz audytową rekonstrukcję
          v2, aby wskazać dokładne plansze. Failed import pozostanie
          niezmieniony.
        </p>
        {reconstructionJob !== null ? (
          <p className="curatedImportStatus">
            Rekonstrukcja {reconstructionJob.id.slice(0, 8)} ·{' '}
            {reconstructionJob.status}
          </p>
        ) : null}
        <button
          className="secondaryButton"
          disabled={
            saving ||
            reconstructionJob?.status === 'processing' ||
            reconstructionJob?.status === 'created'
          }
          onClick={() =>
            void (reconstructionJob?.status === 'failed'
              ? retryReconstruction()
              : startReconstruction())
          }
          type="button"
        >
          {reconstructionJob?.status === 'failed'
            ? 'Ponów rekonstrukcję raportu'
            : 'Odtwórz diagnostykę plansz'}
        </button>
        {error ? (
          <p className="feedbackBanner feedbackBannerError" role="alert">
            {error}
          </p>
        ) : null}
      </section>
    );
  if (
    queue === null ||
    sourceChecksum === null ||
    activeBoard === null ||
    activeDraft === null
  )
    return (
      <p className="curatedImportStatus">
        Brak plansz wymagających rozliczenia.
      </p>
    );

  const activeSourceIndex = sources.indexOf(sourceChecksum);
  const imageUrl = sourceAssetUrl(
    apiBaseUrl,
    uploadId,
    guardJobId,
    sourceChecksum,
    gameId,
  );
  const existing = decisions.get(
    boardKey(sourceChecksum, activeBoard.positionIndex),
  );
  const dirtyCount = sourceBoards.filter(
    (board) =>
      drafts.get(boardKey(sourceChecksum, board.positionIndex))?.dirty === true,
  ).length;
  return (
    <section
      className="geometryGuardResolution"
      aria-label="Rozlicz problematyczne plansze"
    >
      <header className="pageGeometryCorrectionHeader">
        <div>
          <h3>Rozlicz problematyczne plansze</h3>
          <p>
            Źródło {activeSourceIndex + 1}/{sources.length}:{' '}
            {activeBoard.sourceRelativePath}. Każdą siatkę można poprawić;
            czerwone wymagają decyzji.
          </p>
        </div>
        <strong>{queue.unresolvedCount} nierozliczonych</strong>
      </header>
      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {feedback ? (
        <p className="feedbackBanner" role="status">
          {feedback}
        </p>
      ) : null}
      <div className="geometryGuardSourceNav">
        <button
          className="secondaryButton"
          disabled={saving || activeSourceIndex <= 0}
          onClick={() =>
            setSourceChecksum(sources[activeSourceIndex - 1] ?? sourceChecksum)
          }
          type="button"
        >
          Poprzednie zdjęcie
        </button>
        <button
          className="secondaryButton"
          disabled={saving || activeSourceIndex >= sources.length - 1}
          onClick={() =>
            setSourceChecksum(sources[activeSourceIndex + 1] ?? sourceChecksum)
          }
          type="button"
        >
          Następne zdjęcie
        </button>
        <span className="geometryGuardZoom" aria-label="Powiększenie zdjęcia">
          <button
            className="secondaryButton"
            disabled={saving || zoomPercent <= 75}
            onClick={() => setZoomPercent((value) => Math.max(75, value - 25))}
            type="button"
          >
            −
          </button>
          <strong>{zoomPercent}%</strong>
          <button
            className="secondaryButton"
            disabled={saving || zoomPercent >= 300}
            onClick={() => setZoomPercent((value) => Math.min(300, value + 25))}
            type="button"
          >
            +
          </button>
        </span>
      </div>
      <div className="geometryGuardWorkspace">
        <div className="geometryGuardCanvasViewport">
          <div
            className="geometryGuardCanvas"
            style={{ width: `${zoomPercent}%` }}
          >
            <img
              alt={`Źródło wyjątków: ${activeBoard.sourceRelativePath}`}
              onLoad={(event) =>
                setImageSize({
                  width: event.currentTarget.naturalWidth,
                  height: event.currentTarget.naturalHeight,
                })
              }
              onError={() =>
                setError(
                  'Nie udało się wczytać checksumowanego zdjęcia ze stagingu.',
                )
              }
              src={imageUrl}
            />
            {imageSize !== null ? (
              <svg
                onPointerMove={updateCorner}
                onPointerUp={() => setDraggingCorner(null)}
                viewBox={`0 0 ${imageSize.width} ${imageSize.height}`}
              >
                {sourceBoards.map((board) => {
                  const boardDraft = drafts.get(
                    boardKey(sourceChecksum, board.positionIndex),
                  );
                  const boardQuad =
                    boardDraft?.quad ??
                    guardQuadFromUnknown(board.symbolGridQuad) ??
                    guardQuadFromUnknown(board.pageGeometry);
                  if (boardQuad === null) return null;
                  return (
                    <g
                      key={board.positionIndex}
                      onClick={() => chooseBoard(board.positionIndex, false)}
                    >
                      <polygon
                        className={`geometryGuardBoard${
                          board.requiresDecision
                            ? ' geometryGuardBoardRequired'
                            : ''
                        }${
                          board.positionIndex === activeBoard.positionIndex
                            ? ' geometryGuardBoardActive'
                            : ''
                        }${boardDraft?.dirty ? ' geometryGuardBoardDirty' : ''}`}
                        points={points(boardQuad)}
                      />
                      <text
                        className="geometryGuardBoardNumber"
                        x={(boardQuad[0].x + boardQuad[2].x) / 2}
                        y={(boardQuad[0].y + boardQuad[2].y) / 2}
                      >
                        {board.positionIndex + 1}
                      </text>
                    </g>
                  );
                })}
                {activeDraft.quad !== null ? (
                  <g>
                    {
                      <polygon
                        className="geometryGuardGrid"
                        points={points(activeDraft.quad)}
                      />
                    }
                    {guardGridLines(activeDraft.quad).map((line, index) => (
                      <line
                        className="geometryGuardGridLine"
                        key={index}
                        x1={line[0].x}
                        x2={line[1].x}
                        y1={line[0].y}
                        y2={line[1].y}
                      />
                    ))}
                    {activeDraft.quad.map((point, index) => (
                      <g key={CORNER_LABELS[index]}>
                        <circle
                          className="geometryGuardHandle"
                          cx={point.x}
                          cy={point.y}
                          onPointerDown={(event) => {
                            event.stopPropagation();
                            event.currentTarget.ownerSVGElement?.setPointerCapture(
                              event.pointerId,
                            );
                            setDraggingCorner(index);
                          }}
                          r={7}
                        />
                        <text
                          className="geometryGuardCornerLabel"
                          x={point.x + 9}
                          y={point.y - 9}
                        >
                          {CORNER_LABELS[index]}
                        </text>
                      </g>
                    ))}
                  </g>
                ) : null}
              </svg>
            ) : null}
          </div>
        </div>
        <div className="geometryGuardControls">
          <fieldset>
            <legend>Plansze na zdjęciu</legend>
            {sourceBoards.map((board) => {
              const decision = decisions.get(
                boardKey(sourceChecksum, board.positionIndex),
              );
              const boardDraft = drafts.get(
                boardKey(sourceChecksum, board.positionIndex),
              );
              return (
                <label key={board.positionIndex}>
                  <input
                    checked={selectedPositions.includes(board.positionIndex)}
                    onChange={() =>
                      chooseBoard(
                        board.positionIndex,
                        activeDraft.disposition === 'rejected',
                      )
                    }
                    type="checkbox"
                  />{' '}
                  #{board.positionIndex + 1} · {board.sequenceNumber}{' '}
                  {decision
                    ? `· ${decision.disposition} r${decision.revision}`
                    : board.requiresDecision
                      ? '· wymaga decyzji'
                      : '· wynik automatu'}
                  {boardDraft?.dirty ? ' · zmieniona' : ''}
                </label>
              );
            })}
          </fieldset>
          <fieldset>
            <legend>Decyzja dla planszy {activeBoard.sequenceNumber}</legend>
            <label>
              <input
                checked={activeDraft.disposition === 'corrected_full'}
                onChange={() => {
                  updateDraft(activeBoard.positionIndex, (current) => ({
                    ...current,
                    dirty: true,
                    disposition: 'corrected_full',
                    preview: null,
                    unavailable: [],
                  }));
                  setSelectedPositions([activeBoard.positionIndex]);
                }}
                type="radio"
              />{' '}
              Popraw pełną siatkę
            </label>
            <label>
              <input
                checked={activeDraft.disposition === 'partial'}
                onChange={() => {
                  updateDraft(activeBoard.positionIndex, (current) => ({
                    ...current,
                    dirty: true,
                    disposition: 'partial',
                    preview: null,
                  }));
                  setSelectedPositions([activeBoard.positionIndex]);
                }}
                type="radio"
              />{' '}
              Oznacz jako częściową
            </label>
            <label>
              <input
                checked={activeDraft.disposition === 'rejected'}
                onChange={() => {
                  const positions = selectedPositions.includes(
                    activeBoard.positionIndex,
                  )
                    ? selectedPositions
                    : [activeBoard.positionIndex];
                  for (const position of positions) {
                    updateDraft(position, (current) => ({
                      ...current,
                      dirty: true,
                      disposition: 'rejected',
                      preview: null,
                    }));
                  }
                }}
                type="radio"
              />{' '}
              Odrzuć jako nieczytelną
            </label>
          </fieldset>
          <p className="curatedImportStatus">
            {activeBoard.requiresDecision
              ? `Powody bramki: ${activeBoard.reasonCodes.join(', ')}`
              : 'Plansza przeszła automat, ale możesz jawnie poprawić jej siatkę.'}
            {existing ? ` · ostatnia rewizja ${existing.revision}` : ''}
          </p>
          {activeDraft.disposition === 'partial' ? (
            <div className="geometryGuardMask">
              <p>
                Kliknij brakujące pola (1–14). „?” oznacza source_unavailable.
              </p>
              <div className="geometryGuardCellButtons">
                {Array.from({ length: 15 }, (_, index) => (
                  <button
                    aria-pressed={activeDraft.unavailable.includes(index)}
                    key={index}
                    onClick={() => {
                      updateDraft(activeBoard.positionIndex, (current) => ({
                        ...current,
                        dirty: true,
                        preview: null,
                        unavailable: toggleUnavailableCell(
                          current.unavailable,
                          index,
                        ),
                      }));
                    }}
                    type="button"
                  >
                    {activeDraft.unavailable.includes(index) ? '?' : index + 1}
                  </button>
                ))}
              </div>
              <div className="geometryGuardGroupButtons">
                {Array.from({ length: 3 }, (_, row) => (
                  <button
                    className="secondaryButton"
                    key={`r${row}`}
                    onClick={() => {
                      updateDraft(activeBoard.positionIndex, (current) => ({
                        ...current,
                        dirty: true,
                        preview: null,
                        unavailable: toggleUnavailableGroup(
                          current.unavailable,
                          Array.from(
                            { length: 5 },
                            (_value, column) => row * 5 + column,
                          ),
                        ),
                      }));
                    }}
                    type="button"
                  >
                    Rząd {row + 1}
                  </button>
                ))}
                {Array.from({ length: 5 }, (_, column) => (
                  <button
                    className="secondaryButton"
                    key={`c${column}`}
                    onClick={() => {
                      updateDraft(activeBoard.positionIndex, (current) => ({
                        ...current,
                        dirty: true,
                        preview: null,
                        unavailable: toggleUnavailableGroup(
                          current.unavailable,
                          [column, column + 5, column + 10],
                        ),
                      }));
                    }}
                    type="button"
                  >
                    Kol. {column + 1}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div className="importActionButtons">
            {activeDraft.disposition !== 'rejected' ? (
              <button
                className="secondaryButton"
                disabled={saving || activeDraft.quad === null}
                onClick={() => void renderPreview()}
                type="button"
              >
                Generuj podgląd A/B
              </button>
            ) : null}
            <button
              className="primaryButton"
              disabled={saving || dirtyCount === 0}
              onClick={() => void saveDecision()}
              type="button"
            >
              {saving ? 'Zapisywanie…' : `Zapisz decyzję (${dirtyCount})`}
            </button>
          </div>
        </div>
      </div>
      {activeDraft.preview !== null ? (
        <section className="geometryGuardPreview">
          <h4>Podgląd 15 cropów A/B</h4>
          <div className="geometryGuardPreviewGrid">
            {activeDraft.preview.cells.map((cell) => (
              <article key={cell.cellIndex}>
                <strong>{cell.cellIndex + 1}</strong>
                {cell.sourceUnavailable ? (
                  <span className="geometryGuardUnavailable">?</span>
                ) : (
                  <>
                    <div>
                      <small>Propozycja</small>
                      {cell.proposedDataUrl ? (
                        <img
                          alt={`Propozycja pola ${cell.cellIndex + 1}`}
                          src={cell.proposedDataUrl}
                        />
                      ) : (
                        <span>brak</span>
                      )}
                    </div>
                    <div>
                      <small>Po korekcie</small>
                      {cell.currentDataUrl ? (
                        <img
                          alt={`Korekta pola ${cell.cellIndex + 1}`}
                          src={cell.currentDataUrl}
                        />
                      ) : null}
                    </div>
                  </>
                )}
              </article>
            ))}
          </div>
        </section>
      ) : null}
      <footer className="geometryGuardSeal">
        <p>
          {queue.unresolvedCount === 0
            ? 'Wszystkie błędy mają jawne decyzje. Możesz zamknąć niezmienny manifest.'
            : `Pozostało ${queue.unresolvedCount} plansz. Zamknięcie manifestu jest zablokowane.`}
        </p>
        <button
          className="primaryButton"
          disabled={saving || queue.unresolvedCount !== 0}
          onClick={() => void sealManifest()}
          type="button"
        >
          Zamknij manifest decyzji
        </button>
      </footer>
    </section>
  );
}
