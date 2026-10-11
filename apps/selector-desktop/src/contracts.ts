export const APP_URL = 'selector://app/index.html';
export const CHANNELS = {
  pickSource: 'selector:pick-source',
  openLogs: 'selector:open-logs',
} as const;
export interface SourceImage {
  id: string;
  relativePath: string;
  name: string;
  size: number;
  lastModified: number;
  url: string;
}
export interface SourceIndex {
  id: string;
  name: string;
  images: SourceImage[];
}
export type NativeResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: { code: string; message: string } };
export interface SelectorBridge {
  pickSource(): Promise<NativeResult<SourceIndex | null>>;
  openLogs(): Promise<NativeResult<void>>;
}
export class SelectorError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}
export function validateNoArguments(args: unknown[]): void {
  if (args.length !== 0)
    throw new SelectorError(
      'INVALID_ARGUMENT',
      'To polecenie nie przyjmuje argumentów.',
    );
}
export function validateSender(
  senderUrl: string,
  isMainFrame: boolean,
  isWindow: boolean,
): void {
  if (senderUrl !== APP_URL || !isMainFrame || !isWindow)
    throw new SelectorError(
      'UNTRUSTED_SENDER',
      'Niedozwolony nadawca polecenia.',
    );
}
export function parsePhotoUrl(raw: string): {
  sourceId: string;
  imageId: string;
} {
  const match = /^selector-photo:\/\/([a-f0-9-]{36})\/([a-f0-9-]{36})$/.exec(
    raw,
  );
  if (!match)
    throw new SelectorError(
      'INVALID_PHOTO_ID',
      'Niedozwolony identyfikator zdjęcia.',
    );
  return { sourceId: match[1], imageId: match[2] };
}
