import type { Point } from '../../../../packages/vision-lab-api-client/src/index';

export type Viewport = { x: number; y: number; width: number; height: number };
export type ImageSize = { width: number; height: number };
export function captureHandlePointer(event: {
  preventDefault: () => void;
  pointerId: number;
  currentTarget: {
    ownerSVGElement: { setPointerCapture: (id: number) => void } | null;
  };
}) {
  // Prevent SVG text/image native drag before capturing the custom gesture.
  event.preventDefault();
  event.currentTarget.ownerSVGElement?.setPointerCapture(event.pointerId);
}
export function fullViewport(size: ImageSize): Viewport {
  return { x: 0, y: 0, ...size };
}
export function fitViewport(nodes: Point[], size: ImageSize): Viewport {
  if (!nodes.length || nodes.some((p) => !Number.isFinite(p.x + p.y)))
    return fullViewport(size);
  const xs = nodes.map((p) => p.x),
    ys = nodes.map((p) => p.y);
  const minX = Math.min(...xs),
    maxX = Math.max(...xs);
  const minY = Math.min(...ys),
    maxY = Math.max(...ys);
  const marginX = Math.max(1, (maxX - minX) * 0.08);
  const marginY = Math.max(1, (maxY - minY) * 0.08);
  const x = Math.max(0, minX - marginX),
    y = Math.max(0, minY - marginY);
  return {
    x,
    y,
    width: Math.max(1, Math.min(size.width, maxX + marginX) - x),
    height: Math.max(1, Math.min(size.height, maxY + marginY) - y),
  };
}
export function sourcePoint(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
  view: Viewport,
  size: ImageSize,
): Point {
  return {
    x: Math.max(
      0,
      Math.min(
        size.width - 1,
        view.x + ((clientX - rect.left) / rect.width) * view.width,
      ),
    ),
    y: Math.max(
      0,
      Math.min(
        size.height - 1,
        view.y + ((clientY - rect.top) / rect.height) * view.height,
      ),
    ),
    provenance: 'human',
  };
}
