import { type ProjectState, type ProjectDecision } from '../project/types.ts';

export const OUTPUT_MANIFEST_NAME = 'manual-image-selection-output-v1.json';
/** Wire-compatible with Reviewer's OperatorLocalOutputManifestV2.
 * No core-items, repair data, training trace, or remote session is produced.
 */
export interface OperatorLocalManifestV2 {
  schemaVersion: 2;
  storageMode: 'operator_local';
  sessionId: string;
  batchId: string;
  sourceDirectoryName: string;
  sourceManifestChecksumSha256: string;
  fileCount: number;
  firstLayout: number;
  direction: 'ascending' | 'descending';
  sourceTraversalSemantics: 'natural_v2';
  sequenceUpperBound: number | null;
  selectionComplete: boolean;
  decisions: ProjectDecision[];
  currentIndex: number;
  nextRangeStart: number;
  updatedAt: string;
}
export function projectManifest(state: ProjectState): OperatorLocalManifestV2 {
  const ordinal = state.inventory.findIndex(
    (image) => image.relativePath === state.currentRelativePath,
  );
  return {
    schemaVersion: 2,
    storageMode: 'operator_local',
    sessionId: state.projectId,
    batchId: state.projectId,
    sourceDirectoryName: state.sourceDirectoryName,
    sourceManifestChecksumSha256: state.sourceManifestChecksumSha256,
    fileCount: state.inventory.length,
    firstLayout: state.firstLayout,
    direction: state.direction,
    sourceTraversalSemantics: 'natural_v2',
    sequenceUpperBound: state.sequenceUpperBound,
    selectionComplete: state.selectionComplete,
    decisions: state.decisions,
    currentIndex: Math.max(0, ordinal),
    nextRangeStart: state.nextRangeStart,
    updatedAt: state.updatedAt,
  };
}
