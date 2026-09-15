export type SelectedImageCropOutputWriteAction =
  'write' | 'reuse_matching_bytes' | 'reject_changed_output';

export function selectedImageCropOutputWriteAction(input: {
  readonly recordedChecksumSha256: string | null;
  readonly observedChecksumSha256: string | null;
  readonly proposedChecksumSha256: string;
}): SelectedImageCropOutputWriteAction {
  if (
    input.observedChecksumSha256 === input.proposedChecksumSha256 &&
    (input.recordedChecksumSha256 === null ||
      input.recordedChecksumSha256 === input.observedChecksumSha256)
  )
    return 'reuse_matching_bytes';
  if (input.observedChecksumSha256 === input.recordedChecksumSha256)
    return 'write';
  return 'reject_changed_output';
}
