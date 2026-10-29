import { PreviewCache } from './preview-cache.ts';
import React, { useEffect, useRef, useState } from 'react';
import { fitManualImageToViewport } from '@game-predictor/manual-image-selection-core';
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
  failed,
}: {
  source: SourceIndex;
  image: SourceImage;
  view: ViewPreferences;
  changeView: (value: ViewPreferences) => void;
  ready: (id: string | null) => void;
  failed: (id: string) => void;
}) {
  const cache = useRef(new PreviewCache());
  const host = useRef<HTMLDivElement>(null);
  const container = useRef<HTMLDivElement>(null);
  const preferences = useRef(view);
  preferences.current = view;
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [viewport, setViewport] = useState({ width: 1, height: 1 });
  const [error, setError] = useState(false);
  const [decodedFor, setDecodedFor] = useState<string | null>(null);
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
    host.current?.replaceChildren();
    setDecodedFor(null);
    void cache.current
      .activate(source, image)
      .then((current) => {
        if (active) {
          current.alt = image.relativePath;
          host.current?.replaceChildren(current);
          setSize({
            width: current.naturalWidth,
            height: current.naturalHeight,
          });
          setDecodedFor(image.id);
          ready(image.id);
        }
      })
      .catch(() => {
        if (active) {
          setError(true);
          ready(null);
          failed(image.id);
        }
      });
    return () => {
      active = false;
    };
  }, [source, image.id]);
  useEffect(
    () => () => {
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
  const display =
    decodedFor === image.id && size.width
      ? fitManualImageToViewport(size, viewport, view.zoom / 100)
      : null;
  useEffect(() => {
    const current = host.current?.firstElementChild as HTMLImageElement | null;
    if (current && display) {
      current.style.width = `${display.width}px`;
      current.style.height = `${display.height}px`;
      current.style.maxWidth = 'none';
      current.style.maxHeight = 'none';
    }
  }, [display?.width, display?.height, decodedFor]);
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
        ) : null}
        <div className="preview-image-host" ref={host} />
      </div>
    </div>
  );
}
