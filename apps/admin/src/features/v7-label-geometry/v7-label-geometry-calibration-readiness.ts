export const V7_LABEL_GEOMETRY_MINIMUM_SOURCES_PER_POSITION = 5;
export const V7_LABEL_GEOMETRY_MINIMUM_CAPTURE_GROUPS_PER_POSITION = 2;

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
  readonly positions: readonly V7LabelGeometryPositionReadiness[];
  readonly readyForProfileCheck: boolean;
}

/**
 * Calculates only local progress diagnostics. The API remains the owner of
 * profile validation, including residual p95 and the frozen source inventory.
 */
export function calculateV7LabelGeometryCalibrationReadiness(input: {
  readonly captureGroups: Readonly<Record<string, string>>;
  readonly slots: readonly V7LabelGeometryReadinessSlot[];
  readonly sources: readonly V7LabelGeometryReadinessSource[];
}): V7LabelGeometryCalibrationReadiness {
  const sourcesById = new Map(
    input.sources.map((source) => [source.sourceId, source] as const),
  );
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
  return {
    positions,
    readyForProfileCheck: positions.every((position) => position.readyForProfileCheck),
  };
}
