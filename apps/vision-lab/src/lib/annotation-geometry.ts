import type { Point } from '../../../../packages/vision-lab-api-client/src/index';

export function interpolateCorners(corners: Point[], columns: 3 | 5): Point[] {
  return Array.from({ length: 4 * (columns + 1) }, (_, index) => {
    const u = (index % (columns + 1)) / columns;
    const v = Math.floor(index / (columns + 1)) / 3;
    const weights = [(1 - u) * (1 - v), u * (1 - v), u * v, (1 - u) * v];
    return {
      x: corners.reduce((n, p, i) => n + p.x * weights[i], 0),
      y: corners.reduce((n, p, i) => n + p.y * weights[i], 0),
      provenance: 'baseline_proposal',
    };
  });
}

export function activeIntervals(intervals: number[]) {
  return intervals
    .filter((value) => value >= 0 && value <= 30000)
    .reduce((a, b) => a + b, 0);
}
