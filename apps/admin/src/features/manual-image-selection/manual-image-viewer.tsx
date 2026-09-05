'use client';

/* Browser-local previews intentionally use object URLs and native img decoding. */
/* eslint-disable @next/next/no-img-element */
/* Refs are deliberately passed through the reusable viewer state object. */
/* eslint-disable react-hooks/refs */

import {
  fitManualImageToViewport,
  manualPreviewWindow,
  type ManualImageSize,
} from '@game-predictor/manual-image-selection-core';
import { useEffect, useRef, useState, type ReactNode } from 'react';

export interface ManualImageViewerFile {
  readonly handle: FileSystemFileHandle;
  readonly relativePath: string;
}

interface LoadedImageSize {
  readonly size: ManualImageSize;
  readonly sourceUrl: string;
}

export interface ManualImageViewerState {
  readonly imageViewportRef: React.RefObject<HTMLDivElement | null>;
  readonly isFullscreen: boolean;
  readonly viewerRef: React.RefObject<HTMLDivElement | null>;
  readonly visibleImageUrl: string | null;
  readonly zoom: number;
  readonly zoomedImageSize: ManualImageSize | null;
  readonly sourceImageSize: ManualImageSize | null;
  setZoom: React.Dispatch<React.SetStateAction<number>>;
  toggleFullscreen(): Promise<void>;
  onImageLoad(sourceUrl: string, size: ManualImageSize): void;
  onViewportScroll(scrollLeft: number, scrollTop: number): void;
}

export interface ManualImageViewerInitialView {
  readonly scrollLeft: number;
  readonly scrollTop: number;
  readonly zoom: number;
}

