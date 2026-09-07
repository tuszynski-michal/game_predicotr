/** Local draft, not an API model. A partial draft may be temporarily incomplete. */
export interface ManualGridFlags {
  readonly partial: boolean;
  readonly exclude: boolean;
  readonly manualUnavailable: readonly number[];
}

export type ManualGridPoint = { readonly x: number; readonly y: number };

export const completeManualGridFlags: ManualGridFlags = {
  partial: false,
  exclude: false,
  manualUnavailable: [],
};

/** Same square-to-quad projective mapping and pixel-centre bounds as the renderer. */
export function manualGridCellPolygons(
  quad: readonly ManualGridPoint[],
): readonly (readonly ManualGridPoint[])[] {
  if (quad.length !== 4) return [];
  const [a, b, c, d] = quad as [
    ManualGridPoint,
    ManualGridPoint,
    ManualGridPoint,
    ManualGridPoint,
  ];
  const dx1 = b.x - c.x,
    dx2 = d.x - c.x;
  const dy1 = b.y - c.y,
    dy2 = d.y - c.y;
  const dx3 = a.x - b.x + c.x - d.x,
    dy3 = a.y - b.y + c.y - d.y;
  const determinant = dx1 * dy2 - dx2 * dy1;
  if (Math.abs(determinant) < 1e-12) return [];
  const g = (dx3 * dy2 - dx2 * dy3) / determinant;
  const h = (dx1 * dy3 - dx3 * dy1) / determinant;
  const at = (u: number, v: number): ManualGridPoint => {
    const scale = g * u + h * v + 1;
    return {
      x: ((b.x - a.x + g * b.x) * u + (d.x - a.x + h * d.x) * v + a.x) / scale,
      y: ((b.y - a.y + g * b.y) * u + (d.y - a.y + h * d.y) * v + a.y) / scale,
    };
  };
  return Array.from({ length: 15 }, (_, i) => {
    const u = (i % 5) / 5,
      v = Math.floor(i / 5) / 3;
    return [
      at(u, v),
      at(u + 1 / 5, v),
      at(u + 1 / 5, v + 1 / 3),
      at(u, v + 1 / 3),
    ];
  });
}

export function automaticUnavailableGridCells(
  quad: readonly ManualGridPoint[],
  width: number,
  height: number,
): readonly number[] {
  return manualGridCellPolygons(quad).flatMap((points, index) =>
    points.some(
      ({ x, y }) =>
        !Number.isFinite(x) ||
        !Number.isFinite(y) ||
        x < -1e-6 ||
        y < -1e-6 ||
        x > width - 1 + 1e-6 ||
        y > height - 1 + 1e-6,
    )
      ? [index]
      : [],
  );
}

/** A vertical loss is an upstream photo-cropping error in the operator workflow. */
export function manualGridVerticalCropWarning(
  quad: readonly ManualGridPoint[],
  height: number,
): boolean {
  return quad.some((point) => point.y < -1e-6 || point.y > height - 1 + 1e-6);
}

export function manualGridUnavailable(
  flags: ManualGridFlags,
  quad: readonly ManualGridPoint[],
  width: number,
  height: number,
): readonly number[] {
  return [
    ...new Set([
      ...automaticUnavailableGridCells(quad, width, height),
      ...flags.manualUnavailable,
    ]),
  ].sort((a, b) => a - b);
}

export function manualGridQualification(
  flags: ManualGridFlags,
  quad: readonly ManualGridPoint[],
  width: number,
  height: number,
) {
  const unavailable = manualGridUnavailable(flags, quad, width, height);
  if (flags.partial !== unavailable.length > 0) {
    throw new Error(
      flags.partial
        ? 'Niepełna plansza wymaga co najmniej jednego niedostępnego pola. Przesuń narożniki lub wskaż pole.'
        : 'Siatka wychodzi poza zdjęcie. Oznacz ją jako niepełną lub popraw narożniki.',
    );
  }
  return {
    version: 'manual-geometry-qualification-v1' as const,
    completenessStatus: flags.partial
      ? ('pending_partial' as const)
      : ('complete' as const),
    unavailableCellIndices: [...unavailable],
    excludeFromGeometryTraining: flags.partial || flags.exclude,
    exclusionReason: flags.partial
      ? ('missing_pixels' as const)
      : flags.exclude
        ? ('manual_exclusion' as const)
        : null,
  };
}

export function validManualGridFlags(value: unknown): value is ManualGridFlags {
  if (!value || typeof value !== 'object') return false;
  const raw = value as ManualGridFlags;
  return (
    typeof raw.partial === 'boolean' &&
    typeof raw.exclude === 'boolean' &&
    Array.isArray(raw.manualUnavailable) &&
    raw.manualUnavailable.length <= 15 &&
    raw.manualUnavailable.every(
      (i) => Number.isInteger(i) && i >= 0 && i < 15,
    ) &&
    new Set(raw.manualUnavailable).size === raw.manualUnavailable.length &&
    (raw.partial || raw.manualUnavailable.length === 0)
  );
}

export function manualGridFlagsFromQualification(
  value:
    | {
        readonly completenessStatus: string;
        readonly excludeFromGeometryTraining: boolean;
        readonly unavailableCellIndices: readonly number[];
      }
    | null
    | undefined,
): ManualGridFlags {
  return value
    ? {
        partial: value.completenessStatus === 'pending_partial',
        exclude: value.excludeFromGeometryTraining,
        manualUnavailable: [...value.unavailableCellIndices],
      }
    : completeManualGridFlags;
}
