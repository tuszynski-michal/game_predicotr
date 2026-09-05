'use client';

/* Staged source assets are checksum-bound local images and bypass Next optimization. */
/* eslint-disable @next/next/no-img-element */

import type {
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
const ACTOR = 'local-owner';
const CORNER_LABELS = ['LT', 'PT', 'PD', 'LD'] as const;

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
  const [disposition, setDisposition] = useState<Disposition>('corrected_full');
  const [quad, setQuad] = useState<GuardQuad | null>(null);
  const [unavailable, setUnavailable] = useState<readonly number[]>([]);
  const [preview, setPreview] =
    useState<ImageGeometryGuardPreviewResponse | null>(null);
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
    void refresh();
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
  const activeTarget =
    sourceTargets.find((item) => item.positionIndex === activePosition) ?? null;
  const decisions = useMemo(
    () =>
      new Map(
        queue?.decisions.map((item) => [
          `${item.sourceChecksumSha256}:${item.positionIndex}`,
          item,
        ]) ?? [],
      ),
    [queue],
  );

  useEffect(() => {
    const first = sourceTargets[0] ?? null;
    const target = first;
    if (target === null) return;
    setActivePosition(target.positionIndex);
    setSelectedPositions([target.positionIndex]);
    const existing = decisions.get(
      `${target.sourceChecksumSha256}:${target.positionIndex}`,
    );
    const existingQuad = guardQuadFromUnknown(existing?.symbolGridQuad);
    setDisposition(existing?.disposition ?? 'corrected_full');
    setQuad(existingQuad ?? initialGuardQuad(target));
    setUnavailable(existing?.unavailableCellIndices ?? []);
    setPreview(null);
    setImageSize(null);
  }, [decisions, sourceChecksum, sourceTargets]);

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
    const target = sourceTargets.find(
      (item) => item.positionIndex === positionIndex,
    );
    if (target === undefined) return;
    const existing = decisions.get(
      `${target.sourceChecksumSha256}:${positionIndex}`,
    );
    setDisposition(existing?.disposition ?? 'corrected_full');
    setQuad(
      guardQuadFromUnknown(existing?.symbolGridQuad) ??
        initialGuardQuad(target),
    );
    setUnavailable(existing?.unavailableCellIndices ?? []);
    setPreview(null);
  }

  function updateCorner(event: PointerEvent<SVGSVGElement>) {
    if (draggingCorner === null || imageSize === null || quad === null) return;
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
    setQuad((current) =>
      current === null
        ? current
        : (current.map((value, index) =>
            index === draggingCorner ? point : value,
          ) as unknown as GuardQuad),
    );
    setPreview(null);
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
    if (activeTarget === null || quad === null || disposition === 'rejected')
      return;
    if (
      disposition === 'partial' &&
      (unavailable.length < 1 || unavailable.length > 14)
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
          positionIndex: activeTarget.positionIndex,
          sourceChecksumSha256: activeTarget.sourceChecksumSha256,
          symbolGridQuad: quad.map((point) => ({
            x: Math.round(point.x),
            y: Math.round(point.y),
          })) as [
            PageGeometryPoint,
            PageGeometryPoint,
            PageGeometryPoint,
            PageGeometryPoint,
          ],
          unavailableCellIndices:
            disposition === 'partial' ? [...unavailable] : [],
        },
      );
      if (result.error !== undefined || result.data === undefined)
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się przygotować podglądu cropów.',
          ),
        );
      else setPreview(result.data);
    } catch {
      setError('Połączenie z podglądem cropów zostało przerwane.');
    } finally {
      setSaving(false);
    }
  }

  async function saveDecision() {
    if (queue === null || activeTarget === null || saving) return;
    let payload: ImageGeometryGuardDecisionItemCreate[];
    if (disposition === 'rejected') {
      payload = sourceTargets
        .filter((item) => selectedPositions.includes(item.positionIndex))
        .map((item) => ({
          disposition: 'rejected',
          positionIndex: item.positionIndex,
          reason: 'cropped_or_unreadable',
          sequenceNumber: item.sequenceNumber,
          sourceChecksumSha256: item.sourceChecksumSha256,
        }));
    } else {
      if (quad === null || preview === null) {
        setError(
          'Przed zapisem pełnej lub częściowej siatki wygeneruj aktualny podgląd A/B.',
        );
        return;
      }
      payload = [
        {
          disposition,
          positionIndex: activeTarget.positionIndex,
          sequenceNumber: activeTarget.sequenceNumber,
          sourceChecksumSha256: activeTarget.sourceChecksumSha256,
          symbolGridQuad: quad.map((point) => ({
            x: Math.round(point.x),
            y: Math.round(point.y),
          })) as [
            PageGeometryPoint,
            PageGeometryPoint,
            PageGeometryPoint,
            PageGeometryPoint,
          ],
          unavailableCellIndices:
            disposition === 'partial' ? [...unavailable] : [],
        },
      ];
    }
    if (payload.length === 0) {
      setError('Zaznacz co najmniej jedną planszę z tego zdjęcia.');
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
          `Zapisano ${result.data.decisions.length} decyzji. Historia poprzednich rewizji pozostała zachowana.`,
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
  if (queue === null || sourceChecksum === null || activeTarget === null)
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
    `${sourceChecksum}:${activeTarget.positionIndex}`,
  );
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
            {activeTarget.sourceRelativePath}. Wszystkie 9 slotów są widoczne;
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
      </div>
      <div className="geometryGuardWorkspace">
        <div className="geometryGuardCanvas">
          <img
            alt={`Źródło wyjątków: ${activeTarget.sourceRelativePath}`}
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
                const boardQuad = guardQuadFromUnknown(board.pageGeometry);
                if (boardQuad === null) return null;
                return (
                  <g
                    key={board.positionIndex}
                    onClick={() =>
                      board.requiresDecision &&
                      chooseBoard(board.positionIndex, false)
                    }
                  >
                    <polygon
                      className={
                        board.requiresDecision
                          ? 'geometryGuardBoard geometryGuardBoardRequired'
                          : 'geometryGuardBoard'
                      }
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
              {quad !== null ? (
                <g>
                  {
                    <polygon
                      className="geometryGuardGrid"
                      points={points(quad)}
                    />
                  }
                  {guardGridLines(quad).map((line, index) => (
                    <line
                      className="geometryGuardGridLine"
                      key={index}
                      x1={line[0].x}
                      x2={line[1].x}
                      y1={line[0].y}
                      y2={line[1].y}
                    />
                  ))}
                  {quad.map((point, index) => (
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
        <div className="geometryGuardControls">
          <fieldset>
            <legend>Plansze wymagające decyzji</legend>
            {sourceTargets.map((target) => {
              const decision = decisions.get(
                `${sourceChecksum}:${target.positionIndex}`,
              );
              return (
                <label key={target.positionIndex}>
                  <input
                    checked={selectedPositions.includes(target.positionIndex)}
                    onChange={() =>
                      chooseBoard(
                        target.positionIndex,
                        disposition === 'rejected',
                      )
                    }
                    type="checkbox"
                  />{' '}
                  #{target.positionIndex + 1} · {target.sequenceNumber}{' '}
                  {decision
                    ? `· ${decision.disposition} r${decision.revision}`
                    : '· nierozliczona'}
                </label>
              );
            })}
          </fieldset>
          <fieldset>
            <legend>Decyzja dla planszy {activeTarget.sequenceNumber}</legend>
            <label>
              <input
                checked={disposition === 'corrected_full'}
                onChange={() => {
                  chooseBoard(activeTarget.positionIndex, false);
                  setDisposition('corrected_full');
                  setUnavailable([]);
                  setPreview(null);
                  setSelectedPositions([activeTarget.positionIndex]);
                }}
                type="radio"
              />{' '}
              Popraw pełną siatkę
            </label>
            <label>
              <input
                checked={disposition === 'partial'}
                onChange={() => {
                  chooseBoard(activeTarget.positionIndex, false);
                  setDisposition('partial');
                  setPreview(null);
                  setSelectedPositions([activeTarget.positionIndex]);
                }}
                type="radio"
              />{' '}
              Oznacz jako częściową
            </label>
            <label>
              <input
                checked={disposition === 'rejected'}
                onChange={() => {
                  setDisposition('rejected');
                  setPreview(null);
                }}
                type="radio"
              />{' '}
              Odrzuć jako nieczytelną
            </label>
          </fieldset>
          <p className="curatedImportStatus">
            Powody bramki: {activeTarget.reasonCodes.join(', ')}
            {existing ? ` · ostatnia rewizja ${existing.revision}` : ''}
          </p>
          {disposition === 'partial' ? (
            <div className="geometryGuardMask">
              <p>
                Kliknij brakujące pola (1–14). „?” oznacza source_unavailable.
              </p>
              <div className="geometryGuardCellButtons">
                {Array.from({ length: 15 }, (_, index) => (
                  <button
                    aria-pressed={unavailable.includes(index)}
                    key={index}
                    onClick={() => {
                      setUnavailable(toggleUnavailableCell(unavailable, index));
                      setPreview(null);
                    }}
                    type="button"
                  >
                    {unavailable.includes(index) ? '?' : index + 1}
                  </button>
                ))}
              </div>
              <div className="geometryGuardGroupButtons">
                {Array.from({ length: 3 }, (_, row) => (
                  <button
                    className="secondaryButton"
                    key={`r${row}`}
                    onClick={() => {
                      setUnavailable(
                        toggleUnavailableGroup(
                          unavailable,
                          Array.from(
                            { length: 5 },
                            (_value, column) => row * 5 + column,
                          ),
                        ),
                      );
                      setPreview(null);
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
                      setUnavailable(
                        toggleUnavailableGroup(unavailable, [
                          column,
                          column + 5,
                          column + 10,
                        ]),
                      );
                      setPreview(null);
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
            {disposition !== 'rejected' ? (
              <button
                className="secondaryButton"
                disabled={saving || quad === null}
                onClick={() => void renderPreview()}
                type="button"
              >
                Generuj podgląd A/B
              </button>
            ) : null}
            <button
              className="primaryButton"
              disabled={
                saving || (disposition !== 'rejected' && preview === null)
              }
              onClick={() => void saveDecision()}
              type="button"
            >
              {saving
                ? 'Zapisywanie…'
                : disposition === 'rejected' && selectedPositions.length > 1
                  ? `Odrzuć ${selectedPositions.length} plansze`
                  : 'Zapisz decyzję'}
            </button>
          </div>
        </div>
      </div>
      {preview !== null ? (
        <section className="geometryGuardPreview">
          <h4>Podgląd 15 cropów A/B</h4>
          <div className="geometryGuardPreviewGrid">
            {preview.cells.map((cell) => (
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
