import { PreviewCache } from './preview-cache.ts';
import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
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
  step,
  changeView,
  ready,
  failed,
}: {
  source: SourceIndex;
  image: SourceImage;
  view: ViewPreferences;
  step: number;
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
    setError(false);
    void cache.current
      .activate(source, image, step, true)
      .then((current) => {
        if (active) {
          current.alt = image.relativePath;
          const element = container.current!;
          const dimensions = fitManualImageToViewport(
            { width: current.naturalWidth, height: current.naturalHeight },
            {
              width: Math.max(1, element.clientWidth),
              height: Math.max(1, element.clientHeight),
            },
            preferences.current.zoom / 100,
          );
          if (!dimensions) throw new Error('Invalid preview dimensions');
          current.style.width = `${dimensions.width}px`;
          current.style.height = `${dimensions.height}px`;
          current.style.maxWidth = 'none';
          current.style.maxHeight = 'none';
          host.current?.replaceChildren(current);
          element.scrollLeft = preferences.current.scrollX;
          element.scrollTop = preferences.current.scrollY;
          cache.current.present(image.id);
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
  }, [source, image.id, step]);
  useEffect(
    () => () => {
      cache.current.clear();
    },
    [],
  );
  const display = size.width
    ? fitManualImageToViewport(size, viewport, view.zoom / 100)
    : null;
  useLayoutEffect(() => {
    const current = host.current?.firstElementChild as HTMLImageElement | null;
    if (current && display) {
      current.style.width = `${display.width}px`;
      current.style.height = `${display.height}px`;
      current.style.maxWidth = 'none';
      current.style.maxHeight = 'none';
      if (container.current) {
        container.current.scrollLeft = preferences.current.scrollX;
        container.current.scrollTop = preferences.current.scrollY;
      }
    }
  }, [display?.width, display?.height, decodedFor]);
  return (
    <div
      className="preview"
      ref={container}
      data-preview-cache={cache.current.size}
      aria-label="Podgląd zdjęcia"
      onScroll={(event) => {
        if (size.width && decodedFor === image.id)
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
        ) : decodedFor !== image.id ? (
          <span
            role="status"
            className="image-loading"
            aria-label="Ładowanie zdjęcia"
          >
            Ładowanie: {image.relativePath}
          </span>
        ) : null}
        <div className="preview-image-host" ref={host} />
      </div>
    </div>
  );
}
