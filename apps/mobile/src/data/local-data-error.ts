export const LOCAL_DATA_ERROR_CODE = 'local_data_error';

export class LocalDataError extends Error {
  readonly code = LOCAL_DATA_ERROR_CODE;

  constructor(message: string) {
    super(message);
    this.name = 'LocalDataError';
  }
}

export function asLocalDataError(
  error: unknown,
  context?: string,
): LocalDataError {
  if (error instanceof LocalDataError) {
    return error;
  }

  const detail =
    error instanceof Error ? error.message : 'Unknown local data error.';
  return new LocalDataError(context ? `${context}: ${detail}` : detail);
}
