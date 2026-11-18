import type { RangeOverlayPreferences } from './contracts.ts';

export const DEFAULT_RANGE_OVERLAY: RangeOverlayPreferences = {
  enabled: false,
  x: 0.05,
  y: 0.05,
  fontSize: 32,
};

export function isRangeOverlay(
  value: unknown,
): value is RangeOverlayPreferences {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const v = value as RangeOverlayPreferences;
  return (
    Object.keys(v).sort().join(',') === 'enabled,fontSize,x,y' &&
    typeof v.enabled === 'boolean' &&
    Number.isFinite(v.x) &&
    v.x >= 0 &&
    v.x <= 1 &&
    Number.isFinite(v.y) &&
    v.y >= 0 &&
    v.y <= 1 &&
    Number.isFinite(v.fontSize) &&
    v.fontSize >= 12 &&
    v.fontSize <= 160
  );
}
