import { SELECTED_IMAGE_CROP_FILLED_GAPS_OUTPUT_SUFFIX } from '@game-predictor/manual-image-selection-core/crop';

export type SelectedImageCropSourceSelection = 'all' | 'filled_gaps';

export function isSelectedImageCropSourceDirectoryVisible(input: {
  readonly directoryName: string;
  readonly sourceSelection: SelectedImageCropSourceSelection;
  readonly hasFilledGapsManifest: boolean;
}): boolean {
  if (input.sourceSelection === 'all')
    return !input.directoryName.endsWith(' cut');
  return (
    input.hasFilledGapsManifest &&
    !input.directoryName.endsWith(SELECTED_IMAGE_CROP_FILLED_GAPS_OUTPUT_SUFFIX)
  );
}
