import React, { useEffect, useRef, useState } from 'react';
import {
  fitManualImageToViewport,
  manualPreviewWindow,
} from '@game-predictor/manual-image-selection-core';
import type {
  SourceIndex,
  SourceImage,
  ViewPreferences,
} from '../contracts.ts';
export function ImageViewer({
  source,
  image,
  view,
  changeView,
  ready,
}: {
  source: SourceIndex;
  image: SourceImage;
  view: ViewPreferences;
  changeView: (value: ViewPreferences) => void;
  ready: (id: string | null) => void;
}) {
  const cache = useRef(new Map<string, HTMLImageElement>());
  const container = useRef<HTMLDivElement>(null);
  const preferences = useRef(view);
  preferences.current = view;
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [viewport, setViewport] = useState({ width: 1, height: 1 });
  const [error, setError] = useState(false);
  useEffect(() => {
    const element = container.current!;
    const resize = new ResizeObserver(() =>
      setViewport({
        width: Math.max(1, element.clientWidth),
        height: Math.max(1, element.clientHeight),
      }),
    );
    resize.observe(element);
    return () => resize.disconnect();
  }, []);
  useEffect(() => {
    let active = true;
    ready(null);
    setSize({ width: 0, height: 0 });
    setError(false);
    const ordinal = source.images.findIndex((i) => i.id === image.id);
    const allowed = new Set(
      manualPreviewWindow(ordinal, source.images.length).map(
        (index) => source.images[index].id,
      ),
    );
    for (const [id, entry] of cache.current)
      if (!allowed.has(id)) {
        entry.src = '';
        cache.current.delete(id);
      }
    for (const id of allowed)
      if (!cache.current.has(id)) {
        const entry = new Image();
        entry.src = source.images.find((i) => i.id === id)!.url;
        cache.current.set(id, entry);
        void entry.decode().catch(() => {});
      }
    const current = cache.current.get(image.id)!;
    void current
      .decode()
      .then(() => {
        if (active) {
          setSize({
            width: current.naturalWidth,
            height: current.naturalHeight,
          });
          ready(image.id);
        }
      })
      .catch(() => {
        if (active) {
          setError(true);
          ready(null);
        }
      });
    return () => {
      active = false;
    };
  }, [source.id, image.id]);
  useEffect(
    () => () => {
      for (const entry of cache.current.values()) entry.src = '';
      cache.current.clear();
    },
    [],
  );
  useEffect(() => {
    if (!size.width) return;
    const handle = requestAnimationFrame(() => {
      if (container.current) {
        container.current.scrollLeft = preferences.current.scrollX;
        container.current.scrollTop = preferences.current.scrollY;
      }
    });
    return () => cancelAnimationFrame(handle);
  }, [image.id, view.zoom, size.width, viewport.width, viewport.height]);
  const display = size.width
    ? fitManualImageToViewport(size, viewport, view.zoom / 100)
    : null;
  return (
    <div
      className="preview"
      ref={container}
      data-preview-cache={cache.current.size}
      aria-label="Podgląd zdjęcia"
      onScroll={(event) => {
        if (size.width)
          changeView({
            ...preferences.current,
            scrollX: event.currentTarget.scrollLeft,
            scrollY: event.currentTarget.scrollTop,
          });
      }}
    >
      <div className="preview-stage">
        {error ? (
          <p role="alert">
            Nie można odczytać JPEG-a. Plik jest uszkodzony, zmieniony lub
            niedostępny.
          </p>
        ) : !display ? (
          <span className="image-loading" aria-label="Ładowanie zdjęcia" />
        ) : (
          <img
            src={image.url}
            alt={image.relativePath}
            style={{
              width: display.width,
              height: display.height,
              maxWidth: 'none',
              maxHeight: 'none',
            }}
          />
        )}
      </div>
    </div>
  );
}
