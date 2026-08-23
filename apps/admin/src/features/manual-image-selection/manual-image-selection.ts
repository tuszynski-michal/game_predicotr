'use client';

// Compatibility facade for the existing local manual-selection surface. New
// callers should use the shared core for domain behavior and the local FSA
// adapter for browser file access.
export {
  adjacentManualNavigationStep,
  createManualSelectionOutputManifest,
  createManualSelectionState,
  createManualSelectionTraceManifest,
  INDEPENDENT_MANUAL_SELECTION_ID,
  isSupportedManualImage,
  MANUAL_IMAGE_NAVIGATION_STEPS,
  manualPreviewWindow,
  naturalCompare,
  nextManualSelectionState,
  previousManualSelectionState,
  rangeForStart,
  type ManualDecisionAction,
  type ManualImageDescriptor,
  type ManualOutputFileResult,
  type ManualSelectionDecision,
  type ManualSelectionOutputManifestV1,
  type ManualSelectionState,
  type ManualSelectionTraceEvent,
  type ManualSelectionTraceEventKind,
  type ManualSelectionTraceManifestV1,
} from '@game-predictor/manual-image-selection-core';
export {
  FileSystemManualSelectionOutputAdapter,
  FileSystemManualSelectionSourceAdapter,
  isMissingManualDirectoryHandleError,
  listManualImages,
  relinkManualSelectionSession,
  removeManagedManualOutput,
  sha256Hex,
  writeManualOutput,
  writeManualOutputManifest,
  writeManualTraceManifest,
  type ManualImageFile,
  type ManualSelectionSessionRecord,
} from './manual-image-selection-fsa-adapter.ts';