export function useManualImageViewer(
  images: readonly ManualImageViewerFile[],
  currentImageIndex: number,
  onError: (message: string) => void,
  initialView?: ManualImageViewerInitialView,
  onViewChange?: (view: ManualImageViewerInitialView) => void,
): ManualImageViewerState {
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const imageViewportRef = useRef<HTMLDivElement | null>(null);
  const imageUrlCacheRef = useRef<Map<number, string>>(new Map());
  const imageUrlLoadRef = useRef<Map<number, Promise<string>>>(new Map());
  const imageCacheGenerationRef = useRef(0);
  const imageScrollLeftRef = useRef(Math.max(0, initialView?.scrollLeft ?? 0));
  const imageScrollTopRef = useRef(Math.max(0, initialView?.scrollTop ?? 0));
  const pendingScrollRestoreRef = useRef(false);
  const previousImageIndexRef = useRef(currentImageIndex);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageUrlIndex, setImageUrlIndex] = useState(-1);
  const [loadedImageSize, setLoadedImageSize] =
    useState<LoadedImageSize | null>(null);
  const [imageViewportSize, setImageViewportSize] =
    useState<ManualImageSize | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [zoom, setZoom] = useState(() =>
    Math.max(1, Math.min(30, initialView?.zoom ?? 1)),
  );
  const visibleImageUrl = imageUrlIndex === currentImageIndex ? imageUrl : null;
  const zoomedImageSize = fitManualImageToViewport(
    loadedImageSize?.sourceUrl === visibleImageUrl
      ? loadedImageSize.size
      : null,
    imageViewportSize,
    zoom,
  );
  const sourceImageSize =
    loadedImageSize?.sourceUrl === visibleImageUrl
      ? loadedImageSize.size
      : null;

  useEffect(() => {
    onViewChange?.({
      scrollLeft: imageScrollLeftRef.current,
      scrollTop: imageScrollTopRef.current,
      zoom,
    });
  }, [onViewChange, zoom]);

  useEffect(() => {
    const cache = imageUrlCacheRef.current;
    const pendingLoads = imageUrlLoadRef.current;
    pendingScrollRestoreRef.current = true;
    imageCacheGenerationRef.current += 1;
    for (const url of cache.values()) URL.revokeObjectURL(url);
    cache.clear();
    pendingLoads.clear();
    queueMicrotask(() => {
      setImageUrl(null);
      setImageUrlIndex(-1);
    });
    return () => {
      imageCacheGenerationRef.current += 1;
      for (const url of cache.values()) URL.revokeObjectURL(url);
      cache.clear();
      pendingLoads.clear();
    };
  }, [images]);

  useEffect(() => {
    if (previousImageIndexRef.current !== currentImageIndex) {
      pendingScrollRestoreRef.current = true;
      previousImageIndexRef.current = currentImageIndex;
    }
    let cancelled = false;
    const image = images[currentImageIndex];
    if (currentImageIndex < 0 || image === undefined) {
      queueMicrotask(() => {
        if (!cancelled) {
          setImageUrl(null);
          setImageUrlIndex(-1);
        }
      });
      return;
    }

    const generation = imageCacheGenerationRef.current;
    const previewIndexes = manualPreviewWindow(
      currentImageIndex,
      images.length,
    );
    const previewIndexSet = new Set(previewIndexes);
    for (const [index, url] of imageUrlCacheRef.current.entries()) {
      if (!previewIndexSet.has(index)) {
        URL.revokeObjectURL(url);
        imageUrlCacheRef.current.delete(index);
      }
    }

    const loadUrl = (index: number): Promise<string> => {
      const cached = imageUrlCacheRef.current.get(index);
      if (cached !== undefined) return Promise.resolve(cached);
      const pending = imageUrlLoadRef.current.get(index);
      if (pending !== undefined) return pending;
      const target = images[index];
      if (target === undefined)
        return Promise.reject(new Error('IMAGE_OUT_OF_BOUNDS'));
      const load = target.handle
        .getFile()
        .then(async (file) => {
          const url = URL.createObjectURL(file);
          const preview = new Image();
          preview.src = url;
          await preview.decode().catch(() => undefined);
          if (generation !== imageCacheGenerationRef.current) {
            URL.revokeObjectURL(url);
            throw new Error('STALE_IMAGE_CACHE');
          }
          if (
            !manualPreviewWindow(currentImageIndex, images.length).includes(
              index,
            )
          ) {
            URL.revokeObjectURL(url);
            throw new Error('STALE_IMAGE_WINDOW');
          }
          imageUrlCacheRef.current.set(index, url);
          return url;
        })
        .finally(() => imageUrlLoadRef.current.delete(index));
      imageUrlLoadRef.current.set(index, load);
      return load;
    };

    const neighbours = previewIndexes.filter(
      (index) => index !== currentImageIndex,
    );
    void loadUrl(currentImageIndex)
      .then((url) => {
        if (!cancelled) {
          setImageUrl(url);
          setImageUrlIndex(currentImageIndex);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled && !isStaleImageLoad(cause)) {
          onError('Nie udało się odczytać bieżącego zdjęcia.');
        }
      })
      .finally(() => {
        if (!cancelled) {
          void Promise.allSettled(neighbours.map((index) => loadUrl(index)));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [currentImageIndex, images, onError]);

  useEffect(() => {
    const onFullscreenChange = () =>
      setIsFullscreen(document.fullscreenElement === viewerRef.current);
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () =>
      document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  useEffect(() => {
    const viewport = imageViewportRef.current;
    if (viewport === null) return;
    const updateViewportSize = () =>
      setImageViewportSize({
        height: viewport.clientHeight,
        width: viewport.clientWidth,
      });
    updateViewportSize();
    const observer = new ResizeObserver(updateViewportSize);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [currentImageIndex]);

  useEffect(() => {
    if (!pendingScrollRestoreRef.current || zoomedImageSize === null) return;
    const animationFrame = window.requestAnimationFrame(() => {
      const viewport = imageViewportRef.current;
      if (viewport === null) return;
      viewport.scrollLeft = imageScrollLeftRef.current;
      viewport.scrollTop = imageScrollTopRef.current;
      pendingScrollRestoreRef.current = false;
    });
    return () => window.cancelAnimationFrame(animationFrame);
  }, [currentImageIndex, visibleImageUrl, zoomedImageSize]);

  async function toggleFullscreen(): Promise<void> {
    const viewer = viewerRef.current;
    if (viewer === null) return;
    try {
      if (document.fullscreenElement === viewer) {
        await document.exitFullscreen();
      } else {
        if (document.fullscreenElement !== null)
          await document.exitFullscreen();
        await viewer.requestFullscreen();
      }
    } catch (cause) {
      onError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się otworzyć podglądu pełnoekranowego.',
      );
    }
  }

  return {
    imageViewportRef,
    isFullscreen,
    onImageLoad(sourceUrl, size) {
      setLoadedImageSize({ size, sourceUrl });
    },
    onViewportScroll(scrollLeft, scrollTop) {
      if (
        !pendingScrollRestoreRef.current &&
        imageUrlIndex === currentImageIndex
      ) {
        imageScrollLeftRef.current = scrollLeft;
        imageScrollTopRef.current = scrollTop;
        onViewChange?.({ scrollLeft, scrollTop, zoom });
      }
    },
    setZoom,
    sourceImageSize,
    toggleFullscreen,
    viewerRef,
    visibleImageUrl,
    zoom,
    zoomedImageSize,
  };
}

export function ManualImageViewer({
  busy,
  currentLabel,
  currentPosition,
  currentRelativePath,
  fullscreenExtra,
  imageOverlay,
  imageCount,
  navigationStepLabel,
  nextDisabled,
  onNext,
  onPrevious,
  previousDisabled,
  state,
  toolbarStart,
}: {
  readonly busy: boolean;
  readonly currentLabel: string;
  readonly currentPosition: number;
  readonly currentRelativePath: string | null;
  readonly fullscreenExtra?: ReactNode;
  readonly imageOverlay?: ReactNode;
  readonly imageCount: number;
  readonly navigationStepLabel: string;
  readonly nextDisabled: boolean;
  readonly onNext: () => void;
  readonly onPrevious: () => void;
  readonly previousDisabled: boolean;
  readonly state: ManualImageViewerState;
  readonly toolbarStart?: ReactNode;
}) {
  return (
    <>
      <div className="manualImageSelectionViewerToolbar">
        {toolbarStart ?? <span />}
        <div
          className="manualImageSelectionZoom"
          aria-label="Powiększenie zdjęcia"
        >
          <button
            aria-label="Pomniejsz zdjęcie"
            className="secondaryButton"
            disabled={state.zoom <= 1 || busy}
            onClick={() => state.setZoom((value) => Math.max(1, value - 0.25))}
            type="button"
          >
            −
          </button>
          <span>{Math.round(state.zoom * 100)}%</span>
          <button
            aria-label="Powiększ zdjęcie"
            className="secondaryButton"
            disabled={state.zoom >= 30 || busy}
            onClick={() => state.setZoom((value) => Math.min(30, value + 0.25))}
            type="button"
          >
            +
          </button>
        </div>
        <button
          className="secondaryButton"
          disabled={busy}
          onClick={() => void state.toggleFullscreen()}
          type="button"
        >
          {state.isFullscreen ? 'Zamknij pełny ekran' : 'Pełny ekran'}
        </button>
      </div>
      <div className="manualImageSelectionViewer" ref={state.viewerRef}>
        <div className="manualImageSelectionFullscreenInfo" aria-live="polite">
          <strong>{currentLabel}</strong>
          <span>
            zdjęcie {currentPosition} / {imageCount}
          </span>
          <span>{navigationStepLabel}</span>
          <span>{currentRelativePath ?? 'brak zdjęcia'}</span>
          {fullscreenExtra}
        </div>
        <button
          aria-label="Poprzednie zdjęcie"
          className="manualImageSelectionNav"
          disabled={previousDisabled || busy}
          onClick={onPrevious}
          type="button"
        >
          ←
        </button>
        <div className="manualImageSelectionImageFrame">
          <div
            className="manualImageSelectionImageViewport"
            onScroll={(event) =>
              state.onViewportScroll(
                event.currentTarget.scrollLeft,
                event.currentTarget.scrollTop,
              )
            }
            ref={state.imageViewportRef}
          >
            {state.visibleImageUrl === null ? (
              <p>Wczytywanie zdjęcia…</p>
            ) : (
              <div
                className="manualImageSelectionImageCanvas"
                style={
                  state.zoomedImageSize === null
                    ? undefined
                    : {
                        height: `${state.zoomedImageSize.height}px`,
                        width: `${state.zoomedImageSize.width}px`,
                      }
                }
              >
                <img
                  alt={currentRelativePath ?? 'Bieżące zdjęcie'}
                  onLoad={(event) =>
                    state.onImageLoad(state.visibleImageUrl!, {
                      height: event.currentTarget.naturalHeight,
                      width: event.currentTarget.naturalWidth,
                    })
                  }
                  src={state.visibleImageUrl}
                />
                {imageOverlay}
              </div>
            )}
          </div>
          <p className="manualImageSelectionFilename">
            {currentRelativePath ?? 'brak zdjęcia'}
          </p>
        </div>
        <button
          aria-label="Następne zdjęcie"
          className="manualImageSelectionNav"
          disabled={nextDisabled || busy}
          onClick={onNext}
          type="button"
        >
          →
        </button>
      </div>
    </>
  );
}

function isStaleImageLoad(cause: unknown): boolean {
  return (
    cause instanceof Error &&
    (cause.message === 'STALE_IMAGE_CACHE' ||
      cause.message === 'STALE_IMAGE_WINDOW')
  );
}
