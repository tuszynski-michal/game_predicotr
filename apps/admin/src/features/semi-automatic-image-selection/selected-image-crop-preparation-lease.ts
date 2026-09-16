export const SELECTED_IMAGE_CROP_PREPARATION_ALREADY_RUNNING =
  'SELECTED_IMAGE_CROP_PREPARATION_ALREADY_RUNNING' as const;

const STATE_DIRECTORY = '.manual-image-crop-state';
const LEASE_FILE = 'browser-preparation.lock';

interface ExclusiveWritableOptions extends FileSystemCreateWritableOptions {
  readonly mode: 'exclusive';
}

export interface SelectedImageCropPreparationLease {
  release(): Promise<void>;
}

export async function acquireSelectedImageCropPreparationLease(
  outputDirectory: FileSystemDirectoryHandle,
): Promise<SelectedImageCropPreparationLease> {
  const stateDirectory = await outputDirectory.getDirectoryHandle(
    STATE_DIRECTORY,
    { create: true },
  );
  const leaseFile = await stateDirectory.getFileHandle(LEASE_FILE, {
    create: true,
  });
  let writable: FileSystemWritableFileStream;
  try {
    writable = await leaseFile.createWritable({
      keepExistingData: true,
      mode: 'exclusive',
    } as ExclusiveWritableOptions);
  } catch (cause) {
    if (
      cause instanceof DOMException &&
      (cause.name === 'InvalidStateError' ||
        cause.name === 'NoModificationAllowedError')
    ) {
      throw new Error(SELECTED_IMAGE_CROP_PREPARATION_ALREADY_RUNNING);
    }
    throw cause;
  }

  let released = false;
  return {
    async release() {
      if (released) return;
      released = true;
      await writable.abort().catch(() => undefined);
    },
  };
}

export async function withSelectedImageCropPreparationLease<T>(
  outputDirectory: FileSystemDirectoryHandle,
  operation: () => Promise<T>,
): Promise<T> {
  const lease = await acquireSelectedImageCropPreparationLease(outputDirectory);
  try {
    return await operation();
  } finally {
    await lease.release();
  }
}
