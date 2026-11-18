import React, { useLayoutEffect, useRef, useState } from 'react';
import type { RangeOverlayPreferences } from '../contracts.ts';

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

export function RangeOverlay({
  text,
  preferences,
  width,
  height,
  change,
}: {
  text: string;
  preferences: RangeOverlayPreferences;
  width: number;
  height: number;
  change: (value: RangeOverlayPreferences) => void;
}) {
  const label = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const gesture = useRef<{
    pointerId: number;
    mode: 'move' | 'resize';
    clientX: number;
    clientY: number;
    preferences: RangeOverlayPreferences;
    width: number;
    height: number;
  } | null>(null);
  useLayoutEffect(() => {
    const element = label.current!;
    const measure = () =>
      setSize({ width: element.offsetWidth, height: element.offsetHeight });
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    measure();
    return () => observer.disconnect();
  }, []);
  return (
    <div
      ref={label}
      className="range-overlay"
      data-testid="range-overlay"
      style={{
        left: preferences.x * Math.max(0, width - size.width),
        top: preferences.y * Math.max(0, height - size.height),
        fontSize: Math.min(
          preferences.fontSize,
          Math.max(8, (width - 20) / (text.length * 0.7)),
        ),
      }}
      title="Przeciągnij napis, aby go przesunąć. Przeciągnij narożnik, aby zmienić rozmiar."
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.stopPropagation();
        gesture.current = {
          pointerId: event.pointerId,
          mode: (event.target as HTMLElement).closest('.range-overlay-resize')
            ? 'resize'
            : 'move',
          clientX: event.clientX,
          clientY: event.clientY,
          preferences: { ...preferences },
          width: size.width,
          height: size.height,
        };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const start = gesture.current;
        if (!start || start.pointerId !== event.pointerId) return;
        const dx = event.clientX - start.clientX;
        const dy = event.clientY - start.clientY;
        if (start.mode === 'move') {
          change({
            ...start.preferences,
            x: clamp(
              start.preferences.x + dx / Math.max(1, width - start.width),
              0,
              1,
            ),
            y: clamp(
              start.preferences.y + dy / Math.max(1, height - start.height),
              0,
              1,
            ),
          });
        } else {
          const horizontal = dx / Math.max(1, start.width);
          const vertical = dy / Math.max(1, start.height);
          const delta =
            Math.abs(horizontal) > Math.abs(vertical) ? horizontal : vertical;
          change({
            ...start.preferences,
            fontSize: clamp(start.preferences.fontSize * (1 + delta), 12, 160),
          });
        }
      }}
      onLostPointerCapture={() => {
        gesture.current = null;
      }}
      onPointerUp={(event) => {
        if (gesture.current?.pointerId !== event.pointerId) return;
        gesture.current = null;
        event.currentTarget.releasePointerCapture(event.pointerId);
      }}
    >
      <span>{text}</span>
      <button
        type="button"
        className="range-overlay-resize"
        aria-label="Zmień rozmiar napisu zakresu"
        title="Przeciągnij narożnik, aby zmienić rozmiar"
        onKeyDown={(event) => {
          if (
            ['ArrowUp', 'ArrowRight', 'ArrowDown', 'ArrowLeft'].includes(
              event.key,
            )
          ) {
            event.preventDefault();
            event.stopPropagation();
            const delta = ['ArrowUp', 'ArrowRight'].includes(event.key)
              ? 2
              : -2;
            change({
              ...preferences,
              fontSize: clamp(preferences.fontSize + delta, 12, 160),
            });
          }
        }}
      />
    </div>
  );
}
