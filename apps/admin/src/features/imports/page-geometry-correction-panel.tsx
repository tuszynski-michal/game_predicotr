'use client';

/* Geometry previews are checksum-bound local assets and must bypass Next image optimization. */
/* eslint-disable @next/next/no-img-element */

import type {
  AdminApiClient,
  BrowserPageGeometryOverrideCreate,
  BrowserPageGeometryReviewSourceResponse,
  BrowserReadySelectionResponse,
  GeometryEngineVariant,
} from '@game-predictor/admin-api-client';
import { fitManualImageToViewport } from '@game-predictor/manual-image-selection-core';
import {
  automaticUnavailableGridCells,
  completeManualGridFlags,
  manualGridCellPolygons,
  manualGridFlagsFromQualification,
  manualGridQualification,
  manualGridUnavailable,
  manualGridVerticalCropWarning,
  type ManualGridFlags,
} from '@game-predictor/manual-image-selection-core/manual-grid-qualification';
import {
  clearPageGeometryDraft,
  clearCommittedPageGeometryDraft,
  readPageGeometryDraft,
  writePageGeometryDraft,
  serializePageGeometryDraft,
  pageGeometryDraftKey,
  type PageGeometryDraftScope,
} from './page-geometry-draft-storage';
import {
  type PointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { resolveAdminApiBaseUrl } from '@/config/admin-api';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  choosePageGeometryCutFolder,
  checksumPageGeometryFile,
  pendingReplacementMatchesSource,
  replacePageGeometryCutSource,
  verifyPageGeometryCutSource,
  type PendingPageGeometryReplacement,
} from './page-geometry-source-replacement';

import {
  appendPageGeometryBoardCorner,
  appendPageGeometryCorner,
  applyPageGeometryMeshOverrides,
  completePageGeometryBoardQuads,
  completePageGeometryCorners,
  createPageGeometryMesh,
  isPageGeometryMeshBoundaryPoint,
  PAGE_BOARD_CORNER_COUNT,
  PAGE_BOARD_COUNT,
  pageGeometryPointFromRenderedCanvas,
  pageGeometryMeshFromQuads,
  pageGeometryQuadsFromCornerPlacement,
  pageGeometryQuadsFromMesh,
  pageGeometrySymbolCutLines,
  type PageGeometryCorners,
  type PageGeometryPoint,
  type PageGeometryQuad,
} from './page-geometry-mesh';
import {
  v12FrameFromGrid,
  v12PreviewFrameFromGrid,
  v12OffsetsFromPair,
  validV12FrameOffsets,
  type V12OffsetDraft,
} from './page-geometry-v12-offsets';

type GeometryCorrectionClient = Pick<
  AdminApiClient,
  | 'createBrowserPageGeometryOverride'
  | 'excludeBrowserPageGeometrySource'
  | 'replaceUnconfirmedBrowserPageGeometrySource'
  | 'confirmBrowserPageGeometrySourceReplacement'
  | 'discardBrowserPageGeometrySourceReplacement'
  | 'listBrowserPageGeometryReviewSources'
>;

type Point = PageGeometryPoint;
type Quad = PageGeometryQuad;
type PageCorners = PageGeometryCorners;
type CorrectionMode = 'curve' | 'page' | number;

interface PageGeometryCorrectionPanelProps {
  readonly allowOutsideSource?: boolean;
  readonly allowRegisteredSourceInspection?: boolean;
  readonly api: GeometryCorrectionClient;
  readonly apiBaseUrl: string;
  readonly focusSourceChecksumSha256?: string;
  readonly initialReplacementSource?: BrowserPageGeometryReviewSourceResponse;
  readonly gameId: string;
  readonly geometryEngineVariant?: GeometryEngineVariant;
  readonly onPendingSourceCountChange?: (count: number) => void;
  readonly onDraftSaved?: () => void;
  readonly onSubmitSaved: () => Promise<void>;
  readonly onSourceReplaced: (
    ready: BrowserReadySelectionResponse,
    replacementChecksumSha256: string,
    source: BrowserPageGeometryReviewSourceResponse,
  ) => Promise<void>;
  readonly preflightJobId: string;
  readonly uploadId: string;
}

const HANDLE_SCREEN_RADIUS = 7;
const MIN_GEOMETRY_ZOOM = 1;
const MAX_GEOMETRY_ZOOM = 30;
const GEOMETRY_ZOOM_STEP = 0.25;
const OUTSIDE_SOURCE_AREA_RATIO = 0.3;
const OUTSIDE_SOURCE_VIEWPORT_SCALE = Math.sqrt(1 + OUTSIDE_SOURCE_AREA_RATIO);
const OUTSIDE_SOURCE_MARGIN_RATIO = (OUTSIDE_SOURCE_VIEWPORT_SCALE - 1) / 2;
const OUTSIDE_SOURCE_IMAGE_START_PERCENT =
  (OUTSIDE_SOURCE_MARGIN_RATIO / OUTSIDE_SOURCE_VIEWPORT_SCALE) * 100;
const OUTSIDE_SOURCE_IMAGE_SIZE_PERCENT = 100 / OUTSIDE_SOURCE_VIEWPORT_SCALE;
const CORNER_LABELS = ['LT', 'PT', 'PD', 'LD'] as const;
const CORNER_NAMES = [
  'lewy górny',
  'prawy górny',
  'prawy dolny',
  'lewy dolny',
] as const;

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, Math.round(value)));
}

function outsideSourceMinimum(size: number) {
  return -size * OUTSIDE_SOURCE_MARGIN_RATIO;
}

function outsideSourceMaximum(size: number) {
  return size * (1 + OUTSIDE_SOURCE_MARGIN_RATIO);
}

function initialCorners(width: number, height: number): PageCorners {
  const horizontal = Math.max(2, Math.round(width * 0.08));
  const vertical = Math.max(2, Math.round(height * 0.08));
  return [
    { x: horizontal, y: vertical },
    { x: width - horizontal, y: vertical },
    { x: width - horizontal, y: height - vertical },
    { x: horizontal, y: height - vertical },
  ];
}

function existingSourceQuads(
  source: BrowserPageGeometryReviewSourceResponse,
): readonly Quad[] {
  const raw = source.existingFinalQuads;
  if (
    raw === null ||
    raw === undefined ||
    raw.length < 1 ||
    raw.length > source.expectedBoardCount ||
    raw.some((quad) => quad.length !== 4)
  ) {
    return [];
  }
  return raw.map((quad) => [quad[0]!, quad[1]!, quad[2]!, quad[3]!] as Quad);
}

function existingV12Quads(
  source: BrowserPageGeometryReviewSourceResponse,
  layer: 'boardFrame' | 'symbolGrid',
): readonly Quad[] {
  const raw =
    layer === 'boardFrame'
      ? source.existingBoardFrameQuads
      : source.existingSymbolGridQuads;
  if (
    raw === null ||
    raw === undefined ||
    raw.length < 1 ||
    raw.length > source.expectedBoardCount ||
    raw.some((quad) => quad.length !== 4)
  ) {
    return [];
  }
  return raw.map((quad) => [quad[0]!, quad[1]!, quad[2]!, quad[3]!] as Quad);
}

function expandedFrameQuad(quad: Quad, width: number, height: number): Quad {
  const center = quad.reduce(
    (value, point) => ({ x: value.x + point.x / 4, y: value.y + point.y / 4 }),
    { x: 0, y: 0 },
  );
  const expanded = quad.map((point) => ({
    x: clamp(center.x + (point.x - center.x) * 1.08, 0, width - 1),
    y: clamp(center.y + (point.y - center.y) * 1.08, 0, height - 1),
  }));
  return [expanded[0]!, expanded[1]!, expanded[2]!, expanded[3]!];
}

function outerCornersFromQuads(quads: readonly Quad[]): PageCorners | null {
  if (quads.length !== 9) return null;
  return [quads[0]![0], quads[2]![1], quads[8]![2], quads[6]![3]];
}

function sourceAssetUrl(
  apiBaseUrl: string,
  uploadId: string,
  sourceChecksumSha256: string,
  gameId: string,
) {
  const base = resolveAdminApiBaseUrl(apiBaseUrl);
  const encodedUpload = encodeURIComponent(uploadId);
  const encodedChecksum = encodeURIComponent(sourceChecksumSha256);
  const encodedGame = encodeURIComponent(gameId);
  return `${base}/api/v1/admin/image-imports/browser-selections/${encodedUpload}/page-geometry-sources/${encodedChecksum}/asset?game_id=${encodedGame}`;
}

function pointText(point: Point) {
  return `${Math.round(point.x)},${Math.round(point.y)}`;
}

const GEOMETRY_REJECTION_LABELS: Readonly<Record<string, string>> = {
  PAGE_GEOMETRY_BOOTSTRAP_ANCHOR_REQUIRED:
    'Brakuje zweryfikowanej strony wzorcowej dla tego ujęcia.',
  PAGE_GEOMETRY_HOMOGRAPHY_INVALID:
    'Nie udało się wyznaczyć stabilnego przekształcenia perspektywy.',
  PAGE_GEOMETRY_INLIER_EVIDENCE_INSUFFICIENT:
    'Za mało dopasowanych punktów potwierdziło tę samą perspektywę.',
  PAGE_GEOMETRY_MATCHES_INSUFFICIENT:
    'Zdjęcie ma za mało zgodnych punktów ze stronami wzorcowymi.',
  PAGE_GEOMETRY_QUADS_INVALID:
    'Przeniesione obrysy plansz nie utworzyły poprawnej siatki 3 × 3.',
  PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT:
    'Co najmniej jedna plansza nie ma wystarczającego potwierdzenia czerwonej ramki.',
  PAGE_GEOMETRY_REPROJECTION_ERROR_EXCESSIVE:
    'Dopasowane punkty mają zbyt duży błąd po transformacji.',
  PAGE_GEOMETRY_TARGET_FEATURES_INSUFFICIENT:
    'Na zdjęciu znaleziono za mało stabilnych punktów obrazu.',
};

