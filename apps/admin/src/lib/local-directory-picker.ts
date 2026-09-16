export type LocalDirectoryPickerMode = 'read' | 'readwrite';

export interface LocalDirectoryPickerOptions {
  readonly id?: string;
  readonly mode: LocalDirectoryPickerMode;
}

interface DirectoryPickerWindow extends Window {
  showDirectoryPicker?: (
    options?: LocalDirectoryPickerOptions,
  ) => Promise<FileSystemDirectoryHandle>;
}

export class LocalDirectoryPickerActiveError extends Error {
  constructor() {
    super(
      'Trwa wybór folderu w innym lokalnym module. Zamknij lub anuluj otwarte okno wyboru folderu, a następnie spróbuj ponownie.',
    );
    this.name = 'LocalDirectoryPickerActiveError';
  }
}

let pickerActive = false;
const listeners = new Set<() => void>();

export function isLocalDirectoryPickerActive(): boolean {
  return pickerActive;
}

export function subscribeLocalDirectoryPickerActive(
  listener: () => void,
): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export async function pickLocalDirectory(
  options: LocalDirectoryPickerOptions,
): Promise<FileSystemDirectoryHandle> {
  if (pickerActive) throw new LocalDirectoryPickerActiveError();

  const picker = (window as DirectoryPickerWindow).showDirectoryPicker;
  if (picker === undefined) {
    throw new Error('Ta przeglądarka nie obsługuje wyboru folderu lokalnego.');
  }

  setPickerActive(true);
  try {
    return await picker.call(window, options);
  } catch (cause) {
    if (isNativePickerAlreadyActive(cause)) {
      throw new LocalDirectoryPickerActiveError();
    }
    throw cause;
  } finally {
    setPickerActive(false);
  }
}

function setPickerActive(next: boolean): void {
  if (pickerActive === next) return;
  pickerActive = next;
  for (const listener of listeners) listener();
}

function isNativePickerAlreadyActive(cause: unknown): boolean {
  return (
    cause instanceof DOMException &&
    cause.name === 'InvalidStateError' &&
    cause.message.toLowerCase().includes('file picker already active')
  );
}
