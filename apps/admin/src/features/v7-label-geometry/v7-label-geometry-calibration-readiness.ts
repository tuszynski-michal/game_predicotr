export const V7_LABEL_GEOMETRY_MINIMUM_SOURCES_PER_POSITION = 5;
export const V7_LABEL_GEOMETRY_MINIMUM_CAPTURE_GROUPS_PER_POSITION = 2;
export const V7_LABEL_GEOMETRY_DYNAMIC_FAMILY_ID = 'standard_3x3_numeric_labels_v2';
export const V7_LABEL_GEOMETRY_MINIMUM_DYNAMIC_POINTS_PER_SOURCE = 5;

export interface V7LabelGeometryReadinessSource {
  readonly sourceChecksumSha256: string;
  readonly sourceId: string;
}

export interface V7LabelGeometryReadinessSlot {
  readonly cropAssessment?: 'contained' | 'clipped' | 'uncertain' | null;
  readonly positionIndex: number;
  readonly sourceId: string;
  readonly state: 'annotated' | 'unavailable' | 'unreviewed';
}

export interface V7LabelGeometryPositionReadiness {
  readonly captureGroupCount: number;
  readonly containedAnnotationCount: number;
  readonly incompleteAnnotationCount: number;
  readonly positionIndex: number;
  readonly readyForProfileCheck: boolean;
  readonly sourceCount: number;
  readonly unavailableCount: number;
}

export interface V7LabelGeometryCalibrationReadiness {
  /**
   * V2 fits a local grid per photo, so every photo that contributes points
   * needs five of them across two rows and two columns. Otherwise the server
   * rejects the whole profile, not only that photo.
   */
  readonly incompleteLatticeSourceIds: readonly string[];
  readonly positions: readonly V7LabelGeometryPositionReadiness[];
  readonly readyForProfileCheck: boolean;
}

/**
 * Calculates only local progress diagnostics. The API remains the owner of
 * profile validation, including residual p95 and the frozen source inventory.
 */
export function calculateV7LabelGeometryCalibrationReadiness(input: {
  readonly captureGroups: Readonly<Record<string, string>>;
  readonly geometryFamilyId?: string;
  readonly slots: readonly V7LabelGeometryReadinessSlot[];
  readonly sources: readonly V7LabelGeometryReadinessSource[];
}): V7LabelGeometryCalibrationReadiness {
  const sourcesById = new Map(
    input.sources.map((source) => [source.sourceId, source] as const),
  );
  const profilePositionsBySource = new Map<string, number[]>();
  const positions = Array.from({ length: 9 }, (_, positionIndex) => {
    const sourceChecksums = new Set<string>();
    const captureGroups = new Set<string>();
    let containedAnnotationCount = 0;
    let incompleteAnnotationCount = 0;
    let unavailableCount = 0;

    for (const slot of input.slots) {
      if (slot.positionIndex !== positionIndex) continue;
      if (slot.state === 'unavailable') {
        unavailableCount += 1;
        continue;
      }
      if (slot.state !== 'annotated') continue;
      if (slot.cropAssessment !== 'contained') {
        incompleteAnnotationCount += 1;
        continue;
      }
      const source = sourcesById.get(slot.sourceId);
      const captureGroup = input.captureGroups[slot.sourceId]?.trim();
      if (source === undefined || captureGroup === undefined || captureGroup === '') {
        incompleteAnnotationCount += 1;
        continue;
      }
      containedAnnotationCount += 1;
      const sourcePositions = profilePositionsBySource.get(slot.sourceId) ?? [];
      sourcePositions.push(positionIndex);
      profilePositionsBySource.set(slot.sourceId, sourcePositions);
      sourceChecksums.add(source.sourceChecksumSha256);
      captureGroups.add(captureGroup);
    }

    const sourceCount = sourceChecksums.size;
    const captureGroupCount = captureGroups.size;
    return {
      captureGroupCount,
      containedAnnotationCount,
      incompleteAnnotationCount,
      positionIndex,
      readyForProfileCheck:
        sourceCount >= V7_LABEL_GEOMETRY_MINIMUM_SOURCES_PER_POSITION &&
        captureGroupCount >= V7_LABEL_GEOMETRY_MINIMUM_CAPTURE_GROUPS_PER_POSITION,
      sourceCount,
      unavailableCount,
    };
  });
  const incompleteLatticeSourceIds =
    input.geometryFamilyId === V7_LABEL_GEOMETRY_DYNAMIC_FAMILY_ID
      ? [...profilePositionsBySource.entries()]
          .filter(([, sourcePositions]) => !spansDynamicLattice(sourcePositions))
          .map(([sourceId]) => sourceId)
          .sort()
      : [];
  return {
    incompleteLatticeSourceIds,
    positions,
    readyForProfileCheck:
      incompleteLatticeSourceIds.length === 0 &&
      positions.every((position) => position.readyForProfileCheck),
  };
}

function spansDynamicLattice(positions: readonly number[]): boolean {
  const unique = new Set(positions);
  const rows = new Set([...unique].map((position) => Math.floor(position / 3)));
  const columns = new Set([...unique].map((position) => position % 3));
  return (
    unique.size >= V7_LABEL_GEOMETRY_MINIMUM_DYNAMIC_POINTS_PER_SOURCE &&
    rows.size >= 2 &&
    columns.size >= 2
  );
}