function rejectionLabel(reasonCode: string | null | undefined) {
  if (reasonCode === null || reasonCode === undefined) {
    return 'Szczegółowa przyczyna nie została zapisana.';
  }
  return (
    GEOMETRY_REJECTION_LABELS[reasonCode] ?? `Powód techniczny: ${reasonCode}`
  );
}

function diagnosticMetric(label: string, value: number | null | undefined) {
  return value === null || value === undefined ? null : (
    <li>
      {label}: {Number.isInteger(value) ? value : value.toFixed(3)}
    </li>
  );
}

export function PageGeometryCorrectionPanel(
  props: PageGeometryCorrectionPanelProps,
) {
  return (
    <PageGeometryCorrectionPanelContent
      key={`${props.gameId}:${props.uploadId}:${props.preflightJobId}`}
      {...props}
    />
  );
}

function PageGeometryCorrectionPanelContent({
  allowOutsideSource: outsideSourceOverride = false,
  allowRegisteredSourceInspection = false,
  api,
  apiBaseUrl,
  focusSourceChecksumSha256,
  initialReplacementSource,
  gameId,
  geometryEngineVariant,
  onPendingSourceCountChange,
  onDraftSaved,
  onSubmitSaved,
  onSourceReplaced,
  preflightJobId,
  uploadId,
}: PageGeometryCorrectionPanelProps) {
  const [sources, setSources] = useState<
    readonly BrowserPageGeometryReviewSourceResponse[]
  >([]);
  const [sourceIndex, setSourceIndex] = useState(0);
  const [imageSize, setImageSize] = useState<{
    height: number;
    width: number;
  } | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [viewportSize, setViewportSize] = useState<{
    height: number;
    width: number;
  } | null>(null);
  const [zoom, setZoom] = useState(MIN_GEOMETRY_ZOOM);
  const [pageCorners, setPageCorners] = useState<PageCorners | null>(null);
  const [initialPageCorners, setInitialPageCorners] =
    useState<PageCorners | null>(null);
  const [initialBoardOverrides, setInitialBoardOverrides] = useState<
    ReadonlyMap<number, Quad>
  >(new Map());
  const [cornerPlacement, setCornerPlacement] = useState<
    readonly Point[] | null
  >(null);
  const [boardCornerPlacement, setBoardCornerPlacement] = useState<
    readonly Point[] | null
  >(null);
  const [meshOverrides, setMeshOverrides] = useState<
    ReadonlyMap<number, Point>
  >(new Map());
  const [boardOverrides, setBoardOverrides] = useState<
    ReadonlyMap<number, Quad>
  >(new Map());
  const [v12BoardFrameQuads, setV12BoardFrameQuads] = useState<
    readonly Quad[] | null
  >(null);
  const [v12SymbolGridQuads, setV12SymbolGridQuads] = useState<
    readonly Quad[] | null
  >(null);
  const [v12FrameOffsets, setV12FrameOffsets] = useState<
    readonly (V12OffsetDraft | null)[]
  >([]);
  const [v12LegacyPairConfirmed, setV12LegacyPairConfirmed] = useState(false);
  const [correctionMode, setCorrectionMode] = useState<CorrectionMode>('page');
  const [dragging, setDragging] = useState<
    | {
        readonly kind: 'board';
        readonly pointIndex: number;
        readonly boardIndex: number;
      }
    | { readonly kind: 'mesh'; readonly pointIndex: number }
    | { readonly kind: 'page'; readonly pointIndex: number }
    | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [excluding, setExcluding] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [cutFolder, setCutFolder] = useState<FileSystemDirectoryHandle | null>(
    null,
  );
  const [pendingReplacement, setPendingReplacement] =
    useState<PendingPageGeometryReplacement | null>(null);
  const [storageReady, setStorageReady] = useState(false);
  const replacementInputRef = useRef<HTMLInputElement | null>(null);
  const inspectionInputRef = useRef<HTMLInputElement | null>(null);
  const [inspectionSourceChecksumSha256, setInspectionSourceChecksumSha256] =
    useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [savedCount, setSavedCount] = useState(0);
  const [geometryManifestChecksum, setGeometryManifestChecksum] = useState('');
  const [partialTrainingPool, setPartialTrainingPool] = useState({
    readyPatterns: 0,
    samples: 0,
    sources: 0,
  });
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [qualificationFlags, setQualificationFlags] = useState<
    readonly ManualGridFlags[]
  >([]);
  const [draftConflict, setDraftConflict] = useState(false);
  const loadedDraftKey = useRef<string | null>(null);
  const lastPersistedDraft = useRef<string | null>(null);
  const [loadedSourceChecksum, setLoadedSourceChecksum] = useState<
    string | null
  >(null);
  const allowOutsideSource =
    outsideSourceOverride || qualificationFlags.some((value) => value.partial);
  const activeFocusSourceChecksumSha256 =
    inspectionSourceChecksumSha256 ?? focusSourceChecksumSha256;
  const v12Enabled = geometryEngineVariant === 'contrast_frame_grid_v1_2';

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    if (initialReplacementSource !== undefined) {
      setSources([initialReplacementSource]);
      setSavedCount(0);
      setGeometryManifestChecksum('');
      onPendingSourceCountChange?.(1);
      setSourceIndex(0);
      setLoading(false);
      return;
    }
    try {
      const result = await api.listBrowserPageGeometryReviewSources(
        uploadId,
        preflightJobId,
        gameId,
        activeFocusSourceChecksumSha256,
      );
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się pobrać stron wymagających korekty geometrii.',
          ),
        );
        return;
      }
      const pendingSources = result.data.sources.filter(
        (item) => !item.savedSincePreflight,
      );
      if (
        inspectionSourceChecksumSha256 !== null &&
        !pendingSources.some(
          (item) =>
            item.sourceChecksumSha256 === inspectionSourceChecksumSha256,
        )
      ) {
        setSavedCount(result.data.sources.length - pendingSources.length);
        setGeometryManifestChecksum(result.data.geometryManifestChecksumSha256);
        setSources([]);
        onPendingSourceCountChange?.(
          pendingSources.filter(
            (item) => item.reviewReason !== 'operator_inspection',
          ).length,
        );
        setSourceIndex(0);
        setError(
          'Wybrane zdjęcie nie jest aktywnym, zarejestrowanym źródłem tego stagingu.',
        );
        return;
      }
      const focusedSources =
        inspectionSourceChecksumSha256 !== null
          ? pendingSources.filter(
              (item) =>
                item.sourceChecksumSha256 === inspectionSourceChecksumSha256,
            )
          : activeFocusSourceChecksumSha256 === undefined
            ? pendingSources
            : [
                ...pendingSources.filter(
                  (item) =>
                    item.sourceChecksumSha256 ===
                    activeFocusSourceChecksumSha256,
                ),
                ...pendingSources.filter(
                  (item) =>
                    item.sourceChecksumSha256 !==
                    activeFocusSourceChecksumSha256,
                ),
              ];
      setSavedCount(result.data.sources.length - pendingSources.length);
      setGeometryManifestChecksum(result.data.geometryManifestChecksumSha256);
      setPartialTrainingPool({
        readyPatterns: result.data.partialGridReadyPatternCount ?? 0,
        samples: result.data.partialGridTrainingSampleCount ?? 0,
        sources: result.data.partialGridTrainingSourceCount ?? 0,
      });
      setSources(focusedSources);
      onPendingSourceCountChange?.(
        pendingSources.filter(
          (item) => item.reviewReason !== 'operator_inspection',
        ).length,
      );
      setSourceIndex(0);
    } catch {
      setError('Nie udało się połączyć z lokalnym API korekty geometrii.');
    } finally {
      setLoading(false);
    }
  }, [
    activeFocusSourceChecksumSha256,
    api,
    gameId,
    initialReplacementSource,
    inspectionSourceChecksumSha256,
    onPendingSourceCountChange,
    preflightJobId,
    uploadId,
  ]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void refresh();
    });
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  const source = sources[sourceIndex] ?? null;
  const replacementRecoveryKey =
    source === null
      ? null
      : `page-geometry-replacement:${gameId}:${uploadId}:${source.sourceChecksumSha256}`;
  useEffect(() => {
    queueMicrotask(() => setStorageReady(true));
  }, []);
  let storedReplacement: PendingPageGeometryReplacement | null = null;
  if (
    storageReady &&
    replacementRecoveryKey !== null &&
    typeof window !== 'undefined'
  ) {
    try {
      const raw = window.localStorage.getItem(replacementRecoveryKey);
      const parsed: unknown = raw === null ? null : JSON.parse(raw);
      if (pendingReplacementMatchesSource(source, parsed))
        storedReplacement = parsed;
    } catch {
      // Browser storage can be unavailable; this leaves the normal replacement flow intact.
    }
  }
  const activePendingReplacement = pendingReplacementMatchesSource(
    source,
    pendingReplacement,
  )
    ? pendingReplacement
    : storedReplacement;
  const draftScope = useMemo<PageGeometryDraftScope | null>(
    () =>
      source && imageSize
        ? {
            gameId,
            uploadId,
            preflightJobId,
            checksum: source.sourceChecksumSha256,
            revision: source.existingOverrideRevision ?? 0,
            width: imageSize.width,
            height: imageSize.height,
            count: source.expectedBoardCount,
          }
        : null,
    [source, imageSize, gameId, uploadId, preflightJobId],
  );
  const expectedBoardCount = source?.expectedBoardCount ?? PAGE_BOARD_COUNT;
  const deferredSourceCount = sources.filter(
    (item) => item.reviewReason === 'review_required',
  ).length;
  const registeredUpdateSourceCount = sources.length - deferredSourceCount;

  useEffect(() => {
    const viewport = viewportRef.current;
    if (viewport === null) return;
    const updateSize = () =>
      setViewportSize({
        height: viewport.clientHeight,
        width: viewport.clientWidth,
      });
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [source?.sourceChecksumSha256]);

  const mesh = useMemo(() => {
    if (pageCorners === null) return [];
    return applyPageGeometryMeshOverrides(
      createPageGeometryMesh(pageCorners),
      meshOverrides,
    );
  }, [meshOverrides, pageCorners]);
  const quads = useMemo(() => {
    const generated = pageGeometryQuadsFromMesh(mesh).slice(
      0,
      expectedBoardCount,
    );
    return generated.map((quad, index) => boardOverrides.get(index) ?? quad);
  }, [boardOverrides, expectedBoardCount, mesh]);
  const v12DerivedFrames = useMemo(
    () =>
      quads.map((grid, index) => {
        const offsets = v12FrameOffsets[index];
        if (validV12FrameOffsets(offsets))
          return v12PreviewFrameFromGrid(grid, offsets);
        const storedGrid = v12SymbolGridQuads?.[index];
        const storedFrame = v12BoardFrameQuads?.[index];
        return offsets === null &&
          v12LegacyPairConfirmed &&
          storedGrid &&
          storedFrame &&
          JSON.stringify(storedGrid) === JSON.stringify(grid)
          ? storedFrame
          : null;
      }),
    [
      quads,
      v12BoardFrameQuads,
      v12FrameOffsets,
      v12LegacyPairConfirmed,
      v12SymbolGridQuads,
    ],
  );
  const v12FramesReady =
    v12Enabled &&
    v12DerivedFrames.length === expectedBoardCount &&
    v12DerivedFrames.every(
      (frame, index) =>
        frame !== null &&
        (validV12FrameOffsets(v12FrameOffsets[index])
          ? v12FrameFromGrid(quads[index]!, v12FrameOffsets[index]) !== null
          : v12FrameOffsets[index] === null && v12LegacyPairConfirmed),
    );
  const v12Draft = useMemo(() => {
    if (!v12Enabled) return undefined;
    const symbolGridQuads = quads;
    const boardFrameQuads = v12DerivedFrames.map(
      (frame, index) => frame ?? v12BoardFrameQuads?.[index] ?? quads[index]!,
    );
    if (
      symbolGridQuads.length !== expectedBoardCount ||
      boardFrameQuads.length !== expectedBoardCount
    )
      return undefined;
    return {
      activeLayer: 'symbolGrid' as const,
      boardFrameQuads,
      frameConfirmed: v12FramesReady,
      frameOffsets: v12FrameOffsets,
      symbolGridQuads,
    };
  }, [
    expectedBoardCount,
    quads,
    v12BoardFrameQuads,
    v12DerivedFrames,
    v12Enabled,
    v12FrameOffsets,
    v12FramesReady,
  ]);
  const placedBoardQuads = useMemo(
    () =>
      boardCornerPlacement === null
        ? []
        : pageGeometryQuadsFromCornerPlacement(
            boardCornerPlacement,
            expectedBoardCount,
          ),
    [boardCornerPlacement, expectedBoardCount],
  );
  useEffect(() => {
    if (
      !draftScope ||
      !pageCorners ||
      draftConflict ||
      quads.length !== draftScope.count ||
      qualificationFlags.length !== draftScope.count ||
      (v12Enabled && v12Draft === undefined) ||
      loadedDraftKey.current !== pageGeometryDraftKey(draftScope)
    )
      return;
    try {
      const draft = {
        quads,
        pageCorners,
        flags: qualificationFlags,
        cornerPlacement,
        boardCornerPlacement,
        ...(v12Draft === undefined ? {} : { v12: v12Draft }),
      };
      const ownText = serializePageGeometryDraft(draftScope, draft);
      if (lastPersistedDraft.current === ownText) return;
      writePageGeometryDraft(localStorage, draftScope, draft);
      lastPersistedDraft.current = ownText;
    } catch {
      queueMicrotask(() =>
        setError(
          'Nie udało się utrwalić szkicu. Nie odświeżaj strony przed zapisem.',
        ),
      );
    }
  }, [
    draftScope,
    pageCorners,
    draftConflict,
    quads,
    qualificationFlags,
    cornerPlacement,
    boardCornerPlacement,
    v12Draft,
    v12Enabled,
  ]);
  const activeBoardPlacementIndex = Math.min(
    placedBoardQuads.length,
    expectedBoardCount - 1,
  );
  const activeBoardPlacementPoints =
    boardCornerPlacement === null
      ? []
      : boardCornerPlacement.slice(
          activeBoardPlacementIndex * PAGE_BOARD_CORNER_COUNT,
        );
  const manualPlacementActive =
    cornerPlacement !== null || boardCornerPlacement !== null;
  const displayedV12SymbolQuads = quads;
  const displayedV12FrameQuads = v12Enabled ? v12DerivedFrames : [];
  const symbolGuideQuads =
    boardCornerPlacement !== null
      ? placedBoardQuads
      : cornerPlacement !== null
        ? []
        : v12Enabled
          ? displayedV12SymbolQuads
          : quads;
  const zoomedCanvasSize = fitManualImageToViewport(
    imageSize,
    viewportSize,
    zoom,
  );
  const handleRadius =
    imageSize === null || zoomedCanvasSize === null
      ? HANDLE_SCREEN_RADIUS
      : (HANDLE_SCREEN_RADIUS * imageSize.width) / zoomedCanvasSize.width;

  const imageUrl =
    source === null
      ? null
      : sourceAssetUrl(
          apiBaseUrl,
          uploadId,
          source.sourceChecksumSha256,
          gameId,
        );

  function resetGeometry(
    width: number,
    height: number,
    existingQuads: readonly Quad[],
  ) {
    const storedV12SymbolQuads =
      v12Enabled && source ? existingV12Quads(source, 'symbolGrid') : [];
    const storedV12FrameQuads =
      v12Enabled && source ? existingV12Quads(source, 'boardFrame') : [];
    const initialSymbolQuads = v12Enabled
      ? storedV12SymbolQuads.length === expectedBoardCount
        ? storedV12SymbolQuads
        : existingQuads
      : existingQuads;
    const initialFrameQuads = v12Enabled
      ? storedV12FrameQuads.length === expectedBoardCount
        ? storedV12FrameQuads
        : initialSymbolQuads.map((quad) =>
            expandedFrameQuad(quad, width, height),
          )
      : [];
    const corners =
      outerCornersFromQuads(initialSymbolQuads) ??
      initialCorners(width, height);
    const overrides = new Map(
      initialSymbolQuads.map((quad, index) => [index, quad] as const),
    );
    setImageSize({ height, width });
    setLoadedSourceChecksum(source?.sourceChecksumSha256 ?? null);
    setInitialPageCorners(corners);
    setInitialBoardOverrides(overrides);
    setPageCorners(corners);
    setCornerPlacement(null);
    setBoardCornerPlacement(null);
    setMeshOverrides(new Map());
    setBoardOverrides(overrides);
    setV12SymbolGridQuads(v12Enabled ? initialSymbolQuads : null);
    setV12BoardFrameQuads(v12Enabled ? initialFrameQuads : null);
    setV12LegacyPairConfirmed(
      v12Enabled &&
        typeof source?.existingOverrideRevision === 'number' &&
        storedV12FrameQuads.length === expectedBoardCount &&
        storedV12SymbolQuads.length === expectedBoardCount,
    );
    setV12FrameOffsets(
      v12Enabled
        ? initialSymbolQuads.map((grid, index) =>
            storedV12FrameQuads[index]
              ? v12OffsetsFromPair(grid, storedV12FrameQuads[index])
              : null,
          )
        : [],
    );
    setCorrectionMode(v12Enabled ? 0 : 'page');
    setDragging(null);
    const baseFlags = Array.from({ length: expectedBoardCount }, (_, i) =>
      manualGridFlagsFromQualification(source?.existingSlotQualifications?.[i]),
    );
    setQualificationFlags(baseFlags);
    setDraftConflict(false);
    loadedDraftKey.current = null;
    if (source) {
      const scope: PageGeometryDraftScope = {
        gameId,
        uploadId,
        preflightJobId,
        checksum: source.sourceChecksumSha256,
        revision: source.existingOverrideRevision ?? 0,
        width,
        height,
        count: source.expectedBoardCount,
      };
      try {
        const restored = readPageGeometryDraft(localStorage, scope);
        if (restored && (!v12Enabled || restored.v12 !== undefined)) {
          const restoredV12 = v12Enabled ? restored.v12 : undefined;
          const restoredQuads = restoredV12?.symbolGridQuads ?? restored.quads;
          setPageCorners(
            outerCornersFromQuads(restoredQuads) ?? restored.pageCorners,
          );
          setBoardOverrides(new Map(restoredQuads.map((quad, i) => [i, quad])));
          setQualificationFlags(restored.flags);
          setCornerPlacement(restored.cornerPlacement);
          setBoardCornerPlacement(restored.boardCornerPlacement);
          if (restoredV12 !== undefined) {
            setV12BoardFrameQuads(restoredV12.boardFrameQuads);
            setV12SymbolGridQuads(restoredV12.symbolGridQuads);
            setV12LegacyPairConfirmed(restoredV12.frameConfirmed);
            setV12FrameOffsets(
              restoredV12.frameOffsets ??
                restoredV12.symbolGridQuads.map((grid, index) =>
                  v12OffsetsFromPair(grid, restoredV12.boardFrameQuads[index]!),
                ),
            );
          }
        } else if (restored) {
          setFeedback(
            'Starszy szkic nie zawiera obu warstw V1.2, więc zachowano geometrię z aktualnego preflightu.',
          );
        }
        loadedDraftKey.current = pageGeometryDraftKey(scope);
      } catch (cause) {
        setDraftConflict(true);
        setError(
          cause instanceof Error ? cause.message : 'Nie można odczytać szkicu.',
        );
      }
    }
  }

  function resetCurrentGeometry() {
    if (
      initialPageCorners === null ||
      loadedSourceChecksum !== source?.sourceChecksumSha256
    )
      return;
    setPageCorners(initialPageCorners);
    setCornerPlacement(null);
    setBoardCornerPlacement(null);
    setMeshOverrides(new Map());
    setBoardOverrides(initialBoardOverrides);
    if (v12Enabled && source !== null && imageSize !== null) {
      const symbols = existingV12Quads(source, 'symbolGrid');
      const symbolQuads =
        symbols.length === expectedBoardCount
          ? symbols
          : existingSourceQuads(source);
      const frames = existingV12Quads(source, 'boardFrame');
      setV12SymbolGridQuads(symbolQuads);
      setV12BoardFrameQuads(
        frames.length === expectedBoardCount
          ? frames
          : symbolQuads.map((quad) =>
              expandedFrameQuad(quad, imageSize.width, imageSize.height),
            ),
      );
      setV12LegacyPairConfirmed(
        typeof source.existingOverrideRevision === 'number' &&
          frames.length === expectedBoardCount &&
          symbols.length === expectedBoardCount,
      );
      setV12FrameOffsets(
        symbolQuads.map((grid, index) =>
          frames[index] ? v12OffsetsFromPair(grid, frames[index]) : null,
        ),
      );
    }
    setCorrectionMode(v12Enabled ? 0 : 'page');
    setDragging(null);
    setQualificationFlags(
      Array.from({ length: expectedBoardCount }, (_, i) =>
        manualGridFlagsFromQualification(
          source?.existingSlotQualifications?.[i],
        ),
      ),
    );
    if (draftScope) {
      clearPageGeometryDraft(localStorage, draftScope);
      loadedDraftKey.current = pageGeometryDraftKey(draftScope);
    }
    setDraftConflict(false);
    setError('');
    setFeedback('Przywrócono geometrię widoczną przy otwarciu zdjęcia.');
  }

  function beginCornerPlacement() {
    setCorrectionMode('page');
    setCornerPlacement([]);
    setBoardCornerPlacement(null);
    setDragging(null);
    setFeedback(
      'Wskaż kolejno: lewy górny, prawy górny, prawy dolny i lewy dolny punkt.',
    );
  }

  function beginBoardCornerPlacement() {
    setCorrectionMode(0);
    setCornerPlacement(null);
    setBoardCornerPlacement([]);
    setDragging(null);
    setFeedback(
      `Plansza 1 z ${expectedBoardCount} (rząd 1, kolumna 1). Wskaż kolejno: lewy górny, prawy górny, prawy dolny i lewy dolny punkt.`,
    );
  }

  function showAllBoardCorners(currentQuads: readonly Quad[]) {
    const independentMesh = pageGeometryMeshFromQuads(currentQuads);
    if (independentMesh === null) return false;
    setMeshOverrides(
      new Map(independentMesh.map((point, index) => [index, point] as const)),
    );
    setBoardOverrides(new Map());
    setCorrectionMode('curve');
    return true;
  }

  function placeNextCorner(event: PointerEvent<SVGSVGElement>) {
    if (
      (cornerPlacement === null && boardCornerPlacement === null) ||
      imageSize === null
    ) {
      return;
    }
    const point = relativePoint(event);
    if (point === null) return;
    const bounded = {
      x: clamp(
        point.x,
        allowOutsideSource ? outsideSourceMinimum(imageSize.width) : 0,
        allowOutsideSource
          ? outsideSourceMaximum(imageSize.width)
          : imageSize.width - 1,
      ),
      y: clamp(
        point.y,
        allowOutsideSource ? outsideSourceMinimum(imageSize.height) : 0,
        allowOutsideSource
          ? outsideSourceMaximum(imageSize.height)
          : imageSize.height - 1,
      ),
    };
    if (boardCornerPlacement !== null) {
      const next = appendPageGeometryBoardCorner(
        boardCornerPlacement,
        bounded,
        expectedBoardCount,
      );
      const nextQuads = pageGeometryQuadsFromCornerPlacement(
        next,
        expectedBoardCount,
      );
      const expectedCompletedPoints =
        nextQuads.length * PAGE_BOARD_CORNER_COUNT;
      setBoardCornerPlacement(next);
      if (
        next.length % PAGE_BOARD_CORNER_COUNT === 0 &&
        next.length !== expectedCompletedPoints
      ) {
        setFeedback(
          `Plansza ${nextQuads.length + 1} nie tworzy poprawnego obrysu albo nie leży po właściwej stronie poprzedniej planszy. Cofnij błędny punkt i wskaż go ponownie.`,
        );
        return;
      }
      const completeQuads = completePageGeometryBoardQuads(
        next,
        expectedBoardCount,
      );
      if (completeQuads !== null) {
        const outerCorners = outerCornersFromQuads(completeQuads);
        if (outerCorners !== null) {
          setPageCorners(outerCorners);
          if (v12Enabled) {
            setMeshOverrides(new Map());
            setBoardOverrides(
              new Map(completeQuads.map((quad, i) => [i, quad])),
            );
            setCorrectionMode(0);
          } else showAllBoardCorners(completeQuads);
        } else {
          setBoardOverrides(
            new Map(completeQuads.map((quad, index) => [index, quad] as const)),
          );
          setCorrectionMode(0);
        }
        setBoardCornerPlacement(null);
        setFeedback(
          expectedBoardCount === PAGE_BOARD_COUNT
            ? 'Ustawiono osobno wszystkie 9 plansz w kolejności 1–3, 4–6, 7–9. Włączono wszystkie 36 narożników, które możesz teraz doprecyzować przed zapisem.'
            : `Ustawiono osobno wszystkie ${expectedBoardCount} plansz końcowej strony. Możesz doprecyzować każdą planszę przed zapisem.`,
        );
        return;
      }
      const boardIndex = nextQuads.length;
      const cornerIndex = next.length - expectedCompletedPoints;
      setFeedback(
        cornerIndex === 0
          ? `Plansza ${boardIndex + 1} z ${expectedBoardCount} (rząd ${Math.floor(boardIndex / 3) + 1}, kolumna ${(boardIndex % 3) + 1}). Wskaż lewy górny punkt.`
          : `Plansza ${boardIndex + 1} z ${expectedBoardCount}: wskaż ${CORNER_NAMES[cornerIndex]}.`,
      );
      return;
    }
    if (cornerPlacement === null) return;
    const next = appendPageGeometryCorner(cornerPlacement, bounded);
    const complete = completePageGeometryCorners(next);
    if (complete === null) {
      setCornerPlacement(next);
      if (next.length === 4) {
        setFeedback(
          'Punkty nie tworzą poprawnego obrysu LT → PT → PD → LD. Cofnij błędny punkt i wskaż go ponownie.',
        );
      }
      return;
    }
    setPageCorners(complete);
    setCornerPlacement(null);
    setMeshOverrides(new Map());
    setBoardOverrides(new Map());
    setFeedback(
      'Cztery narożniki ustawione. Możesz je przeciągnąć albo dopasować krzywiznę.',
    );
  }

  function undoCornerPlacement() {
    if (boardCornerPlacement !== null) {
      setBoardCornerPlacement((current) =>
        current === null ? current : current.slice(0, -1),
      );
      return;
    }
    setCornerPlacement((current) =>
      current === null ? current : current.slice(0, -1),
    );
  }

  function updatePoint(next: Point) {
    if (dragging === null || imageSize === null || pageCorners === null) return;
    const point = {
      x: clamp(
        next.x,
        allowOutsideSource ? outsideSourceMinimum(imageSize.width) : 0,
        allowOutsideSource
          ? outsideSourceMaximum(imageSize.width)
          : imageSize.width - 1,
      ),
      y: clamp(
        next.y,
        allowOutsideSource ? outsideSourceMinimum(imageSize.height) : 0,
        allowOutsideSource
          ? outsideSourceMaximum(imageSize.height)
          : imageSize.height - 1,
      ),
    };
    if (dragging.kind === 'page') {
      setPageCorners((current) => {
        if (current === null) return current;
        const nextCorners: PageCorners = [
          dragging.pointIndex === 0 ? point : current[0],
          dragging.pointIndex === 1 ? point : current[1],
          dragging.pointIndex === 2 ? point : current[2],
          dragging.pointIndex === 3 ? point : current[3],
        ];
        return nextCorners;
      });
      setMeshOverrides(new Map());
      setBoardOverrides(new Map());
      return;
    }
    if (dragging.kind === 'mesh') {
      setMeshOverrides((current) => {
        const nextOverrides = new Map(current);
        nextOverrides.set(dragging.pointIndex, point);
        return nextOverrides;
      });
      setBoardOverrides(new Map());
      return;
    }
    setBoardOverrides((current) => {
      const currentQuad =
        current.get(dragging.boardIndex) ?? quads[dragging.boardIndex];
      if (currentQuad === undefined) return current;
      const nextOverrides = new Map(current);
      const nextQuad: Quad = [
        dragging.pointIndex === 0 ? point : currentQuad[0],
        dragging.pointIndex === 1 ? point : currentQuad[1],
        dragging.pointIndex === 2 ? point : currentQuad[2],
        dragging.pointIndex === 3 ? point : currentQuad[3],
      ];
      nextOverrides.set(dragging.boardIndex, nextQuad);
      return nextOverrides;
    });
  }

  function relativePoint(event: PointerEvent<SVGSVGElement>): Point | null {
    if (imageSize === null) return null;
    const rect = event.currentTarget.getBoundingClientRect();
    const point = pageGeometryPointFromRenderedCanvas({
      clientX: event.clientX,
      clientY: event.clientY,
      imageHeight:
        imageSize.height *
        (allowOutsideSource ? OUTSIDE_SOURCE_VIEWPORT_SCALE : 1),
      imageWidth:
        imageSize.width *
        (allowOutsideSource ? OUTSIDE_SOURCE_VIEWPORT_SCALE : 1),
      renderedHeight: rect.height,
      renderedLeft: rect.left,
      renderedTop: rect.top,
      renderedWidth: rect.width,
    });
    if (point === null || !allowOutsideSource) return point;
    return {
      x: point.x - imageSize.width * OUTSIDE_SOURCE_MARGIN_RATIO,
      y: point.y - imageSize.height * OUTSIDE_SOURCE_MARGIN_RATIO,
    };
  }

  function beginDrag(
    event: PointerEvent<SVGCircleElement>,
    value: NonNullable<typeof dragging>,
  ) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.ownerSVGElement?.setPointerCapture(event.pointerId);
    setDragging(value);
  }

  async function save() {
    const symbolQuadsForSave = quads;
    const frameQuadsForSave = v12Enabled
      ? v12DerivedFrames.filter((frame): frame is Quad => frame !== null)
      : [];
    if (
      source === null ||
      imageSize === null ||
      symbolQuadsForSave.length !== expectedBoardCount ||
      (v12Enabled && frameQuadsForSave.length !== expectedBoardCount) ||
      (v12Enabled && !v12FramesReady) ||
      draftConflict ||
      !draftScope ||
      loadedDraftKey.current !== pageGeometryDraftKey(draftScope) ||
      saving ||
      replacing ||
      activePendingReplacement !== null
    )
      return;
    setSaving(true);
    setError('');
    setFeedback('Zapisuję korektę całej strony…');
    try {
      const submittedDraftText = pageCorners
        ? serializePageGeometryDraft(draftScope, {
            quads,
            pageCorners,
            flags: qualificationFlags,
            cornerPlacement,
            boardCornerPlacement,
            ...(v12Draft === undefined ? {} : { v12: v12Draft }),
          })
        : null;
      const finalQuads = symbolQuadsForSave.map((quad) =>
        quad.map((point) => ({
          x: Math.round(point.x),
          y: Math.round(point.y),
        })),
      ) as BrowserPageGeometryOverrideCreate['finalQuads'];
      const result = await api.createBrowserPageGeometryOverride(uploadId, {
        actor: 'local-owner',
        finalQuads,
        ...(v12Enabled
          ? {
              boardFrameQuads: frameQuadsForSave.map((quad) =>
                quad.map((point) => ({
                  x: Math.round(point.x),
                  y: Math.round(point.y),
                })),
              ) as BrowserPageGeometryOverrideCreate['boardFrameQuads'],
              symbolGridQuads: finalQuads,
            }
          : {}),
        gameId,
        imageHeight: imageSize.height,
        imageWidth: imageSize.width,
        sourceChecksumSha256: source.sourceChecksumSha256,
        slotQualifications:
          qualificationFlags.some((flags) => flags.partial || flags.exclude) ||
          source.existingSlotQualifications
            ? symbolQuadsForSave.map((quad, i) =>
                manualGridQualification(
                  qualificationFlags[i] ?? completeManualGridFlags,
                  quad,
                  imageSize.width,
                  imageSize.height,
                ),
              )
            : undefined,
        expectedOverrideRevision: source.existingOverrideRevision ?? 0,
      });
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się zapisać korekty geometrii.',
          ),
        );
        return;
      }
      setFeedback(
        source.reviewReason === 'manual_override' ||
          source.reviewReason === 'operator_inspection'
          ? 'Zapisano aktualizację już zarejestrowanej geometrii. Licznik poprawnych zdjęć nie wzrośnie, ponieważ to źródło było w nim wcześniej.'
          : 'Zapisano geometrię odroczonego zdjęcia. Po wysłaniu partii i ukończeniu preflightu przejdzie ono do zarejestrowanych.',
      );
      setSavedCount((current) => current + 1);
      if (initialReplacementSource !== undefined) onDraftSaved?.();
      clearCommittedPageGeometryDraft(
        localStorage,
        draftScope,
        submittedDraftText,
      );
      loadedDraftKey.current = null;
      const remainingSources = sources.filter(
        (item) => item.sourceChecksumSha256 !== source.sourceChecksumSha256,
      );
      setSources(remainingSources);
      onPendingSourceCountChange?.(
        remainingSources.filter(
          (item) => item.reviewReason !== 'operator_inspection',
        ).length,
      );
      setSourceIndex((current) =>
        Math.min(current, Math.max(0, sources.length - 2)),
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się zapisać korekty geometrii strony.',
      );
    } finally {
      setSaving(false);
    }
  }

  async function submitSaved() {
    if (
      submitting ||
      saving ||
      replacing ||
      activePendingReplacement !== null ||
      savedCount === 0
    )
      return;
    setSubmitting(true);
    setError('');
    setFeedback('Tworzę jeden preflight dla całej zapisanej partii…');
    try {
      await onSubmitSaved();
    } catch {
      setError('Nie udało się wysłać zapisanych geometrii do weryfikacji.');
    } finally {
      setSubmitting(false);
    }
  }

  async function excludeCurrentSource() {
    if (
      source === null ||
      saving ||
      submitting ||
      excluding ||
      replacing ||
      activePendingReplacement !== null
    )
      return;
    const confirmed = globalThis.confirm(
      `Usunąć ${source.sourceRelativePath} z tego importu? Zdjęcie pozostanie w bezpiecznym stagingu, ale nie zostanie skopiowane ani przetworzone. Poprawioną wersję będzie można przesłać w nowym imporcie.`,
    );
    if (!confirmed) return;
    setExcluding(true);
    setError('');
    setFeedback('Wykluczam zdjęcie z importu…');
    try {
      const result = await api.excludeBrowserPageGeometrySource(
        uploadId,
        preflightJobId,
        {
          actor: 'local-owner',
          gameId,
          geometryManifestChecksumSha256: geometryManifestChecksum,
          sourceChecksumSha256: source.sourceChecksumSha256,
          sourceRelativePath: source.sourceRelativePath,
        },
      );
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się usunąć zdjęcia z importu.',
          ),
        );
        return;
      }
      const remainingSources = sources.filter(
        (item) => item.sourceChecksumSha256 !== source.sourceChecksumSha256,
      );
      setSources(remainingSources);
      onPendingSourceCountChange?.(
        remainingSources.filter(
          (item) => item.reviewReason !== 'operator_inspection',
        ).length,
      );
      if (source.savedSincePreflight) {
        setSavedCount((current) => Math.max(0, current - 1));
      }
      setSourceIndex((current) =>
        Math.min(current, Math.max(0, sources.length - 2)),
      );
      setFeedback(
        'Zdjęcie zostało wykluczone. Nie trafi do importu ani jego raportu roboczego.',
      );
    } catch {
      setError('Nie udało się połączyć z lokalnym API wykluczeń importu.');
    } finally {
      setExcluding(false);
    }
  }

  async function chooseCutFolder() {
    try {
      setCutFolder(await choosePageGeometryCutFolder());
      setError('');
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się wybrać katalogu cut.',
      );
    }
  }

  async function replaceCurrentSource(file: File | undefined) {
    if (!file || !source || !cutFolder || replacing || saving || submitting)
      return;
    setReplacing(true);
    setError('');
    try {
      if (!/\.jpe?g$/i.test(file.name)) {
        throw new Error('Wybierz nowe zdjęcie JPEG.');
      }
      await verifyPageGeometryCutSource(
        cutFolder,
        source.sourceRelativePath,
        source.sourceChecksumSha256,
      );
      if (replacementRecoveryKey === null)
        throw new Error('Brak tożsamości zdjęcia do podmiany.');
      window.localStorage.setItem(replacementRecoveryKey, 'preparing');
      window.localStorage.removeItem(replacementRecoveryKey);
      const result = await api.replaceUnconfirmedBrowserPageGeometrySource(
        uploadId,
        preflightJobId,
        gameId,
        source.sourceChecksumSha256,
        source.sourceRelativePath,
        geometryManifestChecksum,
        file,
      );
      if (result.error !== undefined || result.data === undefined) {
        throw new Error(
          apiErrorMessage(
            result.error,
            'Nie udało się przygotować nowej rewizji stagingu.',
          ),
        );
      }
      const ready = result.data;
      const expectedReplacementChecksum = await checksumPageGeometryFile(file);
      const pending: PendingPageGeometryReplacement = {
        replacementUploadId: ready.uploadId,
        replacementChecksum: expectedReplacementChecksum,
        sourceChecksum: source.sourceChecksumSha256,
        sourceRelativePath: source.sourceRelativePath,
      };
      if (replacementRecoveryKey !== null) {
        window.localStorage.setItem(
          replacementRecoveryKey,
          JSON.stringify(pending),
        );
      }
      setPendingReplacement(pending);
      const replacementChecksum = await replacePageGeometryCutSource(
        cutFolder,
        source.sourceRelativePath,
        source.sourceChecksumSha256,
        file,
      );
      const confirmation =
        await api.confirmBrowserPageGeometrySourceReplacement(
          uploadId,
          ready.uploadId,
          gameId,
          source.sourceChecksumSha256,
          source.sourceRelativePath,
          replacementChecksum,
        );
      if (confirmation.error !== undefined || confirmation.data === undefined) {
        throw new Error(
          apiErrorMessage(
            confirmation.error,
            'Zdjęcie zapisano, ale nie udało się potwierdzić nowej rewizji.',
          ),
        );
      }
      if (replacementRecoveryKey !== null)
        window.localStorage.removeItem(replacementRecoveryKey);
      setPendingReplacement(null);
      setFeedback(
        'Nowe zdjęcie zapisano w katalogu cut i stagingu. Przygotowuję jego geometrię…',
      );
      await onSourceReplaced(confirmation.data, replacementChecksum, source);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się podmienić zdjęcia.',
      );
    } finally {
      if (replacementInputRef.current) replacementInputRef.current.value = '';
      setReplacing(false);
    }
  }

  async function finishPendingReplacement() {
    if (!activePendingReplacement || !cutFolder || !source || replacing) return;
    const pendingReplacement = activePendingReplacement;
    setReplacing(true);
    setError('');
    try {
      try {
        await verifyPageGeometryCutSource(
          cutFolder,
          pendingReplacement.sourceRelativePath,
          pendingReplacement.replacementChecksum,
        );
      } catch (cause) {
        try {
          await verifyPageGeometryCutSource(
            cutFolder,
            pendingReplacement.sourceRelativePath,
            pendingReplacement.sourceChecksum,
          );
        } catch {
          throw cause;
        }
        const discarded = await api.discardBrowserPageGeometrySourceReplacement(
          uploadId,
          pendingReplacement.replacementUploadId,
          gameId,
        );
        if (discarded.error !== undefined) {
          throw new Error(
            apiErrorMessage(
              discarded.error,
              'Nie udało się anulować przygotowanej podmiany.',
            ),
          );
        }
        if (replacementRecoveryKey !== null)
          window.localStorage.removeItem(replacementRecoveryKey);
        setPendingReplacement(null);
        setFeedback(
          'Oryginalne zdjęcie nadal jest w katalogu cut. Wybierz nowe zdjęcie ponownie.',
        );
        return;
      }
      const confirmed = await api.confirmBrowserPageGeometrySourceReplacement(
        uploadId,
        pendingReplacement.replacementUploadId,
        gameId,
        pendingReplacement.sourceChecksum,
        pendingReplacement.sourceRelativePath,
        pendingReplacement.replacementChecksum,
      );
      if (confirmed.error !== undefined || confirmed.data === undefined) {
        throw new Error(
          apiErrorMessage(confirmed.error, 'Nie udało się dokończyć podmiany.'),
        );
      }
      if (replacementRecoveryKey !== null)
        window.localStorage.removeItem(replacementRecoveryKey);
      setPendingReplacement(null);
      await onSourceReplaced(
        confirmed.data,
        pendingReplacement.replacementChecksum,
        source,
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się dokończyć podmiany.',
      );
    } finally {
      setReplacing(false);
    }
  }

  async function inspectRegisteredSource(file: File) {
    setError('');
    setFeedback('');
    try {
      setInspectionSourceChecksumSha256(await checksumPageGeometryFile(file));
    } catch {
      setError(
        'Nie udało się odczytać wybranego zdjęcia do korekty geometrii.',
      );
    } finally {
      if (inspectionInputRef.current) inspectionInputRef.current.value = '';
    }
  }

  return (
    <section
      className="pageGeometryCorrection"
      aria-label="Korekta geometrii strony"
    >
      <div className="pageGeometryCorrectionHeader">
        <div>
          <h3>Korekta geometrii strony</h3>
          <p>
            Liczniki dotyczą zdjęć źródłowych, nie pojedynczych plansz. Jedno
            zdjęcie zawiera od jednej do dziewięciu plansz zgodnie z zakresem
            zapisanym w nazwie; zostaną one utworzone dopiero w imporcie po
            zakończeniu preflightu geometrii.
          </p>
          <p>
            Oddzielna pula niepełnych siatek: {partialTrainingPool.samples}{' '}
            próbek z {partialTrainingPool.sources} zdjęć; gotowe wzorce:{' '}
            {partialTrainingPool.readyPatterns}. Wzorzec wymaga co najmniej 3
            różnych zdjęć.
          </p>
        </div>
        <div className="pageGeometryCorrectionHeaderActions">
          {allowRegisteredSourceInspection ? (
            <>
              <input
                accept=".jpg,.jpeg,image/jpeg"
                aria-label="Wybierz zarejestrowane zdjęcie do korekty geometrii"
                hidden
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  if (file !== undefined) void inspectRegisteredSource(file);
                }}
                ref={inspectionInputRef}
                type="file"
              />
              <button
                className="secondaryButton"
                disabled={loading || saving || submitting || replacing}
                onClick={() => inspectionInputRef.current?.click()}
                type="button"
              >
                Wskaż zarejestrowane zdjęcie
              </button>
              {inspectionSourceChecksumSha256 !== null ? (
                <button
                  className="secondaryButton"
                  disabled={loading || saving || submitting || replacing}
                  onClick={() => setInspectionSourceChecksumSha256(null)}
                  type="button"
                >
                  Wróć do kolejki
                </button>
              ) : null}
            </>
          ) : null}
          <button
            className="secondaryButton"
            disabled={loading || saving || submitting}
            onClick={() => void refresh()}
            type="button"
          >
            Odśwież listę
          </button>
          <button
            className="primaryButton"
            disabled={
              savedCount === 0 ||
              saving ||
              submitting ||
              replacing ||
              activePendingReplacement !== null
            }
            onClick={() => void submitSaved()}
            type="button"
          >
            {submitting
              ? 'Wysyłanie partii…'
              : `Wyślij zapisane do weryfikacji (${savedCount})`}
          </button>
        </div>
      </div>
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
      {loading ? (
        <p className="curatedImportStatus">Ładowanie stron do korekty…</p>
      ) : null}
      {!loading && sources.length === 0 ? (
        <p className="curatedImportStatus">
          {allowRegisteredSourceInspection
            ? 'Nie ma stron oczekujących na korektę. Możesz wskazać zarejestrowane zdjęcie powyżej; jego lokalny plik służy tylko do porównania checksumy i nie zostanie przesłany.'
            : 'Nie ma już stron oczekujących na korektę geometrii.'}
        </p>
      ) : null}
      {source !== null ? (
        <div className="pageGeometryCorrectionGrid">
          <div className="pageGeometryControls">
            <p className="curatedImportStatus">
              Pozostałe zdjęcia: odroczone {deferredSourceCount} · aktualizacje
              wcześniej zarejestrowanej geometrii {registeredUpdateSourceCount}
            </p>
            <p className="curatedImportStatus">
              Strona {sourceIndex + 1}/{sources.length} ·{' '}
              {source.sourceRelativePath}
              {source.sequenceRangeStart !== null &&
              source.sequenceRangeEnd !== null
                ? ` · plansze ${source.sequenceRangeStart}–${source.sequenceRangeEnd}`
                : ''}
              {source.reviewReason === 'operator_inspection'
                ? ' · zarejestrowane zdjęcie — sprawdź automatyczną geometrię'
                : source.reviewReason === 'manual_override'
                  ? ` · aktualizacja już zarejestrowanej geometrii r${source.existingOverrideRevision ?? '?'}`
                  : ' · odroczone zdjęcie — wymaga geometrii'}
            </p>
            {source.automaticPartialProposals?.length ? (
              <p className="geometryOriginNotice" role="status">
                Pochodzenie: automatyczna propozycja v0.10.4 · sloty{' '}
                {source.automaticPartialProposals
                  .map(
                    (proposal) =>
                      `${proposal.positionIndex} (brakujące komórki: ${proposal.geometryQualification.unavailableCellIndices.join(', ') || 'brak'})`,
                  )
                  .join(' · ')}
                . Wszystkie sloty z nazwy pliku pozostają widoczne i wymagają
                ręcznego potwierdzenia.
              </p>
            ) : null}
            {source.geometryOrigin === 'manual_template' ? (
              <div
                className="geometryOriginNotice geometryOriginNoticeWarning"
                role="status"
              >
                <strong>Nie wykryto geometrii — ustaw plansze ręcznie.</strong>
                <p>
                  Widoczne prostokąty są wyłącznie roboczym szablonem edytora, a
                  nie wynikiem automatycznego wykrycia.{' '}
                  {rejectionLabel(source.rejectionReasonCode)}
                </p>
                <details>
                  <summary>Diagnostyka dopasowania</summary>
                  {source.registrationDiagnostics?.bestAttempt ? (
                    <ul>
                      <li>
                        Bramka:{' '}
                        {source.registrationDiagnostics.bestAttempt.reasonCode}
                      </li>
                      {diagnosticMetric(
                        'Budżet cech',
                        source.registrationDiagnostics.bestAttempt.featureCount,
                      )}
                      {diagnosticMetric(
                        'Dopasowania',
                        source.registrationDiagnostics.bestAttempt.matchCount,
                      )}
                      {diagnosticMetric(
                        'Inliery',
                        source.registrationDiagnostics.bestAttempt.inlierCount,
                      )}
                      {diagnosticMetric(
                        'Udział inlierów',
                        source.registrationDiagnostics.bestAttempt.inlierRatio,
                      )}
                      {diagnosticMetric(
                        'p95 reprojekcji',
                        source.registrationDiagnostics.bestAttempt
                          .p95ReprojectionError,
                      )}
                      {diagnosticMetric(
                        'Średnie pokrycie ramek',
                        source.registrationDiagnostics.bestAttempt
                          .meanRedEdgeCoverage,
                      )}
                      {diagnosticMetric(
                        'Najsłabsza ramka',
                        source.registrationDiagnostics.bestAttempt
                          .minimumBoardRedEdgeCoverage,
                      )}
                    </ul>
                  ) : (
                    <p>Szczegółowa przyczyna nie została zapisana.</p>
                  )}
                </details>
              </div>
            ) : source.geometryOrigin === 'manual_override' ? (
              <p className="geometryOriginNotice">
                Wczytano ręcznie zapisaną geometrię. Reset przywraca dokładnie
                ten zapis.
              </p>
            ) : (
              <p className="geometryOriginNotice">
                Wczytano geometrię zaproponowaną automatycznie.
              </p>
            )}
            <p className="geometryInstructions">
              {source.reviewReason === 'manual_override' ||
              source.reviewReason === 'operator_inspection'
                ? 'To zdjęcie jest już uwzględnione w liczniku zarejestrowanych. Zapis zmieni jego obrys, ale nie zwiększy tego licznika.'
                : `Edytor przygotował komplet ${expectedBoardCount} edytowalnych plansz. Po zapisaniu i wykonaniu preflightu to zdjęcie przejdzie z odroczonych do zarejestrowanych.`}
            </p>
            {v12Enabled ? (
              <p className="geometryInstructions">
                Wskaż cztery narożniki siatki symboli każdej planszy. Ramka
                powstanie z czterech odstępów podanych pod zdjęciem.
              </p>
            ) : null}
            <label>
              Zakres korekty
              <select
                disabled={
                  saving ||
                  submitting ||
                  cornerPlacement !== null ||
                  boardCornerPlacement !== null
                }
                onChange={(event) => {
                  const value = event.target.value;
                  if (value === 'curve') {
                    showAllBoardCorners(quads);
                    return;
                  }
                  setCorrectionMode(
                    value === 'page' || value === 'curve'
                      ? value
                      : Number(value),
                  );
                }}
                value={String(correctionMode)}
              >
                {!v12Enabled ? (
                  <option value="page">Cała strona — 4 główne uchwyty</option>
                ) : null}
                {!v12Enabled && expectedBoardCount === PAGE_BOARD_COUNT ? (
                  <option value="curve">
                    Wszystkie plansze — 36 narożników
                  </option>
                ) : null}
                {Array.from({ length: expectedBoardCount }, (_, index) => (
                  <option key={index} value={index}>
                    Plansza {index + 1} — korekta wyjątkowa
                  </option>
                ))}
              </select>
            </label>
            <p className="geometryInstructions">
              {boardCornerPlacement !== null
                ? activeBoardPlacementPoints.length >= PAGE_BOARD_CORNER_COUNT
                  ? `Plansza ${activeBoardPlacementIndex + 1} z ${expectedBoardCount} nie tworzy poprawnego obrysu albo nie zachowuje kolejności od lewej do prawej. Cofnij błędny punkt.`
                  : `Plansza ${activeBoardPlacementIndex + 1} z ${expectedBoardCount} · rząd ${Math.floor(activeBoardPlacementIndex / 3) + 1}, kolumna ${(activeBoardPlacementIndex % 3) + 1} · kliknij punkt ${activeBoardPlacementPoints.length + 1} z 4: ${CORNER_NAMES[activeBoardPlacementPoints.length]}.`
                : cornerPlacement !== null
                  ? `Kliknij punkt ${cornerPlacement.length + 1} z 4: ${CORNER_NAMES[cornerPlacement.length]}.`
                  : correctionMode === 'page'
                    ? 'Najpierw ustaw cztery żółte uchwyty na zewnętrznych narożnikach. Ta operacja zeruje korektę krzywizny.'
                    : correctionMode === 'curve'
                      ? 'Przesuń dowolny z 36 niezależnych narożników dziewięciu plansz. Każda plansza zachowuje własny obrys, odstępy i krzywiznę.'
                      : 'W razie wyjątku doprecyzuj tylko tę jedną planszę. Pozostałe zachowają elastyczną geometrię całej strony.'}
            </p>
            <p className="geometryInstructions">
              Przerywane linie wewnątrz plansz pokazują potencjalny podział na
              symbole 5 × 3 po rektyfikacji. Po rozpoczęciu ręcznego wyznaczania
              poprzednia propozycja systemu jest ukrywana.
            </p>
            <div className="pageGeometryNavigation">
              <button
                className="secondaryButton"
                disabled={saving || sourceIndex === 0}
                onClick={() =>
                  setSourceIndex((current) => Math.max(0, current - 1))
                }
                type="button"
              >
                Poprzednia
              </button>
              <button
                className="secondaryButton"
                disabled={saving || sourceIndex >= sources.length - 1}
                onClick={() =>
                  setSourceIndex((current) =>
                    Math.min(sources.length - 1, current + 1),
                  )
                }
                type="button"
              >
                Następna
              </button>
              <button
                className="primaryButton"
                disabled={
                  saving ||
                  submitting ||
                  replacing ||
                  activePendingReplacement !== null ||
                  imageSize === null ||
                  cornerPlacement !== null ||
                  boardCornerPlacement !== null ||
                  (v12Enabled && !v12FramesReady)
                }
                onClick={() => void save()}
                type="button"
              >
                {saving ? 'Zapisywanie…' : 'Zapisz i przejdź dalej'}
              </button>
              {initialReplacementSource === undefined ? (
                <button
                  className="dangerButton"
                  disabled={
                    saving ||
                    submitting ||
                    excluding ||
                    replacing ||
                    activePendingReplacement !== null
                  }
                  onClick={() => void excludeCurrentSource()}
                  type="button"
                >
                  {excluding ? 'Usuwanie…' : 'Usuń z importu'}
                </button>
              ) : null}
              {initialReplacementSource === undefined &&
              source.reviewReason === 'review_required' &&
              !source.savedSincePreflight ? (
                <>
                  <button
                    className="secondaryButton"
                    disabled={saving || submitting || replacing}
                    onClick={() => void chooseCutFolder()}
                    type="button"
                  >
                    {cutFolder === null
                      ? 'Wskaż katalog cut'
                      : `Katalog: ${cutFolder.name}`}
                  </button>
                  <input
                    accept=".jpg,.jpeg,image/jpeg"
                    hidden
                    onChange={(event) =>
                      void replaceCurrentSource(event.target.files?.[0])
                    }
                    ref={replacementInputRef}
                    type="file"
                  />
                  <button
                    className="secondaryButton"
                    disabled={
                      saving ||
                      submitting ||
                      replacing ||
                      cutFolder === null ||
                      activePendingReplacement !== null
                    }
                    onClick={() => replacementInputRef.current?.click()}
                    type="button"
                  >
                    {replacing ? 'Podmieniam…' : 'Wgraj nowe zdjęcie'}
                  </button>
                  {activePendingReplacement !== null ? (
                    <button
                      className="secondaryButton"
                      disabled={
                        saving || submitting || replacing || cutFolder === null
                      }
                      onClick={() => void finishPendingReplacement()}
                      type="button"
                    >
                      Dokończ podmianę po przerwaniu
                    </button>
                  ) : null}
                </>
              ) : null}
              {!v12Enabled ? (
                <button
                  className="secondaryButton"
                  disabled={saving || submitting || imageSize === null}
                  onClick={beginCornerPlacement}
                  type="button"
                >
                  Wyznacz 4 narożniki
                </button>
              ) : null}
              <button
                className="secondaryButton"
                disabled={saving || submitting || imageSize === null}
                onClick={beginBoardCornerPlacement}
                type="button"
              >
                {v12Enabled
                  ? 'Wyznacz plansze'
                  : `Wyznacz ${expectedBoardCount} plansz osobno`}
              </button>
              {(cornerPlacement !== null && cornerPlacement.length > 0) ||
              (boardCornerPlacement !== null &&
                boardCornerPlacement.length > 0) ? (
                <button
                  className="secondaryButton"
                  disabled={saving || submitting}
                  onClick={undoCornerPlacement}
                  type="button"
                >
                  Cofnij punkt
                </button>
              ) : null}
              <button
                className="secondaryButton"
                disabled={saving || submitting || initialPageCorners === null}
                onClick={resetCurrentGeometry}
                type="button"
              >
                Reset
              </button>
            </div>
            <div
              className="pageGeometryZoom"
              aria-label="Powiększenie zdjęcia geometrii"
            >
              <button
                aria-label="Pomniejsz zdjęcie geometrii"
                className="secondaryButton"
                disabled={saving || submitting || zoom <= MIN_GEOMETRY_ZOOM}
                onClick={() =>
                  setZoom((current) =>
                    Math.max(MIN_GEOMETRY_ZOOM, current - GEOMETRY_ZOOM_STEP),
                  )
                }
                type="button"
              >
                −
              </button>
              <button
                className="secondaryButton pageGeometryZoomValue"
                disabled={saving || submitting || zoom === MIN_GEOMETRY_ZOOM}
                onClick={() => setZoom(MIN_GEOMETRY_ZOOM)}
                title="Przywróć dopasowanie do okna"
                type="button"
              >
                {Math.round(zoom * 100)}%
              </button>
              <button
                aria-label="Powiększ zdjęcie geometrii"
                className="secondaryButton"
                disabled={saving || submitting || zoom >= MAX_GEOMETRY_ZOOM}
                onClick={() =>
                  setZoom((current) =>
                    Math.min(MAX_GEOMETRY_ZOOM, current + GEOMETRY_ZOOM_STEP),
                  )
                }
                type="button"
              >
                +
              </button>
              <span>Przewijaj powiększony obraz w obu osiach.</span>
            </div>
          </div>
          <div className="pageGeometryViewport" ref={viewportRef}>
            <div
              className="pageGeometryCanvas"
              key={source.sourceChecksumSha256}
              style={
                zoomedCanvasSize === null
                  ? undefined
                  : {
                      height: `${zoomedCanvasSize.height}px`,
                      width: `${zoomedCanvasSize.width}px`,
                      background: allowOutsideSource ? '#555' : undefined,
                    }
              }
            >
              {imageUrl !== null ? (
                <img
                  alt={`Źródło do korekty: ${source.sourceRelativePath}`}
                  onLoad={(event) =>
                    resetGeometry(
                      event.currentTarget.naturalWidth,
                      event.currentTarget.naturalHeight,
                      existingSourceQuads(source),
                    )
                  }
                  src={imageUrl}
                  style={
                    allowOutsideSource
                      ? {
                          position: 'absolute',
                          left: `${OUTSIDE_SOURCE_IMAGE_START_PERCENT}%`,
                          top: `${OUTSIDE_SOURCE_IMAGE_START_PERCENT}%`,
                          width: `${OUTSIDE_SOURCE_IMAGE_SIZE_PERCENT}%`,
                          height: `${OUTSIDE_SOURCE_IMAGE_SIZE_PERCENT}%`,
                        }
                      : undefined
                  }
                />
              ) : null}
              {imageSize !== null &&
              pageCorners !== null &&
              loadedSourceChecksum === source.sourceChecksumSha256 ? (
                <svg
                  aria-label="Nakładka geometrii strony"
                  onPointerDown={placeNextCorner}
                  onPointerMove={(event) => {
                    const point = relativePoint(event);
                    if (point !== null) updatePoint(point);
                  }}
                  onPointerUp={() => setDragging(null)}
                  viewBox={
                    allowOutsideSource
                      ? `${outsideSourceMinimum(imageSize.width)} ${outsideSourceMinimum(imageSize.height)} ${OUTSIDE_SOURCE_VIEWPORT_SCALE * imageSize.width} ${OUTSIDE_SOURCE_VIEWPORT_SCALE * imageSize.height}`
                      : `0 0 ${imageSize.width} ${imageSize.height}`
                  }
                >
                  <defs>
                    <pattern
                      id="partial-cell-hatch"
                      width="12"
                      height="12"
                      patternUnits="userSpaceOnUse"
                    >
                      <rect width="12" height="12" fill="#7779" />
                      <path d="M0 12L12 0" stroke="#ddd" strokeWidth="2" />
                    </pattern>
                  </defs>
                  {v12Enabled
                    ? displayedV12FrameQuads.map((quad, index) =>
                        quad === null ? null : (
                          <polygon
                            className="pageGeometryBoardPlacement"
                            key={`v12-frame-reference-${index}`}
                            points={quad.map(pointText).join(' ')}
                            pointerEvents="none"
                          />
                        ),
                      )
                    : null}
                  {!manualPlacementActive
                    ? quads.map((quad, index) => (
                        <polygon
                          className={
                            correctionMode === index
                              ? 'pageGeometryBoard pageGeometryBoardSelected'
                              : 'pageGeometryBoard'
                          }
                          key={index}
                          onPointerDown={(event) => {
                            event.stopPropagation();
                            setCorrectionMode(index);
                          }}
                          points={quad.map(pointText).join(' ')}
                        />
                      ))
                    : null}
                  {boardCornerPlacement !== null
                    ? placedBoardQuads.map((quad, index) => (
                        <polygon
                          className="pageGeometryBoardPlacement"
                          key={`placed-board-${index}`}
                          points={quad.map(pointText).join(' ')}
                        />
                      ))
                    : null}
                  {symbolGuideQuads.flatMap((quad, boardIndex) =>
                    pageGeometrySymbolCutLines(quad).map((line, lineIndex) => (
                      <line
                        className={
                          manualPlacementActive
                            ? 'pageGeometrySymbolCut pageGeometrySymbolCutPlacement'
                            : 'pageGeometrySymbolCut'
                        }
                        key={`symbol-cut-${boardIndex}-${lineIndex}`}
                        x1={line[0].x}
                        x2={line[1].x}
                        y1={line[0].y}
                        y2={line[1].y}
                      />
                    )),
                  )}
                  {quads.flatMap((quad, i) =>
                    manualGridUnavailable(
                      qualificationFlags[i] ?? completeManualGridFlags,
                      quad,
                      imageSize.width,
                      imageSize.height,
                    ).map((cellIndex) => (
                      <polygon
                        key={`partial-${i}-${cellIndex}`}
                        points={(manualGridCellPolygons(quad)[cellIndex] ?? [])
                          .map(pointText)
                          .join(' ')}
                        fill="url(#partial-cell-hatch)"
                        pointerEvents="none"
                      />
                    )),
                  )}
                  {boardCornerPlacement !== null ? (
                    <>
                      {activeBoardPlacementPoints.length > 1 ? (
                        <polyline
                          className="pageGeometryPlacementLine"
                          points={activeBoardPlacementPoints
                            .map(pointText)
                            .join(' ')}
                        />
                      ) : null}
                      {activeBoardPlacementPoints.map((point, index) => (
                        <g key={`board-corner-${index}`}>
                          <circle
                            className="pageGeometryHandle pageGeometryPlacementHandle"
                            cx={point.x}
                            cy={point.y}
                            r={handleRadius}
                          />
                          <text
                            className="pageGeometryPlacementLabel"
                            x={point.x + handleRadius + 4 / zoom}
                            y={point.y - handleRadius - 4 / zoom}
                          >
                            {CORNER_LABELS[index]}
                          </text>
                        </g>
                      ))}
                    </>
                  ) : null}
                  {cornerPlacement !== null ? (
                    <>
                      {cornerPlacement.length > 1 ? (
                        <polyline
                          className="pageGeometryPlacementLine"
                          points={cornerPlacement.map(pointText).join(' ')}
                        />
                      ) : null}
                      {cornerPlacement.map((point, index) => (
                        <g key={index}>
                          <circle
                            className="pageGeometryHandle pageGeometryPlacementHandle"
                            cx={point.x}
                            cy={point.y}
                            r={handleRadius}
                          />
                          <text
                            className="pageGeometryPlacementLabel"
                            x={point.x + handleRadius + 4 / zoom}
                            y={point.y - handleRadius - 4 / zoom}
                          >
                            {CORNER_LABELS[index]}
                          </text>
                        </g>
                      ))}
                    </>
                  ) : null}
                  {cornerPlacement === null && boardCornerPlacement === null
                    ? correctionMode === 'page'
                      ? pageCorners.map((point, index) => (
                          <circle
                            className="pageGeometryHandle"
                            cx={point.x}
                            cy={point.y}
                            key={index}
                            onPointerDown={(event) =>
                              beginDrag(event, {
                                kind: 'page',
                                pointIndex: index,
                              })
                            }
                            r={handleRadius}
                          />
                        ))
                      : correctionMode === 'curve'
                        ? mesh.map((point, index) => (
                            <circle
                              className={
                                isPageGeometryMeshBoundaryPoint(index)
                                  ? 'pageGeometryHandle pageGeometryMeshBoundaryHandle'
                                  : 'pageGeometryHandle pageGeometryMeshInnerHandle'
                              }
                              cx={point.x}
                              cy={point.y}
                              key={index}
                              onPointerDown={(event) =>
                                beginDrag(event, {
                                  kind: 'mesh',
                                  pointIndex: index,
                                })
                              }
                              r={handleRadius}
                            />
                          ))
                        : (quads[correctionMode] ?? []).map((point, index) => (
                            <circle
                              className="pageGeometryHandle pageGeometryBoardHandle"
                              cx={point.x}
                              cy={point.y}
                              key={index}
                              onPointerDown={(event) =>
                                beginDrag(event, {
                                  boardIndex: correctionMode,
                                  kind: 'board',
                                  pointIndex: index,
                                })
                              }
                              r={handleRadius}
                            />
                          ))
                    : null}
                </svg>
              ) : null}
            </div>
          </div>
          {typeof correctionMode === 'number' &&
          imageSize &&
          loadedSourceChecksum === source.sourceChecksumSha256
            ? (() => {
                const index = correctionMode,
                  quad = quads[index] ?? [];
                const flags =
                  qualificationFlags[index] ?? completeManualGridFlags;
                const unavailable = manualGridUnavailable(
                  flags,
                  quad,
                  imageSize.width,
                  imageSize.height,
                );
                const automatic = automaticUnavailableGridCells(
                  quad,
                  imageSize.width,
                  imageSize.height,
                );
                const update = (next: ManualGridFlags) =>
                  setQualificationFlags((previous) =>
                    previous.map((value, i) => (i === index ? next : value)),
                  );
                return (
                  <fieldset
                    className="pageGeometryQualification"
                    disabled={saving || draftConflict}
                  >
                    <legend>
                      Plansza {index + 1} · dostępne {15 - unavailable.length}
                      /15
                    </legend>
                    {manualGridVerticalCropWarning(quad, imageSize.height) ? (
                      <p role="status">
                        Brak góry lub dołu planszy: sprawdź wcześniejsze
                        przycięcie zdjęcia. Zalecana poprawa pliku źródłowego;
                        tej geometrii nie używamy do uczenia ani kotwic.
                      </p>
                    ) : null}
                    {v12Enabled ? (
                      <>
                        <div className="pageGeometryFrameOffsets">
                          {(
                            [
                              ['top', 'Góra'],
                              ['bottom', 'Dół'],
                              ['left', 'Lewo'],
                              ['right', 'Prawo'],
                            ] as const
                          ).map(([side, label]) => (
                            <label key={side}>
                              {label} — odstęp od siatki (%)
                              <input
                                aria-label={`${label} — odstęp od siatki (%)`}
                                max="100"
                                min="-100"
                                onChange={(event) => {
                                  const raw = event.target.value;
                                  const parsed = Number(raw);
                                  setV12FrameOffsets((previous) =>
                                    Array.from(
                                      { length: expectedBoardCount },
                                      (_, slot) => {
                                        const current = previous[slot] ?? {};
                                        if (slot !== index) return current;
                                        const next = { ...current };
                                        if (
                                          raw === '' ||
                                          !Number.isFinite(parsed)
                                        )
                                          delete next[side];
                                        else next[side] = parsed;
                                        return next;
                                      },
                                    ),
                                  );
                                }}
                                step="0.1"
                                type="number"
                                value={v12FrameOffsets[index]?.[side] ?? ''}
                              />
                            </label>
                          ))}
                        </div>
                        <p className="pageGeometryFrameOffsetsHint">
                          Dodatnia wartość rozszerza ramkę na zewnątrz. Ujemną
                          widać w podglądzie; zapis wymaga siatki wewnątrz ramki.
                        </p>
                      </>
                    ) : null}
                    <div className="pageGeometryQualificationRow">
                      <label className="pageGeometryQualificationCheck">
                        <input
                          type="checkbox"
                          checked={flags.partial}
                          onChange={(event) =>
                            update({
                              ...flags,
                              partial: event.target.checked,
                              exclude: event.target.checked || flags.exclude,
                              includeInPartialGridTraining: event.target.checked
                                ? flags.includeInPartialGridTraining
                                : false,
                              manualUnavailable: event.target.checked
                                ? flags.manualUnavailable
                                : [],
                            })
                          }
                        />
                        Niepełna plansza
                      </label>
                      <label className="pageGeometryQualificationCheck">
                        <input
                          type="checkbox"
                          checked={flags.partial || flags.exclude}
                          disabled={flags.partial}
                          onChange={(event) =>
                            update({ ...flags, exclude: event.target.checked })
                          }
                        />
                        Nie używaj do uczenia geometrii
                      </label>
                      <label className="pageGeometryQualificationCheck pageGeometryQualificationNote">
                        <input
                          type="checkbox"
                          checked={flags.includeInPartialGridTraining}
                          disabled={!flags.partial}
                          onChange={(event) =>
                            update({
                              ...flags,
                              includeInPartialGridTraining:
                                event.target.checked,
                            })
                          }
                        />
                        <small>
                          Użyj w oddzielnym uczeniu niepełnych siatek. Zmiana
                          dotyczy kolejnego uczenia, nie już aktywnego profilu.
                        </small>
                      </label>
                    </div>
                    {flags.partial ? (
                      <div className="pageGeometryQualificationCells">
                        {Array.from({ length: 15 }, (_, i) => (
                          <label
                            className="pageGeometryQualificationCheck"
                            key={i}
                          >
                            <input
                              type="checkbox"
                              aria-label={`Pole ${i + 1} poza zdjęciem`}
                              checked={unavailable.includes(i)}
                              disabled={automatic.includes(i)}
                              onChange={(event) =>
                                update({
                                  ...flags,
                                  manualUnavailable: event.target.checked
                                    ? [...flags.manualUnavailable, i]
                                    : flags.manualUnavailable.filter(
                                        (value) => value !== i,
                                      ),
                                })
                              }
                            />
                            {i + 1}
                          </label>
                        ))}
                      </div>
                    ) : null}
                  </fieldset>
                );
              })()
            : null}
        </div>
      ) : null}
    </section>
  );
}
